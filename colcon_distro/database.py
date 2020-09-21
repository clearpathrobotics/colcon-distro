
import aiosqlite
import asyncio
import contextlib
import logging
import pkg_resources
import sqlite3


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# TODO: Would be interesting to profile what the overhead is of passing all these small
# sqlite operations to the other thread to do them "asyncronously". We could probably
# save a bunch of this is we did the insertions in batches.


class Database:
    SCHEMA_SCRIPT = "schema.sql"
    PRAGMA_FOREIGN_KEYS = "PRAGMA foreign_keys=1"
    FETCH_SET_QUERY = """
    SELECT repo_states.name, type, url, version, package_descriptors
    FROM repo_states
    JOIN set_repo_states ON repo_states.id = set_repo_states.repo_state_id
    JOIN sets ON set_repo_states.set_id == sets.id
    WHERE sets.dist = ? AND sets.name = ?
    ORDER BY repo_states.name"""
    FETCH_REPO_STATE_QUERY = """
    SELECT id, package_descriptors
    FROM repo_states
    WHERE name = ? AND type = ? AND url = ? AND version = ?"""
    INSERT_SET_QUERY = """
    INSERT INTO sets (dist, name, last_updated) VALUES (?, ?, ?)"""
    INSERT_REPO_STATE_QUERY = """
    INSERT INTO repo_states (name, type, url, version, package_descriptors) VALUES (?, ?, ?, ?, ?)"""
    INSERT_SET_REPO_STATES_QUERY = """
    INSERT INTO set_repo_states (set_id, repo_state_id) VALUES (?, ?)"""

    def __init__(self, config):
        filepath = config.get_database_filepath()
        if not filepath.exists():
            self.initialize(filepath)
        self.connection = Connection(filepath, self.connect_fn)

    def initialize(self, filepath):
        """
        Initializes a new empty database; this only ever happens at startup, so we
        just do it synchronously.
        """
        queries = pkg_resources.resource_string(__name__, self.SCHEMA_SCRIPT).decode()
        db = sqlite3.connect(filepath)
        db.executescript(queries)
        db.commit()
        db.close()

    async def connect_fn(self, db):
        """
        Callback function for anything we'd like to execute on a newly-opened database connection.
        """
        await db.execute(self.PRAGMA_FOREIGN_KEYS)

    async def fetch_set(self, dist_name, name):
        """
        Return either a full set of repo_state rows if the set is in the
        database, or the empty set if it is not.
        """
        async with self.connection() as db:
            await db.execute(self.FETCH_SET_QUERY, (dist_name, name))
            cursor = await db.execute(self.FETCH_SET_QUERY, (dist_name, name))
            return await cursor.fetchall()

    async def fetch_repo_state(self, name, typename, url, version):
        """
        Get a single repo state, returning a tuple that is the row id and json string,
        or None if the row is not found.
        """
        async with self.connection() as db:
            cursor = await db.execute(self.FETCH_REPO_STATE_QUERY, (name, typename, url, version))
            result = await cursor.fetchall()
            return result[0] if result else None

    async def insert_repo_state(self, name, typename, url, version, json_str):
        """
        Insert a repo state, returning the row id for it. If the row already exists,
        this query will fail due to db constraints.
        """
        async with self.connection() as db:
            cursor = await db.execute(self.INSERT_REPO_STATE_QUERY, (name, typename, url, version, json_str))
            row_id = cursor.lastrowid
            await db.commit()
        return row_id

    async def insert_set(self, dist_name, name, repo_state_ids):
        """
        Insert a new set row from dist_name, name, and set of ids, all of which must
        exist in the repo states table or this query will fail due to db constraints.
        """
        async with self.connection() as db:
            cursor = await db.execute(self.INSERT_SET_QUERY, (dist_name, name, None))
            set_id = cursor.lastrowid
            await db.executemany(self.INSERT_SET_REPO_STATES_QUERY, [(set_id, r) for r in repo_state_ids])
            await db.commit()


class Connection:
    """
    This manager class provides a few important capabilities to our sqlite connection.
    First, it mutexes it, so that commits from one coroutine don't get interleaved with
    queries from another, since sqlite has no built in concept of there being multiple
    clients or concurrent transactions going on. Second, it starts a background task
    which on cancelation closes the connection.
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
