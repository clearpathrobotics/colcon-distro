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

from download import downloader_for
import httpx


async def scan_repositories(working_dir):
    # Limits concurrent downloads.
    download_semaphore = asyncio.Semaphore(8)

    repository_scanners = []
    async with httpx.AsyncClient() as http_client:
        for repository_item in islice(y['repositories'].items(), 10):
            async def scan_repository(name, repo_data):
                async with download_semaphore:
                    tardata = await downloader_for(repo_data['source']['url']).download(http_client, repo_data['source']['version'])

                if not tardata:
                    return name, []
                repo_dir = Path(working_dir, name)
                repo_dir.mkdir()
                tarproc = await asyncio.create_subprocess_exec('tar', '-xz', cwd=repo_dir, stdin=asyncio.subprocess.PIPE)
                await tarproc.communicate(input=tardata)

                args.base_paths = [repo_dir]
                return name, discover_packages(args, extensions)

            repository_scanners.append(scan_repository(*repository_item))

    return await asyncio.gather(*repository_scanners)

import asyncio
with TemporaryDirectory() as working_dir:
    scan_results = asyncio.run(scan_repositories(working_dir))


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
