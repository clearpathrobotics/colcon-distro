import argparse
import asyncio
import logging
import sanic
import yaml

from .config import add_config_args, get_config
from .database import Database
from .download import GitRev
from .model import Model
from .vendor.compress import Compress


app = sanic.Sanic(__name__)

# We deal in single requests; there's no advantage in having the client
# hold the connection open.
app.config.KEEP_ALIVE = False

# Requests are tiny and should arrive quickly.
app.config.REQUEST_TIMEOUT = 5

# In the worst case where nothing is cached, it can take a long time
# to generate a response; this is up from the default of 60 seconds.
app.config.RESPONSE_TIMEOUT = 300

# Compress responses with gzip or brotli as acceptable to the client.
Compress(app)

async def get_response_obj(dist, ref):
    repo_states_list = await app.model.get_set(dist, ref)
    def repo_states_items():
        for name, typename, url, version, packages in repo_states_list:
            repo_obj = {
                'type': typename,
                'url': url,
                'version': version,
                'packages': packages
            }
            yield name, repo_obj
    # Include the original request information in the response to facilitate using
    # this result with an import workflow (not yet implemented).
    return {
        'rosdistro': {
            'repository': app.model.config.distro.repository,
            'distribution': dist,
            'ref': ref
        },
        'repositories': dict(repo_states_items())
    }

@app.route("/get/<dist>/<ref:path>.yaml")
async def get_yaml(request, dist, ref):
    headers = {
        'Content-Disposition': f'attachment; filename={ref.replace("/", "-")}.yaml'
    }
    ro = await get_response_obj(dist, ref)
    return sanic.response.raw(
        yaml.dump(ro, sort_keys=False, encoding='utf-8'),
        headers=headers,
        content_type='application/yaml')

@app.route("/get/<dist>/<ref:path>.json")
async def get_json(request, dist, ref):
    headers = {
        'Content-Disposition': f'inline; name={ref.replace("/", "-")}.json'
    }
    ro = await get_response_obj(dist, ref)
    return sanic.response.json(ro, headers=headers)

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
    logging.getLogger("sanic.access").propagate = False
    logging.getLogger("sanic.root").propagate = False

    config = get_config(args)
    db = Database(config)
    app.model = Model(config, db)

    async def run_server():
        server = await app.create_server(
            host=args.host,
            port=args.port,
            return_asyncio_server=True
        )
        return await server.serve_forever()

    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        pass
