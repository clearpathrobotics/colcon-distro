Reference
=========

The colcon-distro project is a client-server architecture, with mostly
separate components between the frontend and backend.

Backend
-------

The backend is the Sanic-based asynchronous server process which may be
queried for distro snapshot information at the ``/get`` endpoint. It
runs continuously and contains the logic to download packages by tarball,
inspect them for discovered packages, and save the discovered information
to a SQLite database. When a new snapshot request partially overlaps
with one that is already cached, the backend is smart enough to only
fetch the repo states it doesn't know about yet.

.. automodule:: colcon_distro.server

.. automodule:: colcon_distro.model

    .. autoclass:: Model
        :members:

.. automodule:: colcon_distro.repository_augmentation
    :members:

.. automodule:: colcon_distro.download

    .. autoclass:: GitRev
        :members:

    .. autoclass:: GitDownloader
        :members:

.. automodule:: colcon_distro.discovery
    :members:

.. automodule:: colcon_distro.database

    .. autoclass:: Connection
        :members:

    .. autoclass:: Database
        :members:

Frontend
--------

The frontend is :class:`colcon_distro.generate.Generator`, which is
synchronous and pulls a snapshot's JSON from a running backend instance,
transforming it into a spec file that can be consumed by something
like `vcstool`_. A command line interface to the generator is supplied
as a colcon verb ``colcon generate``, as well as a separate ``colcon
download``, which provides an alternative downloader that leverages
the same download system as the backend (rather than using an external
tool for this function).

.. _vcstool: https://github.com/dirk-thomas/vcstool

.. automodule:: colcon_distro.generate

    .. autoclass:: Generator
        :members:
        :undoc-members:

Common
------

.. automodule:: colcon_distro.repository_descriptor

    .. autoclass:: RepositoryDescriptor
        :members:
