import json
from pathlib import Path

from .package import descriptor_to_dict, descriptor_from_dict


class RepositoryDescriptor:
    __slots__ = (
        'path',
        'name',
        'type',
        'url',
        'version',
        'packages',
        'metadata',
    )

    def __init__(self):
        self.path = None
        self.name = None
        self.type = None
        self.url = None
        self.version = None
        self.packages = None
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

    def parse_metadata_json(self, metadata_json: str):
        """
        Parses the passed-in metadata_json string, and sets the metadata dict
        accordingly.
        """
        self.metadata = json.loads(metadata_json)

    def metadata_json(self):
        """
        Returns the json serialization of the metadata field.
        """
        assert self.metadata != None
        return json.dumps(self.metadata)

    def parse_packages_json(self, packages_json: str):
        """
        Parses the passed-in packages_json string, and sets the packages list
        accordingly.
        """
        packages_dicts = json.loads(packages_json)
        self.packages = [descriptor_from_dict(pd) for pd in packages_dicts]

    def packages_dicts(self):
        """
        Returns the packages field as a list of package dicts
        """
        assert self.packages != None
        return [descriptor_to_dict(pd) for pd in self.packages]

    def packages_json(self):
        """
        Returns the json serialization of the packages field.
        """
        return json.dumps(self.packages_dicts())

    def has_identity(self):
        """
        Object has "identity" if it has a name and source control info.
        """
        return self.name != None and self.type != None and \
            self.url != None and self.version != None

    def __eg__(self, other):
        return self.name == other.name and \
            self.type == other.type and \
            self.url == other.url and \
            self.version == other.version
