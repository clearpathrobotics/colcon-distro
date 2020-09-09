import argparse
import asyncio
import logging
import sanic

from .config import add_config_args, get_config
from .database import Database
from .download import GitRev
from .generator import scan_repositories
from .model import Model
from .vendor.compress import Compress


app = sanic.Sanic(__name__)
Compress(app)

@app.route("/get/<dist>/<ref:path>.json")
async def get(request, dist, ref):
    repo_states = await app.model.get_set(dist, ref)
    return sanic.response.json({
        'rosdistro': {
            'repository': app.model.config.distro.repository,
            'distribution': dist,
            'ref': ref
        },
        'cache': repo_states
    })


def get_arg_parser():
    ap = argparse.ArgumentParser()
    add_config_args(ap)
    ap.add_argument("--host", default='0.0.0.0')
    ap.add_argument("--port", default=8998)
    ap.add_argument("--debug", default=False, action='store_true')
    return ap


def main():
    args = get_arg_parser().parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    config = get_config(args)
    db = Database(config)
    app.model = Model(config, db)
    app.run(host=args.host, port=args.port)
