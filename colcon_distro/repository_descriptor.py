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

    def parse_packages_dicts(self, packages_dicts: str):
        """
        Parses the passed-in packages_dicts string, and sets the packages list
        to PackageDescriptor objects.
        """
        self.packages = [descriptor_from_dict(pd) for pd in packages_dicts]

    def packages_dicts(self):
        """
        Returns the packages field as a list of package dicts, ready to be
        serialized either to database or in a JSON HTTP response.
        """
        assert self.packages is not None
        return [descriptor_to_dict(pd) for pd in self.packages]

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
