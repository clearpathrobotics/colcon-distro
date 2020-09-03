
import aiosqlite
import asyncio
import pkg_resources
import sqlite3


class Database:
    SCHEMA_SCRIPT = "schema.sql"
    FETCH_SET_QUERY = """
    SELECT name, vcs, url, version, package_descriptors
    FROM repo_states
    JOIN set_repo_states ON repo_states.id = set_repo_states.repo_state_id
    JOIN sets ON set_repo_states.set_id == sets.id
    WHERE sets.name = ?"""
    INSERT_SET_QUERY = """
    INSERT INTO sets (name, last_updated) VALUES (?, ?)"""
    INSERT_REPO_STATES_QUERY = """
    INSERT INTO repo_states (name, vcs, url, version, package_descriptors) VALUES (?, ?, ?, ?, ?)"""
    INSERT_SET_REPO_STATES_QUERY = """
    INSERT INTO set_repo_states (set_id, repo_state_id) VALUES (?, ?)"""

    def __init__(self, config):
        self.filepath = config.get_database_filepath()

        if not self.filepath.exists():
            self.initialize()

    def initialize(self):
        """
        Initialize a new empty database; this only ever happens at startup, so we
        just do it synchronously.
        """
        queries = pkg_resources.resource_string(__name__, self.SCHEMA_SCRIPT).decode()
        db = sqlite3.connect(self.filepath)
        db.executescript(queries)
        db.commit()
        db.close()

    async def fetch_set(self, set_name):
        async with aiosqlite.connect(self.filepath) as db:
            pass

    async def insert_set(self, set_name, repo_states):
        async with aiosqlite.connect(self.filepath) as db:
            pass
