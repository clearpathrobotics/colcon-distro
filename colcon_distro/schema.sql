PRAGMA foreign_keys = ON;

/*
Each row corresponds to a repository at a particular moment in time, identified
by the version field, which should be a hash or tag name in the git case. If
we end up supporting zipballs, wheels, or other direct-download assets, then
the version would be an identifying string would could be templated into the
URL.

The descriptors is a JSON array of PackageDescriptor object serializations,
including metadata which may have been added by package augmentation plugins.

Branch/sequence information is intended to go in a separate table as needed
later on, eg a repo_branches table which contains pointers to repo_states
corresponding to the branches at particular points in time. Such a change could
also incorporate breaking off the static repo information from this table.

If needed, the package_descriptors could go to a separate many-many table, but
this would be purely a deduplication for disk savings; not worth the complexity
in the short term.
*/
CREATE TABLE repo_states (
    id INTEGER PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    type VARCHAR(4) NOT NULL,
    url VARCHAR(256) NOT NULL,
    version VARCHAR(40) NOT NULL,
    package_descriptors TEXT NOT NULL
);

CREATE UNIQUE INDEX repo_state_index ON repo_states(name, type, url, version);

/*
Each repo set corresponds to a moment in time for the distro repo. If this is an
immutable point such as a tag or snapshot of frozen/tagged versions, then the
last_updated field should be NULL to indicate that no updates are necessary.

If the name is a branch and contains unfrozen versions, the last_updated field
should the time that it was last validated, and the corresponding repo_states rows
should still be hashes, not branch names.
*/
CREATE TABLE sets (
    id INTEGER PRIMARY KEY,
    dist VARCHAR(16) NOT NULL,
    name VARCHAR(64) NOT NULL,
    last_updated DATETIME
);

CREATE UNIQUE INDEX set_names ON sets(name, dist);

/*
Join table for mapping sets and repo states together. These are added last, and
the intention of the foreign key constraints are that a) deleted sets will automatically
clean up their associated set_repo_states, and b) repo_states rows will not be removable
until all the sets using them have also been deleted.
*/
CREATE TABLE set_repo_states (
    set_id INTEGER NOT NULL,
    repo_state_id INTEGER NOT NULL,
    FOREIGN KEY(set_id) REFERENCES sets(id) ON DELETE CASCADE,
    FOREIGN KEY(repo_state_id) REFERENCES repo_states(id) ON DELETE RESTRICT,
    UNIQUE(set_id, repo_state_id) ON CONFLICT ABORT
);
