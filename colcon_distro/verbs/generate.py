from colcon_core.logging import colcon_logger
from colcon_core.verb import VerbExtensionPoint

import os
import yaml


class GenerateVerb(VerbExtensionPoint):
    def __init__(self):  # noqa: D107
        self.logger = colcon_logger.getChild(__name__)
        super().__init__()

    def add_arguments(self, *, parser):  # noqa: D102
        add = parser.add_argument
        add('--rosdistro', default=os.environ.get('ROSDISTRO', None),
            help='Name of rosdistro')
        add('--colcon-cache', default=os.environ.get('COLCON_CACHE_URL', None),
            help='Location to find the colcon-distro cache server.')
        add('--ref', default=None,
            help='Ref to search on the colcon-distro cache server.')
        add('--output-file', '-o', default='.workspace',
            help='Filename to save result to.')
        add('--deps', action='store_true', default=False,
            help='Include recursive deps of the specified packages.')
        add('pkgs', nargs='+',
            help='List of packages to include.')

    def main(self, *, context):  # noqa: D102
        args = context.args
        if not args.colcon_cache:
            self.logger.error("COLCON_CACHE_URL must be set or --colcon-cache argument passed.")
            return 1

        # Lazy import this so we don't pay the cost when the verb isn't invoked.
        from colcon_distro.generate import Generator, GeneratorError
        try:
            generator = Generator.from_url_cache(args.colcon_cache, args.rosdistro, args.ref)
        except GeneratorError as e:
            self.logger.error(f"Unable to generate workspace: {e}")
            return 1

        descriptors = generator.descriptor_set(*args.pkgs, deps=args.deps)

        output_dict = {
            'repositories': generator.repositories_spec_from_descriptors(descriptors),
            'dependencies': sorted(generator.dependencies_from_descriptors(descriptors))
        }
        with open(context.args.output_file, 'w') as f:
            f.write(yaml.dump(output_dict, sort_keys=False))
        return 0
