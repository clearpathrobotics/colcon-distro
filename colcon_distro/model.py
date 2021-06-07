import asyncio
import functools
import json
import logging
import operator
import yaml

from .database import RepositoryNotFound, RepositorySetNotFound
from .discovery import discover_augmented_packages
from .download import GitRev
from .package import descriptor_to_dict
from .repository_augmentation import augment_repository
from .repository_descriptor import RepositoryDescriptor


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
    """
    This class provides the high level interface which may be queried for repo sets.

    Under the hood, it manages persistence via the database, but also sends work to
    be done and pauses requests for which the work is already in progress.
    """

    def __init__(self, config, db):
        self.config = config
        self.db = db
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

        @functools.wraps(fn)
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
    async def get_set(self, dist_name, ref):
        """
        Returns a set of repository descriptors, by fetching them from the database if possible,
        and falling back to building up manually if required, after which it is saved
        in the database and returned.

        :param: dist_name name of the distribution (eg, noetic)
        :param: ref version control reference to fetch (currently only frozen tags and
            snapshots are supported).
        """
        # Trim the ref prefix if included.
        if ref.startswith("refs/"):
            ref = ref.split("refs/")[1]

        # Check if we have it already in the database, returning as-is if so. Unfortunately
        # we do have to rebuild the list to parse the json, as tuples are immutable.
        try:
            repository_descriptors = await self.db.fetch_set(dist_name, ref)
            logger.info(f"Returning cache for {dist_name}:{ref} from the database.")
        except RepositorySetNotFound:
            # Not in the database, so we need to start generating it. First access the
            # distribution.yaml itself so that we have the raw list of repo versions.
            distro_descriptor = RepositoryDescriptor()
            distro_descriptor.url = self.config.distro.repository
            distro_descriptor.type = 'git'
            distro_descriptor.version = ref
            distro_rev = GitRev(distro_descriptor)
            distro_rev.version = await distro_rev.version_hash_lookup()
            distro_rev.downloader.version = distro_rev.version
            index_yaml_str = await distro_rev.downloader.get_file(self.config.DIST_INDEX_YAML_FILE)
            index_dict = yaml.safe_load(index_yaml_str)

            if dist_name in index_dict['distributions']:
                dist_file_path = index_dict['distributions'][dist_name]['distribution'][0]
            else:
                raise ModelError("Unknown distro [{dist_name}] specified.")
            distro_dict = yaml.safe_load(await distro_rev.downloader.get_file(dist_file_path))

            def _get_repo_states():
                """ Generate getter coroutines for all repo states. """
                for repo_name, repo_dict in distro_dict['repositories'].items():
                    desc = RepositoryDescriptor.from_distro(repo_name, repo_dict['source'])
                    yield self.get_repo_state(desc)

            logger.info(f"Preparing cache for {dist_name}:{ref}.")
            repository_descriptors = await asyncio.gather(*_get_repo_states())

            repo_state_ids = [desc.metadata['repo_state_id'] for desc in repository_descriptors]
            await self.db.insert_set(dist_name, ref, repo_state_ids)
            logger.info(f"Cache for {dist_name}:{ref} is now saved to the database")
        return repository_descriptors

    @remember_progress
    async def get_repo_state(self, repository_descriptor):
        """
        Populates the passed repository_descriptor with PackageDescriptor instances
        in the packages set, and a repo_state_id field in the metadata dict. This may happen
        because all of the information was in the cache, or some or all of it may have
        to have been pulled from the original source.
        """

        # The descriptor passed must have name and source info.
        assert repository_descriptor.has_identity()

        # Check if we already have this in the database.
        try:
            await self.db.fetch_repo_state(repository_descriptor)
        except RepositoryNotFound:
            # If not, grab the source and find the package descriptors, modifying
            # each so the path is relative to the repo rather than absolute.
            self.semaphore = self.semaphore or asyncio.Semaphore(self.config.get_parallelism())
            async with self.semaphore:
                async with GitRev(repository_descriptor).tempdir_download():
                    repository_descriptor.packages = \
                        discover_augmented_packages(repository_descriptor.path)
                    augment_repository(repository_descriptor)

            if not repository_descriptor.packages:
                raise ModelError(f"No packages discovered in {repository_descriptor.url}.")

            # Insert it as a new row, which will set the repo_state_id metadata on it.
            await self.db.insert_repo_state(repository_descriptor)
        return repository_descriptor
