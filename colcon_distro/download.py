import asyncio
import contextlib
import httpx
from io import StringIO
import re
import logging
import os
import pathlib
from tempfile import TemporaryDirectory
import urllib.parse

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class DownloadError(Exception):
    """
    General exception for download-related errors.
    """
    pass


class CountedClient:
    """
    The httpx library can use connection pooling if we use a common Client object for
    all requests. The purpose of this container is to supply that common object while still
    ensuring that it is properly closed when all requests in a batch are complete.
    """
    PARALLELISM = 8
    instance = None

    def __init__(self):
        self.sem = None
        self.client = None

    @classmethod
    @contextlib.asynccontextmanager
    async def get(cls):
        if not cls.instance:
            cls.instance = cls()

        if not cls.instance.client:
            cls.instance.client = httpx.AsyncClient()
            cls.instance.sem = asyncio.Semaphore(cls.PARALLELISM)

        async with cls.instance.sem:
            yield cls.instance.client

        # Here we peek at the semaphore's internal counter and if it's back at the
        # original value (all uses have been released) then we shut everything down.
        if cls.instance.sem._value == cls.PARALLELISM:
            c = cls.instance.client
            cls.instance.client = None
            cls.instance.sem = None
            await c.aclose()


class GitTarballDownloader:
    """
    Generic tarball downloader which is lightly specialized in subclasses for specific hosts.
    """
    headers = {}

    def __init__(self, **args):
        self.__dict__.update(args)
        self.base_url = self.BASE_URL.format(server=self.server)
        self.repo_path_quoted = urllib.parse.quote(self.repo_path, safe='')

    @contextlib.asynccontextmanager
    async def stream_resource(self, url_path, headers=None):
        """
        Yields an httpx response object for a resource on the git server.
        """
        url = f"{self.base_url}/{url_path}"
        async with CountedClient.get() as client:
            async with client.stream('GET', url, headers=(headers or self.headers)) as response:
                if response.status_code != 200:
                    raise DownloadError(f"HTTP {response.status_code} fetching {url}")
                yield response

    @contextlib.asynccontextmanager
    async def stream_repo_tarball(self):
        """
        Yields an httpx response object for a stream of the repo's main tarball.
        """
        url_path = self.TARBALL_PATH.format(**self.__dict__)
        async with self.stream_resource(url_path) as response:
            yield response

    @contextlib.asynccontextmanager
    async def stream_repo_file(self, path):
        """
        Yields an httpx response object for a stream of a repository file.
        """
        path_quoted = urllib.parse.quote(path, safe='')
        url_path = self.FILE_PATH.format(**locals(), **self.__dict__)
        async with self.stream_resource(url_path) as response:
            yield response

    async def extract_tarball_to(self, path):
        tar_proc = None
        tar_output = []

        async with self.stream_repo_tarball() as tarball_stream:
            tar_proc = await asyncio.create_subprocess_exec('tar', '--extract', '--verbose', '--gzip',
                    cwd=path, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)

            async def pass_stdin():
                async for chunk in tarball_stream.aiter_bytes():
                    tar_proc.stdin.write(chunk)
                    await tar_proc.stdin.drain()
                tar_proc.stdin.close()
                await tar_proc.wait()

            async def pass_stdout():
                while line := await tar_proc.stdout.readline():
                    tar_output.append(line.decode())

            await asyncio.wait([pass_stdin(), pass_stdout()])
        return tar_output

    async def download_all_to(self, path):
        """
        Unlike the plain tarball downloader, this also unpacks the result, and can
        therefore do extra stuff like fetch submodules and LFS objects.
        """
        # Download and extract the main repo archive.
        tar_output = await self.extract_tarball_to(path)
        logger.info(f"> {self.version} {self.repo_path} [archive]")

        # Scan the list of extracted files for .gitattributes which may signal the presence
        # of LFS objects which need to be retrieved.
        git_attributes_filepaths = list(_find_files_in_list(path, tar_output, '.gitattributes'))
        if git_attributes_filepaths:
            if lfs_object_dict := dict(self.get_lfs_objects(git_attributes_filepaths)):
                await self.download_all_lfs(lfs_object_dict)
                lfs_count = len(lfs_object_dict)
                logger.info(f"> {self.version} {self.repo_path} [{lfs_count} LFS object(s)]")

        # TODO: Scan for .gitmodules, and if found, recursively instantiate GitRevs for them
        # so that they also can be download_all_to'd the correct paths.

    def get_lfs_objects(self, git_attributes_filepaths):
        """
        Open all files matching the gitattributes globs. Generate nested tuples which
        can become a dict mapping the special LFS hashes back to their actual filenames
        and sizes.

        This function is synchronous simply because the LFS metadata files are very
        small and it doesn't seem worth pushing this work off to an executor thread.
        """
        for attributes_filepath in git_attributes_filepaths:
            for lfs_filepath in _find_files_from_git_attributes(attributes_filepath):
                with open(lfs_filepath, 'r') as f:
                    if f.readline() != 'version https://git-lfs.github.com/spec/v1\n':
                        return
                    match = re.match("oid sha256:([0-9a-f]+)\nsize ([0-9]+)", f.read(), re.MULTILINE)
                    if not match:
                        raise DownloadError(f"Unable to parse LFS information for {filepath}")
                    lfs_sha, lfs_size = match.groups()
                    yield lfs_sha, (lfs_filepath, lfs_size)

    async def download_all_lfs(self, lfs_object_dict):
        """
        This isn't as bad as it looks. Bascially git-lfs puts marker files in the actual
        repo, and those markers contain a hash which may be used to get an actual download
        link and authorization code from a separate Git LFS server. Note that this may be
        batched, so we only make a single request which gets us all LFS download links in
        a single go.

        The overall flow is top-to-bottom in this outer function; see the individual pieces
        for further details.
        """
        def _get_lfs_request(lfs_object_dict):
            """
            Consumes the dict from the above function and returns the JSON-ready object
            structure which is expected by the LFS server.
            """
            def _object_list():
                for lfs_sha, (lfs_filepath, lfs_size) in lfs_object_dict.items():
                    yield {"oid": lfs_sha, "size": lfs_size}
            return {
               "operation": "download",
               "objects": list(_object_list()),
               "transfers": ["lfs-standalone-file", "basic"],
               "ref": {"name": self.version}
            }

        def _generate_downloaders(response_objects):
            """
            For each object given in the LFS response, this generator yields
            a downloader coroutine which takes care of writing it to the correct
            location on disk and confirming the size when finished.
            """
            for obj in response_objects:
                async def _downloader(obj):
                    dl = obj['actions']['download']
                    async with CountedClient.get() as client:
                        stream = client.stream('GET', dl['href'], headers=dl['header'])
                        async with stream as response:
                            if response.status_code != 200:
                                raise DownloadError(f"Received HTTP {response.status_code} while" +
                                                    f"fetching LFS object from {dl['href']}")
                            lfs_filepath, lfs_size = lfs_object_dict[obj['oid']]
                            with open(lfs_filepath, 'wb') as lfs_file:
                                async for chunk in response.aiter_bytes():
                                    lfs_file.write(chunk)
                                if not lfs_file.tell() != lfs_size:
                                    raise DownloadError(f"LFS object size expected {lfs_size}, actual {lfs_file.tell()}.")
                yield _downloader(obj)

        async with CountedClient.get() as client:
            # Auth for the LFS server is slightly different than main GitLab.
            auth = ('oauth2', self.headers['Private-Token'])
            url = f'{self.base_url}/{self.repo_path}.git/info/lfs/objects/batch'

            # This is where we scan for objects in the repo which must be downloaded
            # from LFS, and sent off a list of them to the server.
            request_json = _get_lfs_request(lfs_object_dict)
            response = await client.post(url, auth=auth, json=request_json)

        if response.status_code != 200:
            raise DownloadError("Got {response.status_code} accessing {url} for LFS objects.")
        await asyncio.gather(*_generate_downloaders(response.json()['objects']))


