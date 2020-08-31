from argparse import ArgumentParser
from colcon_core.dependency_descriptor import DependencyDescriptor
from colcon_core.package_discovery import discover_packages
from colcon_core.package_selection import add_arguments as add_packages_arguments
from colcon_core.package_identification import get_package_identification_extensions
from colcon_core.location import set_default_config_path

from itertools import islice
from pathlib import Path
import requests
import subprocess
from tempfile import TemporaryDirectory
import yaml

import logging

logging.basicConfig(level=logging.DEBUG)

DIST_GIT = "http://gitlab.clearpathrobotics.com/sweng-infra/rosdistro_internal"
DIST_YAML_URL = "/raw/{}/indigo/distribution.yaml"
SNAPSHOT = "refs/snapshot/2.20.0/20200828212120"

output = subprocess.check_output(['git', 'ls-remote', DIST_GIT + '.git', SNAPSHOT], universal_newlines=True)
githash = output.split()[0]

dist_url = DIST_GIT + DIST_YAML_URL.format(githash)

resp = requests.get(dist_url)

y = yaml.safe_load(resp.text)

from download import downloader_for
import httpx

async def do_downloads(working_dir):
    # Limits concurrent downloads.
    download_semaphore = asyncio.Semaphore(3)

    downloads = []
    async with httpx.AsyncClient() as http_client:
        for name, repo_data in islice(y['repositories'].items(), 20):
            url = repo_data['source']['url']
            version = repo_data['source']['version']

            d = downloader_for(url)
            downloads.append(d.download_to(download_semaphore, http_client, version, Path(working_dir, name)))
        await asyncio.gather(*downloads)

import asyncio
with TemporaryDirectory() as working_dir:
    asyncio.run(do_downloads(working_dir))



set_default_config_path(path="foo")

parser = ArgumentParser()
add_packages_arguments(parser)
args = parser.parse_args()

extensions = get_package_identification_extensions()
descriptors = discover_packages(args, extensions)

def dependency_str(dep):
    if isinstance(dep, DependencyDescriptor):
        return dep.name
    elif isinstance(dep, str):
        return dep
    raise ValueError("Unexpected dependency type.")

def descriptor_output(d):
    depends_output = {}
    for deptype in ('build', 'run', 'test'):
        if deptype in d.dependencies and d.dependencies[deptype]:
            depends_output[deptype] = sorted([dependency_str(dep) for dep in d.dependencies[deptype]])
    return {
        'type': d.type,
        'depends': depends_output
    }

output = {d.name: descriptor_output(d) for d in sorted(descriptors, key=lambda p: p.name)}

print(yaml.dump(output))
