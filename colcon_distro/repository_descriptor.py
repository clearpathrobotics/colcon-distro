"""
repository_descriptor
=====================

This module provides the RepositoryDescriptor class, which is a data container
for repository-level data.
"""
from colcon_core.package_descriptor import PackageDescriptor
from .package import descriptor_to_dict, descriptor_from_dict

from operator import itemgetter
from pathlib import Path
from typing import List, Optional, Set


class RepositoryDescriptor:
    """
    A descriptor for a repository at a moment in time. The identification items
    are the ``name``, ``type`` (eg ``git``), ``url``, and ``version`` (a tag or
    hash), all of which typically come from a rosdistro source entry. The
    remaining items are ``path``, which may be populated if the repo's contents
    are available on the filesystem (via checkout or tarball extraction);
    ``packages``, which is a list of PackageDescriptor objects; and ``metadata``,
    which is a dict that may be used for storing additional information.

    Similar to PackageDescriptor from colcon-core, this class is
    intentionally light on implementation. It is meant to be a data container
    that is passed around and acted on by other modules, rather than supplying
    its own suite of methods.
    """

    __slots__ = (
        'name',
        'type',
        'url',
        'version',
        'path',
        'packages',
        'metadata',
    )

    def __init__(self):
        self.path: Optional[Path] = None
        self.name: Optional[str] = None
        self.type: Optional[str] = None
        self.url: Optional[str] = None
        self.version: Optional[str] = None
        self.packages: Optional[Set[PackageDescriptor]] = None
        self.metadata = {}

    @classmethod
    def from_distro(cls, name: str, source_dict: dict):
        """
        Construct a descriptor from the name and source dict information
        that are typically in a rosdistro's distribution.yaml.
        """
        rd = cls()
        rd.name = name
        rd.type = source_dict['type']
        rd.url = source_dict['url']
        rd.version = source_dict['version']
        return rd

    def to_dict(self, metadata_inclusions=None):
        repo_dict = {
            'type': self.type,
            'url': self.url,
            'version': self.version,
            'packages': self.packages_dicts(metadata_inclusions)
        }
        if metadata_inclusions is not None:
            repo_dict['metadata'] = {}
            for meta_name, meta_value in self.metadata.items():
                if meta_name in metadata_inclusions:
                    repo_dict['metadata'][meta_name] = meta_value
        return repo_dict

    def parse_packages_dicts(self, packages_dicts: List[dict]):
        """
        Parses the passed-in list of package dicts, and sets the packages list
        to the corresponding PackageDescriptor objects.
        """
        self.packages = set(descriptor_from_dict(pd) for pd in packages_dicts)

    def packages_dicts(self, metadata_inclusions=None) -> List[dict]:
        """
        Returns the packages list as a list of package dicts, ready to be
        serialized either to database or in a JSON HTTP response.
        """
        assert self.packages is not None
        pds = [descriptor_to_dict(pd, metadata_inclusions) for pd in self.packages]
        pds.sort(key=itemgetter('name'))
        return pds

    def identity(self):
        """
        An identification tuple used for hashing and equality checks. Returns
        None if any of the required fields are unset.
        """
        identity_tuple = (self.name, self.type, self.url, self.version)
        return identity_tuple if all(identity_tuple) else None

    def __eq__(self, other):
        sid = self.identity()
        oid = other.identity()
        if sid and oid:
            return sid == oid
        else:
            raise NotImplementedError

    def __hash__(self):
        tup = self.identity()
        if tup:
            return hash(self.identity())
        else:
            raise NotImplementedError
