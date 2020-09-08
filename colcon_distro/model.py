

from colcon_core.package_discovery import discover_packages
from colcon_core.package_identification import get_package_identification_extensions

import argparse
import asyncio
import yaml

from .download import GitRev


# TODO: The early returns in this class are all inconsistent in terms of which fields come back
# from the repo_states tables, and also whether the package descriptors are serialized or not.

# TODO: Both methods should be futurized, so that if the same request comes in for something
# already in progress, we don't start working on it a second time.

class Model:
    def __init__(self, config, db):
        self.config = config
        self.db = db
        self.extensions = get_package_identification_extensions()

    async def get_set(self, name):
        # Check if we have it already in the database.
        if set_repo_states := await self.db.fetch_set(name):
            return set_repo_states

        # Now we need to start generating it. First access the distribution.yaml itself
        # so that we have the raw list of repo versions.
        distro_rev = GitRev(self.config.distro.repository, name)
        distro_rev.version = await distro_rev.version_hash_lookup()
        distro_rev.downloader.version = distro_rev.version
        yaml_str = await distro_rev.get_file(self.config.distro.distribution_file)
        distro_obj = yaml.safe_load(yaml_str)

        def _get_repo_states():
            for repo_name, repo_obj in distro_obj['repositories'].items():
                source = repo_obj['source']
                yield self.get_repo_state(repo_name, source['type'], source['url'], source['version'])

        repo_states = await asyncio.gather(*_get_repo_states())
        repo_state_ids = [repo_state_id for repo_state_id, _ in repo_states]
        await self.db.insert_set(name, repo_state_ids)
        return repo_states

    async def get_repo_state(self, name, typename, url, version):
        # Check if we already have this in the database.
        if repo_state := await self.db.fetch_repo_state(name, typename, url, version):
            return repo_state

        # If not, grab the source and find the package descriptors.
        gitrev = GitRev(url, version)
        async with gitrev.tempdir_download() as repo_dir:
            package_descriptors = discover_packages(self._get_discovery_args(repo_dir), self.extensions)

        # Insert it as a new row, and return that row's id.
        repo_state_id = await self.db.insert_repo_state(name, typename, url, version, package_descriptors)
        return repo_state_id, package_descriptors

    @staticmethod
    def _get_discovery_args(path):
        # See: https://github.com/colcon/colcon-core/issues/378
        return argparse.Namespace(base_paths=[path], ignore_user_meta=True,
                                  paths=None, metas=['./colcon.meta'])
