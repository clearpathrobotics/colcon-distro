

from colcon_core.package_discovery import discover_packages
from colcon_core.package_identification import get_package_identification_extensions

import argparse
import asyncio
import json
import logging
import operator
import yaml

from .download import GitRev
from .package import descriptor_to_dict


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ModelError(Exception):
    """
    General exception for Model-related errors.
    """
    pass

class ModelInternalError(ModelError):
    """
    Exception for errors which are the result of bugs, for example database
    queries which fail due to consistency checks.
    """
    pass

# TODO: It would be great to support a distro that's just a directory of files or a locally-
# modified checkout, rather than needing to be on a known git host. This may require pulling
# some of that logic into a dedicated Distro class.

class Model:
    def __init__(self, config, db):
        self.config = config
        self.db = db
        self.extensions = get_package_identification_extensions()
        self.in_progress = {}

        # Limit how much work we try to do at once.
        self.semaphore = None

    def remember_progress(fn):
        """
        This decorator memoizes the coroutines below by wrapping them in futures and storing
        the result in a dictionary keyed to their name and arguments. The dict entry is cleared
        as soon as the future completes because at that point the content is in the database
        and would be retrieved from there anyway on successive calls.

        The idea here is that if multiple calls for the same (or overlapping) snapshots come in
        concurrently, we don't do the same work twice. And more importantly, we don't violate
        uniqueness constraints in the database by inserting the same results multiple times.
        """
        async def wrapper(self, *args):
            ident = (fn.__name__, *args)
            async def _initial():
                self.in_progress[ident] = asyncio.ensure_future(fn(self, *args))
                try:
                    return await self.in_progress[ident]
                finally:
                    del self.in_progress[ident]
            return await (self.in_progress.get(ident) or _initial())
        return wrapper

    @remember_progress
    async def get_set(self, dist_name, name):
        """
        Returns a set of repo state rows, by fetching them from the database if possible,
        and falling back to building it up manually if required, after which it is saved
        in the database and returned.
        """
        # Trim the ref prefix if included.
        if name.startswith("refs/"):
            name = name.split("refs/")[1]

        # Check if we have it already in the database, returning as-is if so. Unfortunately
        # we do have to rebuild the list to parse the json, as tuples are immutable.
        if set_repo_states := await self.db.fetch_set(dist_name, name):
            logger.info(f"Returning cache for {dist_name}:{name} from the database.")
            parsed_repo_states = []
            for repo_state in set_repo_states:
                parsed_repo_states.append(repo_state[0:-1] + (json.loads(repo_state[-1]),))
            return parsed_repo_states

        # Not in the database, so we need to start generating it. First access the
        # distribution.yaml itself so that we have the raw list of repo versions.
        distro_rev = GitRev(self.config.distro.repository, name)
        distro_rev.version = await distro_rev.version_hash_lookup()
        distro_rev.downloader.version = distro_rev.version
        index_yaml_str = await distro_rev.get_file(self.config.DIST_INDEX_YAML_FILE)
        index_obj = yaml.safe_load(index_yaml_str)

        if dist_name in index_obj['distributions']:
            dist_file_path = index_obj['distributions'][dist_name]['distribution'][0]
        else:
            raise ModelError("Unknown distro [{dist_name}] specified.")
        distro_obj = yaml.safe_load(await distro_rev.get_file(dist_file_path))

        def _get_repo_states():
            """ Generate getter coroutines for all repo states. """
            for repo_name, repo_obj in distro_obj['repositories'].items():
                source = repo_obj['source']
                yield self.get_repo_state(repo_name, source['type'], source['url'], source['version'])

        logger.info(f"Preparing cache for {dist_name}:{name}.")
        repo_states = await asyncio.gather(*_get_repo_states())

        repo_state_ids = [repo_state_tuple[0] for repo_state_tuple in repo_states]
        await self.db.insert_set(dist_name, name, repo_state_ids)
        logger.info(f"Cache for {dist_name}:{name} is now saved to the database")

        # Trim off the row_id values as they aren't part of what this function returns.
        repo_states = [repo_state_tuple[1:] for repo_state_tuple in repo_states]
        return repo_states

    @remember_progress
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

        # If not, grab the source and find the package descriptors, modifying
        # each so the path is relative to the repo rather than absolute.
        self.semaphore = self.semaphore or asyncio.Semaphore(self.config.get_parallelism())
        async with self.semaphore:
            gitrev = GitRev(url, version)
            async with gitrev.tempdir_download() as repo_dir:
                descriptors = discover_packages(self._get_discovery_args(repo_dir), self.extensions)
                for descriptor in descriptors:
                    descriptor.path = descriptor.path.relative_to(repo_dir)

        if not descriptors:
            raise ModelError(f"No packages discovered in {url}.")

        sorted_descriptors = sorted(descriptors, key=operator.attrgetter('name'))
        json_obj = [descriptor_to_dict(d) for d in sorted_descriptors]

        # Insert it as a new row, and return that row's id.
        repo_state_args = (name, typename, url, version, json.dumps(json_obj))
        row_id = await self.db.insert_repo_state(*repo_state_args)
        return row_id, name, typename, url, version, json_obj

    @staticmethod
    def _get_discovery_args(path):
        # See: https://github.com/colcon/colcon-core/issues/378
        return argparse.Namespace(base_paths=[path], ignore_user_meta=True,
                                  paths=None, metas=['./colcon.meta'])
