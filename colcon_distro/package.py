
from colcon_core.dependency_descriptor import DependencyDescriptor
from colcon_core.package_descriptor import PackageDescriptor


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


def descriptor_to_dict(pd: PackageDescriptor):
    depends_output = {}
    for deptype in ('build', 'run', 'test'):
        if deptype in pd.dependencies and pd.dependencies[deptype]:
            dependency_strs = [dependency_str(dep) for dep in pd.dependencies[deptype]]
            dependency_strs.sort()
            depends_output[deptype] = dependency_strs
    return {
        'name': pd.name,
        'path': str(pd.path),
        'type': pd.type,
        'depends': depends_output
    }


def descriptor_from_dict(d: dict):
    pd = PackageDescriptor(d['path'])
    pd.name = d['name']
    pd.type = d['type']
    for deptype, deplist in d['depends'].items():
        for depname in deplist:
            pd.dependencies[deptype].add(DependencyDescriptor(depname))
    return pd
