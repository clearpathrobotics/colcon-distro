
import aiosqlite
import pkg_resources
import sqlite3


class Database:
    SCHEMA_SCRIPT = "schema.sql"
    PRAGMA_FOREIGN_KEYS = "PRAGMA foreign_keys=1"
    FETCH_SET_QUERY = """
    SELECT repo_states.name, type, url, version, package_descriptors
    FROM repo_states
    JOIN set_repo_states ON repo_states.id = set_repo_states.repo_state_id
    JOIN sets ON set_repo_states.set_id == sets.id
    WHERE sets.dist = ? AND sets.name = ?"""
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
        self.filepath = config.get_database_filepath()
        if not self.filepath.exists():
            self.initialize()

    def initialize(self):
        """
        Initializes a new empty database; this only ever happens at startup, so we
        just do it synchronously.
        """
        queries = pkg_resources.resource_string(__name__, self.SCHEMA_SCRIPT).decode()
        db = sqlite3.connect(self.filepath)
        db.executescript(queries)
        db.commit()
        db.close()

    async def fetch_set(self, dist_name, name):
        """
        Return either a full set of repo_state rows if the set is in the
        database, or the empty set if it is not.
        """
        async with aiosqlite.connect(self.filepath) as db:
            await db.execute(self.FETCH_SET_QUERY, (dist_name, name))
            cursor = await db.execute(self.FETCH_SET_QUERY, (dist_name, name))
            return await cursor.fetchall()

    async def fetch_repo_state(self, name, typename, url, version):
        """
        Get a single repo state, returning a tuple that is the row id and json string,
        or None if the row is not found.
        """
        async with aiosqlite.connect(self.filepath) as db:
            cursor = await db.execute(self.FETCH_REPO_STATE_QUERY, (name, typename, url, version))
            result = await cursor.fetchall()
            return result[0] if result else None

    async def insert_repo_state(self, name, typename, url, version, json_str):
        """
        Insert a repo state, returning the row id for it. If the row already exists,
        this query will fail due to db constraints.
        """
        async with aiosqlite.connect(self.filepath) as db:
            await db.execute(self.PRAGMA_FOREIGN_KEYS)
            cursor = await db.execute(self.INSERT_REPO_STATE_QUERY, (name, typename, url, version, json_str))
            row_id = cursor.lastrowid
            await db.commit()
        return row_id

    async def insert_set(self, dist_name, name, repo_state_ids):
        """
        Insert a new set row from dist_name, name, and set of ids, all of which must
        exist in the repo states table or this query will fail due to db constraints.
        """
        async with aiosqlite.connect(self.filepath) as db:
            await db.execute(self.PRAGMA_FOREIGN_KEYS)
            cursor = await db.execute(self.INSERT_SET_QUERY, (dist_name, name, None))
            set_id = cursor.lastrowid
            await db.executemany(self.INSERT_SET_REPO_STATES_QUERY, [(set_id, r) for r in repo_state_ids])
            await db.commit()
