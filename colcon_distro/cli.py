import argparse
import asyncio
import logging

from .config import add_config_args, get_config
from .database import Database
from .download import GitRev
from .generator import scan_repositories

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

    for ref in args.ref:
        distro_rev = GitRev(config.distro.repository, ref)
        distro_rev.version = asyncio.run(distro_rev.version_hash_lookup())
        distro_rev.downloader.version = distro_rev.version
        yaml_str = asyncio.run(distro_rev.get_file(config.distro.distribution_file))

        import yaml
        y = yaml.safe_load(yaml_str)
        scan_results = []
        for x in asyncio.run(scan_repositories(y['repositories'])):
            if isinstance(x, Exception):
                print(x)
            else:
                scan_results.append(x)

        for res in scan_results:
            for package_descriptor in res[-1]:
                print(package_descriptor)
