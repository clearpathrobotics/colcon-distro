colcon-distro
=============

An experiment in using colcon's pluggable package discovery facility to
replace rosdistro cache and rosinstall generator.

Docs: https://colcon-distro.readthedocs.io

Example configuration:

```
[distro]
repository = "https://github.com/clearpathrobotics/rosdistro-snapshots"
distributions = ['noetic', 'rolling']

[database]
filename = "/var/tmp/distro.db"
```

You can also reference a local clone of rosdistro:

```
[distro]
repository = "file:///home/administrator/rosdistro_internal"
distributions = [ 'noetic' ]
```

You can also specify augmented package- and repository descriptor metadata to include, with:

```
[cache]
metadata_inclusions = [ 'narhash' ]
```

This will have no effect unless [colcon-nix][cn] is also installed in the same environment,
as it includes the extensions to actually populate that metadata field during colcon's
package augmentation phase.

[cn]: https://github.com/clearpathrobotics/colcon-nix
