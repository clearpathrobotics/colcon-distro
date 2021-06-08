"""
repository_augmentation
=======================

The purpose of this module is to expose a colcon extension point for augmenting
:class:`colcon_distro.repository_descriptor.RepositoryDescriptor` objects with
additional metadata. Some possible uses for this could include hashes of all or
parts of the repository's contents, information about whether the repository
includes things like docs, tests, etc.
"""
import traceback

from colcon_core.logging import colcon_logger
from colcon_core.plugin_system import instantiate_extensions
from colcon_core.plugin_system import order_extensions_by_priority

from .repository_descriptor import RepositoryDescriptor


logger = colcon_logger.getChild(__name__)


class RepositoryAugmentationExtensionPoint:
    """
    The interface for repository augmentation extensions, which work
    similarly to package augmentation, but for repository-level
    metadata. Colcon doesn't normally concern itself with any source
    unit other than the package, which is why this lives here in
    colcon-distro (where repositories very much matter!) rather than
    in colcon-core with most of the other extension interfaces.
    """

    """The version of the repository augmentation extension interface."""
    EXTENSION_POINT_VERSION = '1.0'

    """The default priority of repository augmentation extensions."""
    PRIORITY = 100

    def augment_repository(
        self, path, metadata: dict, *, additional_argument_names=None
    ):
        """
        Augment the metadata dict with additional fields.
        The method is intended to be overridden in a subclass.
        :param path: Path to the repository.
        :param metadata: Dict on which to set metadata.
        """
        raise NotImplementedError


def get_repository_augmentation_extensions():
    """Get the repository augmentation extensions in priority order."""
    extensions = instantiate_extensions(__name__)
    for name, extension in extensions.items():
        extension.REPOSITORY_AUGMENTATION_NAME = name
    return order_extensions_by_priority(extensions)


def augment_repository(repository_descriptor: RepositoryDescriptor):
    """
    Augment the passed repository, populating its metadata dict according
    to available plugins.
    """
    logger.debug(f"augment_repository called for {repository_descriptor.path}")
    # apply extension augmentations in priority order
    extensions = get_repository_augmentation_extensions()
    for extension in extensions.values():
        try:
            extension.augment_repository(repository_descriptor)
        except Exception as e:  # noqa: F841
            # catch exceptions raised in completer extension
            exc = traceback.format_exc()
            logger.error(
                'Exception in repostory augmentation extension '
                f"'{extension.REPOSITORY_AUGMENTATION_NAME}': {e}\n{exc}")
            # skip failing extension, continue with next one
