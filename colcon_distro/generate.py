from collections import defaultdict
import requests

from .package import descriptor_from_dict


class GeneratorError(RuntimeError):
    pass


class Generator:
    def __init__(self, repositories_dict):
        self.repositories = repositories_dict
        self.packages = dict(self._all_packages())
        self.requested_packages = {}

    @classmethod
    def from_url_cache(cls, cache_url: str, rosdistro: str, ref: str):
        if not cache_url:
            raise GeneratorError("The cache URL must be supplied.")
        if not (rosdistro and ref):
            raise GeneratorError("The rosdistro name and git ref must be supplied.")
        url = f'{cache_url}/get/{rosdistro}/{ref}.json'
        response = requests.get(url)
        if not response.ok:
            raise GeneratorError(
                f"Unable to fetch from {cache_url}, got HTTP {response.status_code}.")
        response_json = response.json()
        return cls(response_json['repositories'])

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

    def repositories_spec_from_descriptors(self, descriptors):
        repo_packages = defaultdict(dict)
        for package in descriptors:
            repo_packages[package.metadata['repo_name']][package.name] = {
                'path': str(package.path),
                'type': package.type
            }

        repositories_dict = {}
        for repo_name in sorted(repo_packages):
            cache_repo = self.repositories[repo_name]
            repositories_dict[repo_name] = {
                'url': cache_repo['url'],
                'type': cache_repo['type'],
                'version': cache_repo['version'],
                'packages': repo_packages[repo_name]
            }
        return repositories_dict

    def dependencies_from_descriptors(self, descriptors):
        deps = set()
        descriptor_names = set([desc.name for desc in descriptors])
        for descriptor in descriptors:
            for deptype, depset in descriptor.dependencies.items():
                for dep in depset:
                    if dep.name not in descriptor_names:
                        deps.add(dep.name)
        return deps
