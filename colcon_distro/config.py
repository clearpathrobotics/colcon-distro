from collections import namedtuple
import contextlib
from pathlib import Path
import toml


DistroConfig = namedtuple('DistroConfig', 'repository distributions branches')


class Config:
    DEFAULT_CONFIG_FILE="colcon-distro.toml"
    DEFAULT_DATABASE_FILE="distro.db"
    DIST_INDEX_YAML_FILE="index.yaml"

    def __init__(self, args):
        self.args = args
        config_file = Path(args.config_file or self.DEFAULT_CONFIG_FILE)
        if config_file.exists():
            with open(config_file, 'r') as f:
                self.toml = toml.load(f)
            self.distro = DistroConfig(**self.toml['distro'])
        else:
            self.toml = None

    def get_database_filepath(self):
        if self.args.database_file:
            return Path(self.args.database_file)
        with contextlib.suppress(KeyError):
            return Path(self.toml['database']['filename'])
        return Path(self.DEFAULT_DATABASE_FILE)


def add_config_args(argparser):
    argparser.add_argument("-c", "--config-file")
    argparser.add_argument("-f", "--database-file")


_config = None

def get_config(args):
    global _config
    if not _config:
        _config = Config(args)
    return _config
