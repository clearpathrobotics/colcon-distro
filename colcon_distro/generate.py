from colcon_core.logging import colcon_logger
from colcon_core.verb import VerbExtensionPoint

from collections import defaultdict
import os
import pathlib
import requests
import subprocess
import yaml

from .package import descriptor_from_dict


class Generator:
    def __init__(self, repositories_dict):
        self.repositories = repositories_dict
        self.packages = dict(self._all_packages())
        self.requested_packages = {}

    @classmethod
    def from_url_cache(cls, cache_url, rosdistro, ref):
        # TODO: Add some error handling/recovery here.
        url = f'{cache_url}/get/{rosdistro}/{ref}.json'
        return cls(requests.get(url).json()['repositories'])

    def _all_packages(self):
        for repo_name, repo_dict in self.repositories.items():
            for package_dict in repo_dict['packages']:
                pd = descriptor_from_dict(package_dict)
                pd.metadata['repo_name'] = repo_name
                yield pd.name, pd

    def descriptor_set(self, *pkg_names, deps=False):
        packages = set()
        for pkg_name in pkg_names:
            packages.add(self.packages[pkg_name])
        if deps:
            deps_packages = set()
            for package in packages:
                for depname in package.get_recursive_dependencies(self.packages.values()):
                    deps_packages.add(self.packages[depname])
            packages |= deps_packages
        return packages

    def repo_spec_from_descriptors(self, descriptors):
        # Build up a dict which maps each repo name to a dict of a the packages to their
        # paths within the repo (info from the descriptor metadata).
        repo_package_paths = defaultdict(dict)
        for package in descriptors:
            repo_package_paths[package.metadata['repo_name']][package.name] = str(package.path)

        # This dict becomes the final generated yaml.
        return_dict = {}
        for repo_name, package_paths in repo_package_paths.items():
            cache_repo = self.repositories[repo_name]
            return_dict[repo_name] = {
                'url': cache_repo['url'],
                'type': cache_repo['type'],
                'version': cache_repo['version'],
                'package_paths': package_paths
            }
        return return_dict

    def outstanding_dependencies(self, descriptors):
        deps = set()
        descriptor_names = set([desc.name for desc in descriptors])
        for descriptor in descriptors:
            for deptype, depset in descriptor.dependencies.items():
                for dep in depset:
                    if dep.name not in descriptor_names:
                        deps.add(dep)
        return deps


class GenerateVerb(VerbExtensionPoint):
    def __init__(self):  # noqa: D107
        self.logger = colcon_logger.getChild(__name__)
        super().__init__()

    def add_arguments(self, *, parser):  # noqa: D102
        parser.add_argument('--rosdistro', default=os.environ.get('ROSDISTRO', None),
            help='Name of rosdistro')
        parser.add_argument('--colcon-cache', default=os.environ.get('COLCON_CACHE_URL', None),
            help='Location to find the colcon-distro cache server.')
        parser.add_argument('--ref', default=None,
            help='Ref to search on the colcon-distro cache server.')
        parser.add_argument('--repos-file', '-r', default='.repos',
            help='Filename to save result to.')
        parser.add_argument('--deps-file', '-d', default='.deps',
            help='Filename to save list of outstanding dependencies to.')
        parser.add_argument('--deps', action='store_true', default=False,
            help='Include recursive deps of the specified packages.')
        parser.add_argument('pkgs', nargs='+',
            help='List of packages to include.')

    def main(self, *, context):  # noqa: D102
        args = context.args
        if not args.colcon_cache:
            self.logger.error("COLCON_CACHE_URL must be set or --colcon-cache argument passed.")
            return 1

        generator = Generator.from_url_cache(args.colcon_cache, args.rosdistro, args.ref)
        descriptors = generator.descriptor_set(*args.pkgs, deps=args.deps)

        spec_dict = generator.repo_spec_from_descriptors(descriptors)
        with open(context.args.repos_file, 'w') as f:
            f.write(yaml.dump({'repositories': spec_dict}))

        outstanding_deps = generator.outstanding_dependencies(descriptors)
        with open(context.args.deps_file, 'w') as f:
            for dep in sorted(outstanding_deps):
                f.write(f'{dep.name}\n')

        return 0
