
from colcon_core.dependency_descriptor import DependencyDescriptor


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


def descriptor_output(d):
    depends_output = {}
    for deptype in ('build', 'run', 'test'):
        if deptype in d.dependencies and d.dependencies[deptype]:
            depends_output[deptype] = sorted([dependency_str(dep) for dep in d.dependencies[deptype]])
    return {
        'name': d.name,
        'type': d.type,
        'depends': depends_output
    }