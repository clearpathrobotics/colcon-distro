import argparse
import asyncio
import logging

from .config import add_config_args, get_config
from .database import Database
from .download import GitRev
from .generator import scan_repositories
from .model import Model

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def get_arg_parser():
    ap = argparse.ArgumentParser()
    add_config_args(ap)
    ap.add_argument("ref", default=None, nargs="+")
    ap.add_argument("--debug", default=False, action='store_true')
    return ap


def main():
    args = get_arg_parser().parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    config = get_config(args)

    db = Database(config)
    model = Model(db)

    for ref in args.ref:
        distro_rev = GitRev(config.distro.repository, ref)
        distro_rev.version = asyncio.run(distro_rev.version_hash_lookup())
        distro_rev.downloader.version = distro_rev.version
        yaml_str = asyncio.run(distro_rev.get_file(config.distro.distribution_file))

        import yaml
        y = yaml.safe_load(yaml_str)

        async def do_scan():
            repo_state_ids = set()
            async for x in scan_repositories(y['repositories']):
                if isinstance(x, Exception):
                    logger.error(x)
                else:
                    repo_state_ids.add(await db.insert_repo_state(*x))
            await db.insert_set(ref, repo_state_ids)

        asyncio.run(do_scan())

        r = asyncio.run(db.fetch_set(ref))
        for x in r:
            print(x)
