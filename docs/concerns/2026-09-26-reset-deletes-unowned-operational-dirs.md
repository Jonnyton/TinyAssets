# `reset(confirm=True)` deletes the operational stores and the migration backup

**Found** 2026-09-26, routing every reader through the universe-ownership
predicate (#4012). Pre-existing on `main`; unchanged by that PR.

**Severity** P1 — data loss on a host-invoked command, including a directory
`docs/host-actions.md` says in as many words not to delete.

`tinyassets/reset.py::universe_dirs` returns every non-dotted directory under the
data root except `{lance, output, runs, wiki}`, and `reset(confirm=True)`
`shutil.rmtree`s all of them. On the live root that is `lancedb` (not the listed
`lance`), `daemon_wikis`, `cloud-automation-inputs`, `scratch`, the workspace
pool, the `_backup_subject_migration_*` migration backup and every
`_removed_universes_*` archive.

**Not the fix:** routing it through ownership. A destructive reader needs a
POSITIVE reason to believe a directory was a universe, and "nobody owns it" is not
one — the migration backup owns nothing. #4012 left this predicate alone
deliberately and named it `_RESERVED_OPERATIONAL_DIRS` so the two questions stop
sharing an answer. The cut needs a marker file or a past prune's archive name, and
a dry-run inventory first: `scripts/universe_ownership_inventory.py` reports
ownership read-only and never recommends removing anything.

**Related, same lane:** a wiki uptime-canary test appends a RED line to the
TRACKED `.agents/uptime.log` (`url=https://fake/mcp`), dirtying every worktree that
runs the suite.

Delete this file when a prune needs a positive universe signal and `reset` no
longer removes a directory it cannot identify.
