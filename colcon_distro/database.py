
import aiosqlite
import asyncio
import contextlib
import logging
import pkg_resources
import sqlite3
from typing import Iterable

from .repository_descriptor import RepositoryDescriptor


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# TODO: Would be interesting to profile what the overhead is of passing all these small
# sqlite operations to the other thread to do them "asyncronously". We could probably
# save a bunch of this is we did the insertions in batches.


class RepositoryNotFound(Exception):
    pass


class RepositorySetNotFound(Exception):
    pass


class Database:
    """
    This class is a low-level wrapper on the SQLite interface, supplying function wrappers
    for all needed queries, with some limited processing such as converting to results between
    RepositoryDescriptor objects and calling the methods on that class which handle JSON
    serialization around the packages field.
    """

    SCHEMA_SCRIPT = "schema.sql"
    PRAGMA_FOREIGN_KEYS = "PRAGMA foreign_keys=1"
    FETCH_SET_QUERY = """
    SELECT name, type, url, version, package_descriptors
    FROM repo_states
    JOIN set_repo_states ON repo_states.id = set_repo_states.repo_state_id
    JOIN sets ON set_repo_states.set_id == sets.id
    WHERE sets.dist = ? AND sets.ref = ?
    ORDER BY name"""
    FETCH_REPO_STATE_QUERY = """
    SELECT id, metadata, package_descriptors
    FROM repo_states
    WHERE name = ? AND type = ? AND url = ? AND version = ?"""
    INSERT_SET_QUERY = """
    INSERT INTO sets (dist, ref, last_updated) VALUES (?, ?, ?)"""
    INSERT_REPO_STATE_QUERY = """
    INSERT INTO repo_states (name, type, url, version, metadata, package_descriptors) VALUES (?, ?, ?, ?, ?, ?)"""
    INSERT_SET_REPO_STATES_QUERY = """
    INSERT INTO set_repo_states (set_id, repo_state_id) VALUES (?, ?)"""

    def __init__(self, config):
        filepath = config.get_database_filepath()
        if not filepath.exists():
            self.initialize(filepath)
        self.connection = Connection(filepath, self.connect_fn)

    def initialize(self, filepath: str) -> None:
        """
        Initializes a new empty database; this only ever happens at startup, so we
        just do it synchronously.
        """
        queries = pkg_resources.resource_string(__name__, self.SCHEMA_SCRIPT).decode()
        db = sqlite3.connect(filepath)
        db.executescript(queries)
        db.commit()
        db.close()

    async def connect_fn(self, db) -> None:
        """
        Callback function for anything we'd like to execute on a newly-opened database connection.
        """
        await db.execute(self.PRAGMA_FOREIGN_KEYS)

    async def fetch_set(self, dist_name: str, ref: str) -> Iterable[RepositoryDescriptor]:
        """
        Return either an iterable of RepositoryDescriptor objects if the set is in the
        database, or raise RepositorySetNotFound if it is not.
        """
        async with self.connection() as db:
            await db.execute(self.FETCH_SET_QUERY, (dist_name, ref))
            cursor = await db.execute(self.FETCH_SET_QUERY, (dist_name, ref))
            if all_data := await cursor.fetchall():
                repository_descriptors = []
                for data in all_data:
                    desc = RepositoryDescriptor()
                    desc.name = data[0]
                    desc.type = data[1]
                    desc.url = data[2]
                    desc.version = data[3]
                    desc.parse_packages_json(data[4])
                    repository_descriptors.append(desc)
                return repository_descriptors
            else:
                raise RepositorySetNotFound

    async def fetch_repo_state(self, desc: RepositoryDescriptor) -> None:
        """
        Uses the identity fields in the passed-in descriptor to search for it in the
        database. If found, the descriptor is populated with the row id and parsed
        PackageDescriptors; it not found RepositoryNotFound is raised.
        """
        query_args = desc.identity()
        assert query_args
        async with self.connection() as db:
            cursor = await db.execute(self.FETCH_REPO_STATE_QUERY, query_args)
            result = await cursor.fetchall()
            if result:
                repo_state_id, metadata_str, packages_str = result[0]
                desc.parse_metadata_json(metadata_str)
                desc.parse_packages_json(packages_str)
                desc.metadata['repo_state_id'] = repo_state_id
            else:
                raise RepositoryNotFound

    async def insert_repo_state(self, desc: RepositoryDescriptor) -> None:
        """
        Insert a repo state, setting the repo_state_id in the descriptor's metadata dict.
        If the row already exists, this query will fail due to db constraints.
        """
        async with self.connection() as db:
            query_args = (
                desc.name,
                desc.type,
                desc.url,
                desc.version,
                desc.metadata_json(),
                desc.packages_json()
            )
            cursor = await db.execute(self.INSERT_REPO_STATE_QUERY, query_args)
            desc.metadata['repo_state_id'] = cursor.lastrowid
            await db.commit()

    async def insert_set(self, dist_name: str, ref: str, repo_state_ids: Iterable[int]) -> None:
        """
        Insert a new set row from dist_name, name, and set of ids, all of which must
        exist in the repo states table or this query will fail due to db constraints.
        """
        async with self.connection() as db:
            cursor = await db.execute(self.INSERT_SET_QUERY, (dist_name, ref, None))
            set_id = cursor.lastrowid
            query_args = [(set_id, r) for r in repo_state_ids]
            await db.executemany(self.INSERT_SET_REPO_STATES_QUERY, query_args)
            await db.commit()


class Connection:
    """
    This manager class provides a few important capabilities to our sqlite connection.
    First, it mutexes it, so that commits from one coroutine don't get interleaved with
    queries from another, since sqlite has no built in concept of there being multiple
    clients or concurrent transactions going on. Second, it starts a background task
    which on cancelation closes the connection.

    A common instance of this class is used as a context manager. It yields the database
    handle and the caller must not store or continue to use it when the context has exited.
    """
    def __init__(self, filepath, connect_fn=None):
        # Lazy-initialize all async stuff so we don't get the wrong loop if this
        # object is constructed ahead of the loop starting.
        self._handle = None
        self._lock = None
        self._filepath = filepath
        self._connect_fn = connect_fn

    @contextlib.asynccontextmanager
    async def __call__(self):
        self._lock = self._lock or asyncio.Lock()
        async with self._lock:
            if not self._handle:
                logger.info(f"Opening database at {self._filepath}.")
                self._handle = await aiosqlite.connect(self._filepath)
                if self._connect_fn:
                    await self._connect_fn(self._handle)
                asyncio.create_task(self._closer())
            yield self._handle

    async def _closer(self):
        try:
            while True:
                await asyncio.sleep(60)
        finally:
            async with self._lock:
                logger.info("Closing database.")
                await self._handle.close()
                self._handle = None
