Overview
========

The primary differences between this package and ``rosdistro_build_cache``
are:

* ``colcon-distro`` does not require ``package.xml`` files in order to locate
  packages in the distribution repos; instead it leverages colcon_'s plugin-based
  package discovery and augmentation mechanisms.
* ``colcon-distro`` does not use the ``release`` attributes of the
  ``distribution.yaml``, relying instead purely on the ``source`` attributes,
  making it suitable for building source workspaces during rolling development.
* ``colcon-distro`` remembers the state of the ``distribution.yaml`` when the
  ``version`` attributes have been frozen to hashes and the overall repo is
  tagged.
* ``colcon-distro`` is backed by a small SQLite database, and is an active server
  process rather than a script which generates one-off cache tarballs on each run.

In addition to the server process, two new verbs are added to ``colcon`` which
provide the client interface to the distro server:

* ``colcon generate`` replaces rosinstall_generator_, consuming the cached distro
  information and performing dependency resolution to assemble a list of repo/refs
  to clone. The output of this verb is compatible with vcstool_.
* ``colcon download`` provides an alternative to ``wstool``, ``vcs``, and similar
  tools, with the primary difference that it always downloads git repos as tarballs,
  and does so asynchronously under colcon's parallel execution framework.

.. _colcon: https://colcon.readthedocs.io/en/released/
.. _rosdistro library: https://github.com/ros-infrastructure/rosdistro/
.. _rosinstall_generator: https://github.com/ros-infrastructure/rosinstall_generator
.. _vcstool: https://github.com/dirk-thomas/vcstool