def _find_files_in_list(path, file_list, name):
    """
    Scans a list of files (eg, from tar output) looking for instances
    of a specific filename.
    """
    name += '\n'
    for line in file_list:
        if line.endswith(name):
            yield path / line.strip()


def _find_files_from_git_attributes(attributes_filepath, filter_type="lfs"):
    """
    This is a naive implementation of the git globbing rules, see:
    https://git-scm.com/docs/gitattributes
    https://git-scm.com/docs/gitignore
    """
    with open(attributes_filepath, 'r') as f:
        attributes_contents = f.read()
    for attributes_line in attributes_contents.splitlines():
        if attributes_line.startswith('#'):
            continue
        line_parts = attributes_line.split()
        if f'filter={filter_type}' in line_parts:
            git_glob = line_parts[0]
            if os.path.sep not in git_glob:
                git_glob = f"**/{git_glob}"
            yield from attributes_filepath.parent.glob(git_glob)


class GithubDownloader(GitTarballDownloader):
    SERVER_REGEX = re.compile(r'^github\.com')
    BASE_URL = 'https://{server}'
    TARBALL_PATH = '{repo_path}/archive/{version}.tar.gz'


class GitLabDownloader(GitTarballDownloader):
    SERVER_REGEX = re.compile(r'^gitlab\.')
    BASE_URL = 'http://{server}'
    TARBALL_PATH = 'api/v4/projects/{repo_path_quoted}/repository/archive.tar.gz?sha={version}'
    FILE_PATH = 'api/v4/projects/{repo_path_quoted}/repository/files/{path_quoted}/raw?ref={version}'
    headers = { 'Private-Token': os.environ.get('GITLAB_PRIVATE_TOKEN', '') }


class GitRev:
    """
    This class is the main entry point of the module, supplying asynchronous methods to
    intelligently download/access the contents of a remote git repo at a specific ref.
    """
    URL_REGEX = re.compile('(?:\w+:\/\/|git@)(?P<server>[\w.-]+)[:/](?P<repo_path>[\w/-]*)(?:\.git)?$')
    DOWNLOADERS = [GitLabDownloader, GithubDownloader]

    def __init__(self, url, version):
        if not (match := self.URL_REGEX.match(url)):
            raise DownloadError(f"Unable to parse version control URL: {url}")
        self.__dict__.update(match.groupdict())
        self.url = url
        self.version = version
        self.downloader = self._get_downloader()

    def _get_downloader(self):
        for dl in self.DOWNLOADERS:
            if dl.SERVER_REGEX.match(self.server):
                return dl(server=self.server, repo_path=self.repo_path, version=self.version)
        raise DownloadError(f"Unable to find downloader for URL: {url}")

    @contextlib.asynccontextmanager
    async def tempdir_download(self):
        dirname = self.repo_path.replace('/', '-')
        with TemporaryDirectory(suffix=dirname) as tempdir:
            await self.downloader.download_all_to(pathlib.Path(tempdir))
            yield tempdir

    async def version_hash_lookup(self):
        git_proc = await asyncio.create_subprocess_exec('git', 'ls-remote', self.url, self.version,
                                                        stdout=asyncio.subprocess.PIPE)
        git_output, git_stderr = await git_proc.communicate()
        if git_stderr:
            logger.error(f"Unexpected error output from git ls-remote: {git_stderr}")
        return git_output.split()[0].decode()

    async def get_file(self, path):
        async with self.downloader.stream_repo_file(path) as response:
            return await response.aread()
