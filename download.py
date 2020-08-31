
import httpx
import re
import logging
import contextlib

logger = logging.getLogger('download')
logger.setLevel(logging.INFO)


class CountedClient(httpx.AsyncClient):
    def __init__(self):
        super().__init__()
        self.uses = 0


class ClientPool:
    def __init__(self):
        self.client_dict = {}

    @contextlib.asynccontextmanager
    async def get(self, server):
        if server not in self.client_dict:
            client = CountedClient()
            self.client_dict[server] = client
        else:
            client = self.client_dict[server]

        client.uses += 1
        yield client
        client.uses -= 1

        if client.uses == 0:
            del self.client_dict[server]
            await client.aclose()


class GitTarballDownloader:
    URL_REGEX = re.compile('(?:\w+:\/\/|git@)(?P<server>[\w.-]+)[:/](?P<repo_path>[\w/-]*)(?:\.git)?$')
    client_pool = ClientPool()

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
    
    async def download(self, version):
        tarball_url = self.TARBALL_URL.format(version=version, **self.args)
        async with self.client_pool.get(self.args['server']) as http_client:
            response = await http_client.get(tarball_url)
        if response.status_code != 200:
            # raise exception here instead?
            logger.error(f"Received HTTP {response.status_code} while fetching {tarball_url}")
            return False
        logger.info(f"Fetched {self.args['repo_path']}")
        return response.content


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
