# A universe is any directory under /data

**Found 2026-09-02**, when the founder read a universe count from another
session and said: *"a universe should only exist if it belongs to a user and
I'm really the only user and have made only the universe that was created when
I workos logged in for the first time."*

They are right, and the cause is not stale data. `read_graph target="graphs"`
returns **12 universes** on production today. Five of them are not universes at
all, and three of those are the archives that PAST PRUNES created.

## What the live surface returns

Read anonymously from `https://tinyassets.io/mcp` on 2026-09-02, every row
`visibility: public`:

| id | what it actually is |
|---|---|
| `_backup_subject_migration_20260829T055340Z` | the backup taken during the WorkOS subject migration |
| `_removed_legacy_20260829` | a prune's archive |
| `_removed_universes_20260828` | a prune's archive |
| `_removed_universes_20260829` | a prune's archive |
| `cloud-automation-inputs` | an operational input directory |
| `daemon_wikis` | an operational directory |
| `scratch` | scratch space |
| `paper-notes` | an old test universe |
| `u-tiny` | an old test universe |
| `u-01ky3zh1arr8qth8jee7zx63pq` | a universe; owner unverified |
| `u-01m160scp4azzpa6yy3ayxa5yh` | a universe; owner unverified |
| `u-01kxm1vszd8hwp7em418asq8h9` | the founder's own, the only one they made |

`read_graph target="graph" graph_id="_removed_universes_20260829"` answers with
a full universe payload. The graveyard is browsable as a universe.

## The cause

`tinyassets/api/universe.py`:

```python
_TOP_LEVEL_OPERATIONAL_DATA_DIRS = frozenset({"lance", "output", "runs", "wiki"})

def _is_listable_universe_dir(path: Path) -> bool:
    return (
        path.is_dir()
        and not path.name.startswith(".")
        and path.name not in _TOP_LEVEL_OPERATIONAL_DATA_DIRS
    )
```

A universe is **any directory that is not one of four hardcoded names**. That
is a denylist standing in for a definition. Every directory the platform
creates under the data root for its own reasons — a backup, a prune's archive,
scratch, an inputs folder — becomes a universe the moment it exists, with no
code change and no warning. `sync_universes_from_filesystem`
(`tinyassets/daemon_server.py`) registers them on the same rule.

So the prunes DID run. What the founder is seeing is partly their output.

## Why it matters beyond tidiness

- **The definition is inverted.** A universe should exist because a user made
  one — a positive, owned record — not because a directory exists. Every future
  operational directory is a new phantom universe, and the fix for each is
  another name in a frozenset somebody has to remember.
- **They are all `public`.** Today an anonymous reader enumerates them; after
  `no-anonymous-principal` any signed-in user will. Either way they are other
  people's future commons listing, populated by our backups.
- **A prune cannot converge.** Pruning universes creates a directory that is
  itself listed as a universe, so the count never reaches what the founder
  expects and the next prune has more to look at than the last.

## The shape of the fix

Enumerate from a positive marker, not from the filesystem: a universe is a row
with an owner. `_is_listable_universe_dir` becomes a lookup of the universe
registration/ownership record, and a directory with no such record is not
listed, not readable by id, and not registered by
`sync_universes_from_filesystem`. Operational directories then need no
denylist, because they were never universes.

Then, separately and with the founder deciding each: what happens to
`paper-notes`, `u-tiny`, and the two ULID universes whose ownership is not yet
verified. **Nothing is deleted off this document** — Hard Rule 13, and the
2026-08-26 incident where a live user's bound universe was archived off a stale
inventory. The ownership query has to run inside the destructive step.

## Not yet established

- Who owns `u-01ky3zh1arr8qth8jee7zx63pq` and `u-01m160scp4azzpa6yy3ayxa5yh`.
  They may be from the WorkOS subject migration (the backup directory beside
  them is dated the same day), in which case they are the founder's under an
  old subject id and they should be able to delete them through the app.
- Whether `_backup_subject_migration_20260829T055340Z` is still needed. It is
  a backup; deleting it is a separate decision from hiding it.
