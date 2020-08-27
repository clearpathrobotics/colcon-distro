from argparse import ArgumentParser
from colcon_core.package_discovery import discover_packages
from colcon_core.package_selection import add_arguments as add_packages_arguments
from colcon_core.package_identification import get_package_identification_extensions
from colcon_core.location import set_default_config_path

import yaml

set_default_config_path(path="foo")

parser = ArgumentParser()
add_packages_arguments(parser)
args = parser.parse_args()

extensions = get_package_identification_extensions()
descriptors = discover_packages(args, extensions)

def descriptor_output(d):
    depends_output = {}
    for deptype in ('build', 'run', 'test'):
        if deptype in d.dependencies and d.dependencies[deptype]:
            depends_output[deptype] = sorted([dep.name for dep in d.dependencies[deptype]])
    return {
        'type': d.type,
        'depends': depends_output
    }

output = {d.name: descriptor_output(d) for d in sorted(descriptors, key=lambda p: p.name)}

print(yaml.dump(output))
