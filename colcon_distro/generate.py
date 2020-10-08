from collections import defaultdict
import os
import requests
import subprocess

from .package import descriptor_from_dict


class Generator:
    def __init__(self, repositories_dict):
        self.repositories = repositories_dict
        self.packages = dict(self._all_packages())
        self.requested_packages = {}

    @classmethod
    def from_url_cache(cls, cache_url, rosdistro, ref):
        # TODO: Add some error handling/recovery here.
        assert cache_url
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
