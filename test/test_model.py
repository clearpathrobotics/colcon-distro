
from colcon_distro.config import Config, DistroConfig
from colcon_distro.database import Database
from colcon_distro.model import Model

import asyncio
import logging
from pathlib import Path
from shutil import copytree
from subprocess import check_output
from tempfile import TemporaryDirectory

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class DummyConfig(Config):
    def __init__(self, config_dir):
        self.toml = None
        self.dir = config_dir
        self.distro_dir = self.dir / 'distro'
        self.distro_dir.mkdir()
        self._git('init')
        self._git('config', 'user.email', 'dummy@example.com')
        self._git('config', 'user.name', 'Dummy')
        self.distro = DistroConfig(
            repository='file://' + str(self.distro_dir),
            distributions=['banana'],
            branches=[],
            python_version=3)

    def add_state(self, state_name):
        state_dir = Path(__file__).parent / 'distro_states' / state_name
        copytree(state_dir, self.distro_dir, dirs_exist_ok=True)
        self._git('add', '.')
        self._git('commit', '-m', state_name)
        self._git('tag', state_name)

    def get_database_filepath(self):
        return self.dir / 'distro.db'

    def _git(self, *cmds):
        cmd = ('git',) + cmds
        logger.info('Invoking: %s', ' '.join(cmd))
        output = check_output(('git',) + cmds, cwd=self.distro_dir, universal_newlines=True).strip()
        if output:
            logger.info('Response: %s', output)


def test_model_github_hashes():
    with TemporaryDirectory() as tmpdir:
        config = DummyConfig(Path(tmpdir))
        config.add_state('roscpp-github-hashes')

        database = Database(config)
        model = Model(config, database)

        # This call will cause the repos in the distribution to be cached.
        descriptors = asyncio.run(model.get_set('banana', 'roscpp-github-hashes'))
        assert len(descriptors) == 16

        # This one will return from the database, so we want to confirm that it's an
        # identical result to the above.
        # TODO: Somehow confirm that it doesn't re-fetch anything. Check logging maybe?
        database2 = Database(config)
        model2 = Model(config, database2)
        descriptors2 = asyncio.run(model2.get_set('banana', 'roscpp-github-hashes'))
        print([d.name for d in descriptors])
        print([d.name for d in descriptors2])
        assert descriptors == descriptors2
