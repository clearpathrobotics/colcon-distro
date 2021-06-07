from colcon_core.package_augmentation import \
    augment_packages, get_package_augmentation_extensions
from colcon_core.package_discovery import discover_packages
from colcon_core.package_identification import get_package_identification_extensions

import argparse

augmentation_extensions = None
identification_extensions = None


def discover_augmented_packages(repo_dir):
    """
    A lightweight wrapper around the colcon upstream operations of discovering
    packages in a particular filesystem path, and then augumenting them according
    to available plugins.
    """
    _load_extensions()

    descriptors = discover_packages(_get_discovery_args(repo_dir),
                                    identification_extensions)
    augment_packages(descriptors,
                     augmentation_extensions=augmentation_extensions)

    for descriptor in descriptors:
        descriptor.path = descriptor.path.relative_to(repo_dir)

    return descriptors


def _load_extensions():
    """ Lazy loading for colcon extensions. """
    global identification_extensions
    if identification_extensions is None:
        identification_extensions = get_package_identification_extensions()

    global augmentation_extensions
    if augmentation_extensions is None:
        augmentation_extensions = get_package_augmentation_extensions()


def _get_discovery_args(path):
    # See: https://github.com/colcon/colcon-core/issues/378
    argparse_ns = argparse.Namespace(
        base_paths=[path],
        ignore_user_meta=True,
        packages_ignore_regex=None,
        packages_ignore=None,
        paths=None,
        metas=['./colcon.meta'])
    return argparse_ns


# Small entry point here for isolated testing purposes. Example use:
#
#   git clone https://github.com/ros/roscpp_core
#   python3 -m colcon_distro.discovery ./roscpp_core
if __name__ == "__main__":  # pragma: no cover
    from sys import argv
    packages = discover_augmented_packages(argv[1])
    for p in packages:
        print(str(p) + "\n")
