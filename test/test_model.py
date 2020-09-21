

from colcon_distro.config import Config, DistroConfig
from colcon_distro.database import Database
from colcon_distro.model import Model

import asyncio
from pathlib import Path
from shutil import copytree
from subprocess import check_call
from tempfile import TemporaryDirectory


class DummyConfig(Config):
    def __init__(self, config_dir):
        self.toml = None
        self.dir = config_dir
        self.distro_dir = self.dir / 'distro'
        self.distro_dir.mkdir()
        check_call(['git', 'init'], cwd=self.distro_dir)
        self.distro = DistroConfig(
            repository='file://' + str(self.distro_dir),
            distributions=['banana'],
            branches=[],
            python_version=3)

    def add_state(self, state_name):
        state_dir = Path(__file__).parent / 'distro_states' / state_name
        copytree(state_dir, self.distro_dir, dirs_exist_ok=True)
        check_call(['git', 'add', '.'], cwd=self.distro_dir)
        check_call(['git', 'commit', '-m', state_name], cwd=self.distro_dir)
        check_call(['git', 'tag', state_name], cwd=self.distro_dir)

    def get_database_filepath(self):
        return self.dir / 'distro.db'


def test_model_github_hashes():
    with TemporaryDirectory() as tmpdir:
        config = DummyConfig(Path(tmpdir))
        config.add_state('roscpp-github-hashes')

        database = Database(config)
        model = Model(config, database)
        
        # This call will cause the repos in the distribution to be cached.
        repo_set_initial = asyncio.run(model.get_set('banana', 'roscpp-github-hashes'))
        assert len(repo_set_initial) == 16

        # This one will return from the database, so we want to confirm that it's an
        # identical result to the above.
        repo_set_second = asyncio.run(model.get_set('banana', 'roscpp-github-hashes'))
        assert repo_set_initial == repo_set_second
