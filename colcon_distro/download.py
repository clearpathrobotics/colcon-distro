"""
download
========

This module provides classes related to efficiently accessing content from
remote repositories, including whole tarball downloads, individual files,
etc. Because there is no standard for this type of access, individual
implementations are present for Github, GitLab, and the local filesystem;
more could easily be added.
"""
import asyncio
from abc import ABC, abstractmethod
import contextlib
import httpx
import re
import logging
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Dict, Iterable, Optional
import urllib.parse

from .repository_descriptor import RepositoryDescriptor

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class DownloadError(RuntimeError):
    """
    General exception for download-related errors.
    """
    pass


class GitDownloader(ABC):
    """
    This abstract class supplies the interface for the host-specific implementations that
    are used by :class:`GitRev`.
    """

    @abstractmethod
    async def get_file(self, path: Path) -> bytes:
        """
        Returns contents of a single file from a git remote, using if possible
        a host-specific API that is faster than simply cloning the repo.

        :param path: path of file within repo to fetch.
        """
        pass

    @abstractmethod
    async def download_all_to(self, path: Path,
                              limit_paths: Optional[Iterable[Path]] = None) -> None:
        """
        Download contents of repository at the specified ref.

        :param path: location on filesystem to extract/copy/clone contents to.
        :param limit_paths: if supplied, only these paths within the repository will
            be extracted. This may be used to only copy certain packages for a workspace.
        """
        pass


class GitHostTarballDownloader(GitDownloader):
    """
    Generic tarball downloader which is lightly specialized in subclasses for specific hosts.
    """
    headers: Dict[str, str] = {}
    SERVER_REGEX: re.Pattern
    TARBALL_PATH: str
    BASE_URL :str = 'https://{server}'

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
            async with client.stream('GET', url, headers=self.headers, follow_redirects=True) as response:
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
            raise DownloadError(f"Archive download failed from {self.base_url}/{url_path}")
        filelist = [line.decode().split(os.path.sep, maxsplit=1)[1]
                    for line in tar_stdout.splitlines()]
        return filelist

    async def download_all_to(self, path, limit_paths=None):
        """
        Unlike the plain tarball downloader, this also unpacks the result, and can
        therefore do extra stuff like fetch submodules.
        """
        # Download and extract the main repo archive.
        await self.extract_tarball_to(path, limit_paths)
        logger.info(f"> {self.version} {self.repo_path} [archive]")

        # TODO: Scan for .gitmodules, and if found, recursively instantiate GitRevs for them
        # so that they also can be download_all_to'd the correct paths.

    async def get_file(self, path):
        async with self.stream_repo_file(path) as response:
            return await response.aread()


class GithubDownloader(GitHostTarballDownloader):
    SERVER_REGEX = re.compile(r'^github\.com')
    TARBALL_PATH = '{repo_path}/archive/{version}.tar.gz'
    FILE_PATH = '{repo_path}/raw/{version}/{path}'


class BitbucketDownloader(GitHostTarballDownloader):
    SERVER_REGEX = re.compile(r'^bitbucket\.org')
    TARBALL_PATH = '{repo_path}/get/{version}.tar.gz'
    FILE_PATH = '{repo_path}/raw/{version}/{path}'


class GitLabDownloader(GitHostTarballDownloader):
    SERVER_REGEX = re.compile(r'^gitlab\.')
    TARBALL_PATH = 'api/v4/projects/{repo_path_quoted}/repository/archive.tar.gz?sha={version}'
    FILE_PATH = 'api/v4/projects/{repo_path_quoted}/repository/files/{path_quoted}/raw?ref={version}'
    headers = {'Private-Token': os.environ.get('GITLAB_PRIVATE_TOKEN', '')}


class GitLocalFileDownloader(GitDownloader):
    def __init__(self, repo_path, version):
        self.repo_path = repo_path

    async def get_file(self, path):
        git_cmd = ['git', 'show', f'{self.version}:{path}']
        git_proc = await asyncio.create_subprocess_exec(
            *git_cmd, cwd=self.repo_path, stdout=asyncio.subprocess.PIPE)
        stdout, stderr = await git_proc.communicate()
        return stdout

    async def download_all_to(self, path, limit_paths=None):
        raise NotImplementedError


class GitRev:
    """
    This class supplies asynchronous methods to download/access the contents of a remote or
    local git repo at a specific ref, choosing an appropriate backend depending on the ``url``
    field of the repository descriptor that is passed into the constructor. The options at
    present are GitLab and Github, with some limited support for a local git clone (enough
    to use it as the rosdistro repo).
    """
    URL_REGEX = re.compile(r'(?:\w+:\/\/|git@)(?P<server>[\w.-]+)[:/](?P<repo_path>[\w/\.-]*?)(?:\.git)?$')
    URL_DOWNLOADERS = [GitLabDownloader, GithubDownloader, BitbucketDownloader]
    FILE_REGEX = re.compile(r'file:\/\/(?P<repo_path>.+)$')

    def __init__(self, repository_descriptor: RepositoryDescriptor):
        self.descriptor = repository_descriptor
        self.downloader: GitDownloader
        assert self.descriptor.url
        if match := self.URL_REGEX.match(self.descriptor.url):
            # Recognized remote hosts (Github, GitLab)
            self.server = match.group('server')
            self.repo_path = match.group('repo_path')
            for dl_cls in self.URL_DOWNLOADERS:
                if dl_cls.SERVER_REGEX.match(self.server):
                    self.downloader = dl_cls(
                        server=self.server, repo_path=self.repo_path, version=self.descriptor.version)
                    break
        elif match := self.FILE_REGEX.match(self.descriptor.url):
            # Repo on the local filesystem
            self.repo_path = match.group('repo_path')
            self.downloader = GitLocalFileDownloader(repo_path=self.repo_path,
                                                     version=self.descriptor.version)
        else:
            raise DownloadError(f"Unable to download from {self.descriptor.url}")

    @contextlib.asynccontextmanager
    async def tempdir_download(self):
        dirname = f"colcon-distro--{self.repo_path.replace('/', '-')}--"
        with TemporaryDirectory(prefix=dirname, dir="/var/tmp") as tempdir:
            if not hasattr(self, 'downloader'):
                raise DownloadError(f"No downloader available for {self.descriptor.url}")
            self.descriptor.path = Path(tempdir)
            await self.downloader.download_all_to(self.descriptor.path)
            yield
            self.descriptor.path = None

    async def version_hash_lookup(self):
        git_proc = await asyncio.create_subprocess_exec(
            'git', 'ls-remote', self.descriptor.url, self.descriptor.version,
            stdout=asyncio.subprocess.PIPE)
        git_output, git_stderr = await git_proc.communicate()
        if git_stderr:
            raise DownloadError(f"Unexpected error output from git ls-remote: {git_stderr}")
        if not git_output:
            raise DownloadError(f"Distro ref {self.descriptor.version} could not be found in the git remote.")
        return git_output.split()[0].decode()
