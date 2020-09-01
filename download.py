import asyncio
from collections import defaultdict
import contextlib
import httpx
import re
import logging
import os
from tempfile import TemporaryDirectory
import urllib.parse

logger = logging.getLogger('download')
logger.setLevel(logging.INFO)


class DownloadError(Exception):
    pass


class CountedClient:
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
    http_client = CountedClient()
    headers = {}

    def __init__(self, **args):
        self.__dict__.update(args)
        self.repo_path_quoted = urllib.parse.quote(self.repo_path, safe='')

    async def stream_repo_tarball(self):
        tarball_url = self.TARBALL_URL.format(**self.__dict__)
        async with self.http_client.get() as client:
            async with client.stream('GET', tarball_url, headers=self.headers) as response:
                if response.status_code != 200:
                    raise DownloadError(f"Received HTTP {response.status_code} while fetching {tarball_url}")
                async for chunk in response.aiter_bytes():
                    yield chunk
        logger.info(f"Finished downloading {self.repo_path}")

    async def download_all_to(self, path):
        """
        Unlike the plain tarball downloader, this also unpacks the result, and can
        therefore do extra stuff like fetch submodules and LFS objects.
        """
        tar_proc = None
        async for chunk in self.stream_repo_tarball():
            # Lazy-start the tar process to avoid leaving it hanging
            # if the download fails to start.
            if not tar_proc:
                tar_proc = await asyncio.create_subprocess_exec('tar', '-xz', '--strip-components=1',
                        cwd=path, stdin=asyncio.subprocess.PIPE)
            tar_proc.stdin.write(chunk)
            await tar_proc.stdin.drain()
        tar_proc.stdin.close()
        await tar_proc.wait()


class GithubDownloader(GitTarballDownloader):
    SERVER_REGEX = re.compile(r'^github\.com')
    TARBALL_URL = 'https://{server}/{repo_path}/archive/{version}.tar.gz'


class GitLabDownloader(GitTarballDownloader):
    SERVER_REGEX = re.compile(r'^gitlab\.')
    TARBALL_URL = 'http://{server}/api/v4/projects/{repo_path_quoted}/repository/archive.tar.gz?sha={version}'
    headers = { 'PRIVATE-TOKEN': os.environ.get('GITLAB_PRIVATE_TOKEN', '') }


class GitRev:
    URL_REGEX = re.compile('(?:\w+:\/\/|git@)(?P<server>[\w.-]+)[:/](?P<repo_path>[\w/-]*)(?:\.git)?$')
    DOWNLOADERS = [GitLabDownloader, GithubDownloader]

    def __init__(self, url, version):
        match = self.URL_REGEX.match(url)
        if not match:
            raise DownloadError(f"Unable to parse version control URL: {url}")
        self.__dict__.update(match.groupdict())
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
            yield tempdir
