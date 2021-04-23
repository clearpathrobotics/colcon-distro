colcon-distro
=============

``colcon-distro`` extends the colcon_ build tool with a persistent distro
caching server which provides an efficient, extensible, snapshot-aware
alternative to the `rosdistro library`_'s native ``rosdistro_build_cache``
tool. The primary differences between the two tools is that:

* ``colcon-distro`` does not require ``package.xml`` files; instead it leverages
  colcon's plugin-based package discovery and augmentation mechanisms.
* ``colcon-distro`` does not use the ``release`` attributes of the
  ``distribution.yaml``, relying instead purely on the ``source`` attributes,
  making it suitable for building source workspaces during rolling development.
* ``colcon-distro`` remembers the state of the ``distribution.yaml`` when the
  ``version`` attributes have been frozen to hashes and the overall repo is
  tagged.
* ``colcon-distro`` is backed by a small SQLite database, and is an active server
  process rather than generating one-off tarballs on each run.

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


.. toctree::
   :maxdepth: 2
   :caption: Contents:

   design
   schema
   reference

Indices and tables
==================

* :ref:`genindex`
* :ref:`search`
