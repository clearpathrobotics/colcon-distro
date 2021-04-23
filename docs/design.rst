Design
======

The basic function of the distro server is to listen-for and service snapshot
requests. A snapshot will be a full dump (``yaml`` or ``json``) of the
``distribution.yaml`` repos, with each repo entry containing an array of serialized
PackageDescriptor_ objects corresponding to the packages discovered within.

.. _PackageDescriptor: https://github.com/colcon/colcon-core/blob/master/colcon_core/package_descriptor.py

For any given request, each repo might be at a frozen version (a tag or hash),
or it might be floating, on a branch. Branches need to be resolved to a latest-hash,
since all database entries in the cache are immutable. The easiest way to resolve
the branch is with ``git ls-remote``, however this requires that ``ssh-agent`` be
running to service SSH git URLs, so this should instead be done using host-specific
native APIs where the regular API token can be used.

Once the list of frozen repos is known, then it's a matter of:

#. Returning the cached entry, if that exists.

#. If it doesn't exist but is already being fetched, waiting and returning it when ready.

#. If it's not already being fetched, triggering it to be fetched.

This type of workload is highly parallel and a natural fit for `Python asyncio`_--- the
core functions for fetching and extracting repos are ``async``, and the webserver used
is Sanic_. Previous implementations used ``httpx`` and Python's internal ``tarfile``,
but this was found to be significantly slower and more fussy to set up than simply
shelling out to external ``curl`` and ``tar`` processes.

.. _Python asyncio: https://docs.python.org/3/library/asyncio.html
.. _Sanic: https://sanic.readthedocs.io/en/stable/
