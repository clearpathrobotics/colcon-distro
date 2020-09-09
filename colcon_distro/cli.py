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
    ap.add_argument("--verbose", default=False, action='store_true')
    return ap


def main():
    args = get_arg_parser().parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    config = get_config(args)
    db = Database(config)
    model = Model(config, db)

    for ref in args.ref:
        result = asyncio.run(model.get_set(ref))
        len_packages = sum([len(x[-1]) for x in result])
        if args.verbose:
            for repo_state in result:
                print(repo_state)
        print(f"Retrieved {len(result)} repo records, containing {len_packages} packages.")
