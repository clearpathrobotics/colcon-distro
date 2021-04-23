import asyncio
import contextlib
import httpx
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


# TODO: Consider replacing the curl subprocess stuff with RPC calls to a aria2 daemon.

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
    async def stream_resource(self, url_path):
        """
        Yields an httpx response object for a resource on the git server.
        """
        url = f"{self.base_url}/{url_path}"
        async with httpx.AsyncClient() as client:
            async with client.stream('GET', url, headers=self.headers) as response:
                if response.status_code != 200:
                    raise DownloadError(f"HTTP {response.status_code} fetching {url}")
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

    async def extract_tarball_to(self, path, limit_paths=None):
        # Originally this was an httpx download, but then the pipes had to be managed
        # inside asyncio, which was a pain and the performance was significantly worse
        # compared to this approach. Also, it didn't work with uvloop, which this does.
        url_path = self.TARBALL_PATH.format(**self.__dict__)
        header_strs = [f'-H "{k}:{v}"' for k, v in self.headers.items()]
        curl_cmd = f'curl -L {" ".join(header_strs)} {self.base_url}/{url_path}'
        tar_cmd = 'tar --extract --verbose --gzip --strip-components=1'
        if limit_paths and '.' not in limit_paths:
            tar_cmd = ' '.join([tar_cmd, "--wildcards", "--no-wildcards-match-slash"]
                               + ["*/%s" % p for p in limit_paths])
        tar_proc = await asyncio.create_subprocess_shell(
            f"{curl_cmd} | {tar_cmd}", cwd=path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        tar_stdout, tar_stderr = await tar_proc.communicate()
        if tar_proc.returncode != 0:
            raise DownloadError("Archive download failed.")
        filelist = [line.decode().split(os.path.sep, maxsplit=1)[1]
                    for line in tar_stdout.splitlines()]
        return filelist

    async def download_all_to(self, path, limit_paths=None):
        """
        Unlike the plain tarball downloader, this also unpacks the result, and can
        therefore do extra stuff like fetch submodules and LFS objects.
        """
        # Download and extract the main repo archive.
        tar_output = await self.extract_tarball_to(path, limit_paths)
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
                # The lfs_filepath is absolute, since it comes assembled to the
                # absolute path of the gitattributes file which identified it.
                with open(lfs_filepath, 'rb') as f:
                    if f.readline() != b'version https://git-lfs.github.com/spec/v1\n':
                        return
                    match = re.match(b"oid sha256:([0-9a-f]+)\nsize ([0-9]+)", f.read(), re.MULTILINE)
                    if not match:
                        raise DownloadError(f"Unable to parse LFS information for {lfs_filepath}")
                    lfs_sha = match.group(1).decode()
                    lfs_size = int(match.group(2))
                    yield lfs_sha, (lfs_filepath, lfs_size)

    async def download_all_lfs(self, lfs_object_dict):
        """
        Git LFS puts marker files in the actual repo, and those markers contain a hash
        which may be used to get an actual download link and authorization code from a
        separate Git LFS server. Since this may be batched, we only make a single request
        which gets us all LFS download links in a single go.
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

        # Auth for the LFS server is slightly different than main GitLab.
        auth = ('oauth2', self.headers['Private-Token'])
        url = f'{self.base_url}/{self.repo_path}.git/info/lfs/objects/batch'

        # This is where we scan for objects in the repo which must be downloaded
        # from LFS, and sent off a list of them to the server.
        request_json = _get_lfs_request(lfs_object_dict)
        async with httpx.AsyncClient() as client:
            response = await client.post(url, auth=auth, json=request_json)

        # Now we have the URLs and auth codes, build up a cURL request to grab
        # them all.
        curl_config = []
        lfs_objs = response.json()['objects']
        for k, v in lfs_objs[0]['actions']['download']['header'].items():
            curl_config.append(f"header = \"{k}: {v}\"")
        for obj in lfs_objs:
            lfs_filepath, lfs_size = lfs_object_dict[obj['oid']]
            dl = obj['actions']['download']
            curl_config.append(f"output = {lfs_filepath}")
            curl_config.append(f"url = {dl['href']}")

        curl_proc = await asyncio.create_subprocess_exec(
            'curl', '-K', '-',
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE)
        curl_stdout, curl_stderr = await curl_proc.communicate('\n'.join(curl_config).encode())
        if curl_proc.returncode != 0:
            raise DownloadError("LFS download failed.")

        for obj in lfs_objs:
            lfs_filepath, lfs_size = lfs_object_dict[obj['oid']]
            actual_size = lfs_filepath.stat().st_size
            if actual_size != lfs_size:
                msg = f"LFS file {lfs_filepath} expected size {lfs_size}, actual {actual_size}."
                raise DownloadError(msg)

    async def get_file(self, path):
        async with self.stream_repo_file(path) as response:
            return await response.aread()


def _find_files_in_list(path, file_list, name):
    """
    Scans a list of files (eg, from tar output) looking for instances
    of a specific filename.
    """
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
    headers = {'Private-Token': os.environ.get('GITLAB_PRIVATE_TOKEN', '')}


class GitLocalFileDownloader:
    def __init__(self, repo_path, version):
        self.repo_path = repo_path

    async def get_file(self, path):
        git_cmd = ['git', 'show', f'{self.version}:{path}']
        git_proc = await asyncio.create_subprocess_exec(
            *git_cmd, cwd=self.repo_path, stdout=asyncio.subprocess.PIPE)
        stdout, stderr = await git_proc.communicate()
        return stdout


class GitRev:
    """
    This class is the main entry point of the module, supplying asynchronous methods to
    intelligently download/access the contents of a remote git repo at a specific ref.
    """
    URL_REGEX = re.compile(r'(?:\w+:\/\/|git@)(?P<server>[\w.-]+)[:/](?P<repo_path>[\w/-]*)(?:\.git)?$')
    URL_DOWNLOADERS = [GitLabDownloader, GithubDownloader]
    FILE_REGEX = re.compile(r'file:\/\/(?P<repo_path>.+)$')

    def __init__(self, url, version):
        self.url = url
        self.version = version
        if match := self.URL_REGEX.match(url):
            # Recognized remote hosts (Github, GitLab)
            self.__dict__.update(match.groupdict())
            for dl_cls in self.URL_DOWNLOADERS:
                if dl_cls.SERVER_REGEX.match(self.server):
                    self.downloader = dl_cls(server=self.server,
                                             repo_path=self.repo_path,
                                             version=self.version)
                    break
        elif match := self.FILE_REGEX.match(url):
            # Repo on the local filesystem
            self.__dict__.update(match.groupdict())
            self.downloader = GitLocalFileDownloader(repo_path=self.repo_path,
                                                     version=version)
        else:
            raise DownloadError(f"Unable to download from {url}")

    @contextlib.asynccontextmanager
    async def tempdir_download(self):
        dirname = f"colcon-distro--{self.repo_path.replace('/', '-')}--"
        with TemporaryDirectory(prefix=dirname, dir="/var/tmp") as tempdir:
            await self.downloader.download_all_to(pathlib.Path(tempdir))
            yield tempdir

    async def version_hash_lookup(self):
        git_proc = await asyncio.create_subprocess_exec('git', 'ls-remote', self.url, self.version,
                                                        stdout=asyncio.subprocess.PIPE)
        git_output, git_stderr = await git_proc.communicate()
        if git_stderr:
            raise DownloadError(f"Unexpected error output from git ls-remote: {git_stderr}")
        if not git_output:
            raise DownloadError(f"Distro ref {self.version} could not be found in the git remote.")
        return git_output.split()[0].decode()
