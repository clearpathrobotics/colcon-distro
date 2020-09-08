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
    model = Model(config, db)

    for ref in args.ref:
        r = asyncio.run(model.get_set(ref))
        print(f"Retrieved {len(r)} repo records, containing X packages.")
