from colcon_core.dependency_descriptor import DependencyDescriptor
from colcon_core.package_discovery import discover_packages
from colcon_core.package_identification import get_package_identification_extensions

import argparse
import asyncio
from itertools import islice
import logging

from .download import GitRev


args = argparse.Namespace(base_paths=['.'], ignore_user_meta=True, paths=None, metas=['./colcon.meta'])
extensions = get_package_identification_extensions()

async def scan_repositories(repositories, parallelism=8):
    # Limits concurrent downloads.
    download_semaphore = asyncio.Semaphore(parallelism)

    async def scan_repository(name, repo_data):
        src = repo_data['source']
        gr = GitRev(src['url'], src['version'])

        async with download_semaphore:
            async with gr.tempdir_download() as repo_dir:
                args.base_paths = [repo_dir]
                package_descriptors = discover_packages(args, extensions)
                return name, 'git', src['url'], src['version'], package_descriptors

    # Temporarily reduce the list so we don't hammer the servers during development.
    repositories = dict(islice(repositories.items(), 10))

    active = [scan_repository(*item) for item in repositories.items()]
    while active:
        finished, active = await asyncio.wait(active, return_when=asyncio.FIRST_COMPLETED)
        for task in finished:
            if task.exception():
                yield task.exception()
            else:
                yield task.result()

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
