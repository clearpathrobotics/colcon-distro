import asyncio
import contextlib
import httpx
from io import StringIO
import re
import logging
import os
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
    def __init__(self):
        self.client = None
        self.count = 0

    @contextlib.asynccontextmanager
    async def get(self):
        if not self.client:
            self.client = httpx.AsyncClient()

        self.count += 1
        yield self.client
        self.count -= 1

        if self.count == 0:
            c = self.client
            self.client = None
            await c.aclose()


class GitTarballDownloader:
    """
    Generic tarball downloader which is specialized in subclasses for specific hosts.
    """
    http_client = CountedClient()
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
        async with self.http_client.get() as client:
            async with client.stream('GET', url, headers=self.headers) as response:
                if response.status_code != 200:
                    raise DownloadError(f"Received HTTP {response.status_code} while fetching {url}")
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
        url_path = self.FILE_PATH.format(path=path, **self.__dict__)
        async with self.stream_resource(url_path) as response:
            yield response

    async def download_all_to(self, path):
        """
        Unlike the plain tarball downloader, this also unpacks the result, and can
        therefore do extra stuff like fetch submodules and LFS objects.
        """
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
                line = await tar_proc.stdout.readline()
                while line:
                    tar_output.append(line)
                    line = await tar_proc.stdout.readline()

            await asyncio.wait([pass_stdin(), pass_stdout()])

        for line in tar_output:
            if line.endswith(b'.gitattributes\n'):
                # TODO: check for LFS files to also download.
                pass


class GithubDownloader(GitTarballDownloader):
    SERVER_REGEX = re.compile(r'^github\.com')
    BASE_URL = 'https://{server}'
    TARBALL_PATH = '{repo_path}/archive/{version}.tar.gz'


class GitLabDownloader(GitTarballDownloader):
    SERVER_REGEX = re.compile(r'^gitlab\.')
    BASE_URL = 'http://{server}'
    TARBALL_PATH = 'api/v4/projects/{repo_path_quoted}/repository/archive.tar.gz?sha={version}'
    FILE_PATH = '{repo_path}/raw/{version}/{path}'
    headers = { 'PRIVATE-TOKEN': os.environ.get('GITLAB_PRIVATE_TOKEN', '') }


class GitRev:
    """
    This class is the main entry point of the module, supplying asynchronous methods to
    intelligently download/access the contents of a remote git repo at a specific ref.
    """
    URL_REGEX = re.compile('(?:\w+:\/\/|git@)(?P<server>[\w.-]+)[:/](?P<repo_path>[\w/-]*)(?:\.git)?$')
    DOWNLOADERS = [GitLabDownloader, GithubDownloader]

    def __init__(self, url, version):
        match = self.URL_REGEX.match(url)
        if not match:
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
            await self.downloader.download_all_to(tempdir)
            logger.info(f"> {self.url} @ {self.version}")
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
