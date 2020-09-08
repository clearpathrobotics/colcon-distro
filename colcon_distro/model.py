


class Model:
    def __init__(self, db):
        self.db = db

    async def get_set(self, name):
        set_repo_states = await self.db.fetch_set(name)
