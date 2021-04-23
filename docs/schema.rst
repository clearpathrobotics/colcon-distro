Database Schema
===============

The database which backs the colcon distro server is meant to be simple
and disposable. Although this use case could benefit from native JSON
types such as are available in PostgreSQL or even from using a first
class document-oriented system like MongoDB, these systems are much
more involved to deploy, and going this route would considerably
complicate the ability to easily run a local instance of the distro
cache server, either for development purposes or as a user.

Raw Definition
--------------

.. literalinclude:: ../colcon_distro/schema.sql
   :language: sql
