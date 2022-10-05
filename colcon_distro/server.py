"""
server
======

This module has the ``main()`` that is the server process's entry point as
well as argument parsing and the rest of the Sanic interface, like
route handlers.
"""

import argparse
import asyncio
import logging
import re
import sanic
import yaml

from .config import add_config_args, get_config
from .database import Database
from .model import Model, ModelError
from .vendor.compress import Compress


app = sanic.Sanic("colcon-distro-server")

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


async def get_response_dict(model, dist, ref):
    try:
        repository_descriptors = await model.get_set(dist, ref)
    except ModelError as e:
        raise sanic.exceptions.NotFound(str(e))

    mi = app.ctx.model.config.get_metadata_inclusions()

    def repo_states_items():
        for desc in repository_descriptors:
            yield desc.name, desc.to_dict(mi)
    # Include the original request information in the response to facilitate using
    # this result with an import workflow (not yet implemented).
    return {
        'rosdistro': {
            'repository': app.ctx.model.config.distro.repository,
            'distribution': dist,
            'ref': ref
        },
        'repositories': dict(repo_states_items())
    }


@app.route("/get/<dist:string>/<path:path>")
async def get_ref(request, dist: str, path: str):
    if m := re.match(r"^(.*)\.(yaml|json)", path):
        ref, requested_format = m.groups()
        response_dict = await get_response_dict(app.ctx.model, dist, ref)
        response_filename = path.replace("/", "-")
        return response_fns[requested_format](response_filename, response_dict)
    raise sanic.exceptions.NotFound(f"Could not find {path}")


def yaml_response(filename: str, response: dict):
    headers = {
        'Content-Disposition': f'attachment; filename={filename}'
    }
    return sanic.response.raw(
        yaml.dump(response, sort_keys=False, encoding='utf-8'),
        headers=headers,
        content_type='application/yaml')


def json_response(filename: str, response: dict):
    headers = {
        'Content-Disposition': f'inline; name={filename}'
    }
    return sanic.response.json(response, headers=headers)


response_fns = {
    'yaml': yaml_response,
    'json': json_response
}


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
    app.ctx.model = Model(config, db)

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
