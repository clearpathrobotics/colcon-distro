colcon-distro
=============

An experiment in using colcon's pluggable package discovery facility to
replaced rosdistro cache and rosinstall generator. More details on the wiki:

https://wiki.clearpathrobotics.com/display/~mpurvis/Next+Generation+Rosdistro+Caching

Example configuration:

```
[distro]
repository = "http://gitlab.clearpathrobotics.com/sweng-infra/rosdistro_internal.git"
distribution_file = "indigo/distribution.yaml"
branches = [ 'master', 'series-.+' ]

[database]
filename = "/var/tmp/distro.db"
```
