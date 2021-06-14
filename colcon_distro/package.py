
from contextlib import suppress
from colcon_core.dependency_descriptor import DependencyDescriptor
from colcon_core.package_descriptor import PackageDescriptor
from typing import Optional, Set


# TODO: This should be reworked as some kind of intermediate representation class that can
# be initialized _either_ from a PackageDescriptor or a JSON serialization, and can generate
# either also.

# TODO: This needs to consult the config for any allowlisted metadata that should be included
# in the serialization.

def dependency_str(dep):
    if isinstance(dep, DependencyDescriptor):
        return dep.name
    elif isinstance(dep, str):
        return dep
    raise ValueError("Unexpected dependency type.")


def descriptor_to_dict(pd: PackageDescriptor, metadata_inclusions: Optional[Set] = None):
    package_dict = {
        'name': pd.name,
        'path': str(pd.path),
        'type': pd.type,
    }

    package_dict['depends'] = {}
    for deptype in ('build', 'run', 'test'):
        if deptype in pd.dependencies and pd.dependencies[deptype]:
            dependency_strs = [dependency_str(dep) for dep in pd.dependencies[deptype]]
            dependency_strs.sort()
            package_dict['depends'][deptype] = dependency_strs

    # Only include the metadata dict if a set of inclusions has specifically been passed, since
    # including everything by default would end up with junk in some cases, like ros.catkin
    # packages that store a function object in there.
    if metadata_inclusions is not None:
        package_dict['metadata'] = {}
        for meta_name, meta_value in pd.metadata.items():
            if meta_name in metadata_inclusions:
                package_dict['metadata'][meta_name] = meta_value

    return package_dict


def descriptor_from_dict(d: dict):
    pd = PackageDescriptor(d['path'])
    pd.name = d['name']
    pd.type = d['type']
    with suppress(KeyError):
        pd.metadata = d['metadata']
    for deptype, deplist in d['depends'].items():
        for depname in deplist:
            pd.dependencies[deptype].add(DependencyDescriptor(depname))
    return pd
