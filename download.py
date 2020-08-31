
import asyncio
import re
import logging

logger = logging.getLogger('download')
logger.setLevel(logging.INFO)


class GitTarballDownloader:
    URL_REGEX = re.compile('(?:\w+:\/\/|git@)(?P<server>[\w.-]+)[:/](?P<repo_path>[\w/-]*)(?:\.git)?$')

    @classmethod
    def from_url(cls, url):
        match = cls.URL_REGEX.match(url)
        if not match:
            raise ValueError(f"Unable to parse version control URL: {url}")
        gd = match.groupdict()
        if cls.SERVER_REGEX.match(gd['server']):
            return cls(**gd)
        return None

    def __init__(self, **args):
        self.args = args
    
    async def download_to(self, download_semaphore, http_client, version, download_dir):
        tarball_url = self.TARBALL_URL.format(version=version, **self.args)
        async with download_semaphore:
            response = await http_client.get(tarball_url)
        if response.status_code != 200:
            logger.error(f"Received HTTP {response.status_code} while fetching {tarball_url}")
            return False
        logger.info(f"Fetched {self.args['repo_path']}")
        tarproc = await asyncio.create_subprocess_exec('tar', '-xz', stdin=asyncio.subprocess.PIPE)
        await tarproc.communicate(input=response.content)
        logger.info(f"Extracted to {download_dir}")
        return True


class GithubDownloader(GitTarballDownloader):
    SERVER_REGEX = re.compile(r'^github\.com')
    TARBALL_URL = 'https://{server}/{repo_path}/archive/{version}.tar.gz'


class GitLabDownloader(GitTarballDownloader):
    SERVER_REGEX = re.compile(r'^gitlab\.')
    TARBALL_URL = 'http://{server}/{repo_path}/repository/archive.tar.gz?ref={version}'


downloaders = [
    GitLabDownloader,
    GithubDownloader
]

def downloader_for(url):
    for downloader in downloaders:
        d = downloader.from_url(url)
        if d:
            return d
    return None
