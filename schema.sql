/*
The descriptor is a JSON serialization of a PackageDescriptor object,
including metadata which may have been added by package augmentation plugins.
*/
CREATE TABLE package_snapshots (
    id INT GENERATED ALWAYS AS IDENTITY,
    descriptor JSON
);

/*
Each row corresponds to a repository at a particular moment in time, identified
by the version field, which should be a hash or tag name in the git case. If
we end up supporting zipballs, wheels, or other direct-download assets, then
the version would be an identifying string would could be templated into the
URL.

The datetime should correspond to the creation time of the tag or commit, not
the creation time of this database record.
*/
CREATE TABLE repo_snapshots (
    id INT GENERATED ALWAYS AS IDENTITY,
    name VARCHAR(64),
    vcs VARCHAR(8),
    url VARCHAR(256),
    version VARCHAR(128),
    datetime TIMESTAMP WITH TIME ZONE,
    package_snapshot_ids INT[]
);

/*
Each ros corresponds to a snapshot of the rosdistro repo.
*/
CREATE TABLE snapshots (
    name VARCHAR(64),
    repo_snapshot_ids INT[]
);
