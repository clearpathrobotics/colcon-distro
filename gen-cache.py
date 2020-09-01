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


set_default_config_path(path="foo")

parser = ArgumentParser()
add_packages_arguments(parser)
args = parser.parse_args()
extensions = get_package_identification_extensions()



DIST_GIT = "http://gitlab.clearpathrobotics.com/sweng-infra/rosdistro_internal"
DIST_YAML_URL = "/raw/{}/indigo/distribution.yaml"
SNAPSHOT = "refs/snapshot/2.20.0/20200828212120"

output = subprocess.check_output(['git', 'ls-remote', DIST_GIT + '.git', SNAPSHOT], universal_newlines=True)
githash = output.split()[0]

dist_url = DIST_GIT + DIST_YAML_URL.format(githash)

resp = requests.get(dist_url)

y = yaml.safe_load(resp.text)

import asyncio
from download import GitRev
import httpx

from time import sleep

def get_repository_scanners():
    # Limits concurrent downloads.
    download_semaphore = asyncio.Semaphore(8)

    async def scan_repository(name, repo_data):
        src = repo_data['source']
        gr = GitRev(src['url'], src['version'])

        async with download_semaphore:
            async with gr.tempdir_download() as repo_dir:
                args.base_paths = [repo_dir]
                print(name, sorted([p.name for p in discover_packages(args, extensions)]))

    for repository_item in islice(y['repositories'].items(), 5):
        yield scan_repository(*repository_item)

async def scan_repositories():
    return await asyncio.gather(*get_repository_scanners(), return_exceptions=True)

for x in asyncio.run(scan_repositories()):
    if x: print(x)


import sys
sys.exit(0)

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

output = {}
for repository_name, repository_package_descriptors in scan_results:
    for package_descriptor in repository_package_descriptors:
        print(descriptor_output(package_descriptor))
