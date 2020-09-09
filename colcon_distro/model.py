

from colcon_core.package_discovery import discover_packages
from colcon_core.package_identification import get_package_identification_extensions

import argparse
import asyncio
import json
import logging
import operator
import yaml

from .download import GitRev
from .package import descriptor_output


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# TODO: Both methods should be futurized, so that if the same request comes in for something
# already in progress, we don't start working on it a second time.

class Model:
    def __init__(self, config, db):
        self.config = config
        self.db = db
        self.extensions = get_package_identification_extensions()

    async def get_set(self, name):
        """
        Returns a list of repo state rows.
        """
        # Trim the ref prefix if included.
        if name.startswith("refs/"):
            name = name.split("refs/")[1]

        # Check if we have it already in the database, returning as-is if so. Unfortunately
        # we do have to rebuild the list to parse the json, as tuples are immutable.
        if set_repo_states := await self.db.fetch_set(name):
            logger.info(f"Returning cache for {name} from the database.")
            parsed_repo_states = []
            for repo_state in set_repo_states:
                parsed_repo_states.append(repo_state[0:-1] + (json.loads(repo_state[-1]),))
            return parsed_repo_states

        # Not in the database, so we need to start generating it. First access the
        # distribution.yaml itself so that we have the raw list of repo versions.
        distro_rev = GitRev(self.config.distro.repository, name)
        distro_rev.version = await distro_rev.version_hash_lookup()
        distro_rev.downloader.version = distro_rev.version
        yaml_str = await distro_rev.get_file(self.config.distro.distribution_file)
        distro_obj = yaml.safe_load(yaml_str)

        def _get_repo_states():
            """ Generate getter coroutines for all repo states. """
            for repo_name, repo_obj in distro_obj['repositories'].items():
                source = repo_obj['source']
                yield self.get_repo_state(repo_name, source['type'], source['url'], source['version'])

        logger.info(f"Preparing cache for {name}.")
        repo_states = await asyncio.gather(*_get_repo_states())

        repo_state_ids = [repo_state_tuple[0] for repo_state_tuple in repo_states]
        await self.db.insert_set(name, repo_state_ids)
        logger.info(f"Cache for {name} is now saved to the database")

        # Trim off the row_id values as they aren't part of what this function returns.
        repo_states = [repo_state_tuple[1:] for repo_state_tuple in repo_states]
        return repo_states

    async def get_repo_state(self, name, typename, url, version):
        """
        Given the search terms, should always return a tuple that is an ID to a database row
        where the repo state data is stored, and a Python object that is the JSON reprentation
        of the serialized PackageDescriptor list for that repo state.
        """
        # Check if we already have this in the database.
        if repo_state := await self.db.fetch_repo_state(name, typename, url, version):
            row_id, json_str = repo_state
            return row_id, name, typename, url, version, json.loads(json_str)

        # If not, grab the source and find the package descriptors.
        gitrev = GitRev(url, version)
        async with gitrev.tempdir_download() as repo_dir:
            descriptors = discover_packages(self._get_discovery_args(repo_dir), self.extensions)

        sorted_descriptors = sorted(descriptors, key=operator.attrgetter('name'))
        json_obj = [descriptor_output(d) for d in sorted_descriptors]

        # Insert it as a new row, and return that row's id.
        repo_state_args = (name, typename, url, version, json.dumps(json_obj))
        row_id = await self.db.insert_repo_state(*repo_state_args)
        return row_id, name, typename, url, version, json_obj

    @staticmethod
    def _get_discovery_args(path):
        # See: https://github.com/colcon/colcon-core/issues/378
        return argparse.Namespace(base_paths=[path], ignore_user_meta=True,
                                  paths=None, metas=['./colcon.meta'])
