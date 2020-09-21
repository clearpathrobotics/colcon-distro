colcon-distro
=============

An experiment in using colcon's pluggable package discovery facility to
replace rosdistro cache and rosinstall generator. More details on the wiki:

https://wiki.clearpathrobotics.com/display/~mpurvis/Next+Generation+Rosdistro+Caching

Example configuration:

```
[distro]
repository = "http://gitlab.clearpathrobotics.com/sweng-infra/rosdistro_internal.git"
distributions = [ 'indigo' ]
branches = [ 'master', 'series-.+' ]

[database]
filename = "/var/tmp/distro.db"
```

You can also reference a local clone of rosdistro:

```
[distro]
repository = "file:///home/administrator/rosdistro_internal"
distributions = [ 'indigo' ]
```

Note though that if you want to use snapshots from the GitLab instance, they will need
to be manually fetched, as `git clone` won't include them by default:

```
git fetch origin +refs/snapshot/*:refs/snapshot/* | tail
```
