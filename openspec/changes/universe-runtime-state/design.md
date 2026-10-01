# Design: platform state leaves the universe root

## Inventory (production, 2026-10-01; readers from `grep -rlF <name> tinyassets/`)

| Root entry | Owner | Files referencing it | Disposition |
|---|---|---|---|
| `.credential-vault.json`, `.credentials/` | platform (credential blindness) | 3, 6 | `.runtime/state/` |
| `.conversation_memory.db*` (+ `.bak-premigrate-*`) | platform (custody) | 5 | `.runtime/state/`. The backups are deleted after an inventory check. |
| `.pending_requests.db`, `.subscription_state.db*`, `.effector_consents.db` | platform (asks, sign-ins, grants) | 2, 2, 3 | `.runtime/state/` |
| `.runs.db*` | platform (run records) | 16 | `.runtime/state/` |
| `.oauth-refresh/`, `.idle_cycle*`, `.provider-assignment-admission.lock`, `.soul.lock` | platform | 2, 1, 2, 1 | `.runtime/state/` |
| `.worker_supervisor.*.json` (680) | platform, epoch-1 leftovers | 2 | Delete files with no live owner. New ones go to `.runtime/state/supervisors/`. |
| `.workspace-staging/` | platform | 5 | `.runtime/state/` |
| `provider_definitions.json`, `ledger.json`, `status.json` | platform | 1, 6, 5 | `.runtime/state/` |
| `story.db`, `knowledge.db*`, `checkpoints.db*`, `lancedb/`, `outbound.db` (per-universe uses) | platform indexes and stores | 4, 5, 5, 4, 22* | `.runtime/state/`. *Most `outbound.db` references are the data-root ledger, which is not per-universe and is untouched. |
| `branch_tasks.json.lock`, `auto_ship_attempts.jsonl.lock` | platform locks | 6, 2 | `.runtime/state/` |
| `workspaces/` | platform-managed checkouts | 12 | `.runtime/state/workspaces/`. Effectors already treat these as platform-owned. |
| `wiki/` | user content (universe wiki pages) | 9 | Stays at the root as user files, read through `universe_files`. |
| `soul_versions/`, `soul.edit.md` | soul governance | 5, 6 | Retired in harness S6 (the history store replaces it). Until then, `.runtime/state/`. |
| `config.yaml`, `soul.md`, brain files, `voice.md`, `AGENTS.md` | user | many | Stay at the root, read through `universe_files` (already the case). |
| `skills/`, `prompts/`, `extensions/`, `workflows/`, `bin/`, `notes/` | user | — | Stay. |

### Names the first inventory missed

`storage_accounting.UNIVERSE_ENTRIES` already lists every per-universe name the
code creates, and `tests/test_storage_registry_complete.py` keeps that list
complete. Eleven of its entries are not in the table above:
`.usage_ledger.db`, `.external_write_receipts.db`, `.idempotency.db`,
`.runtime_status.json`, `.engine_mcp_config.json`, `.pause`, `.lock`,
`.authoring.db`, `.wiki_write_back_destination_markers.db`,
`.credentials.json` and `.langgraph_runs.db`. All of them are platform state
and all of them move. A hand-assembled inventory missed a quarter of the set,
which is why the set is no longer hand-assembled (below).

## One registry, four readers

`universe_paths.PLATFORM_NAMES` is the only list. Each entry records the
name, its kind (file, directory, SQLite with sidecars, or a prefix such as
`.worker_supervisor.`), and whether its bytes are `counted` against the
owner's storage. Four consumers derive from it and from nothing else:

1. **The migration** moves exactly the registry's names.
2. **The source gate** refuses any registry name joined onto a path outside
   `universe_paths`. `UNIVERSE_ENTRIES` in `storage_accounting` becomes
   `frozenset(PLATFORM_NAMES)`, so the existing completeness test now also
   forces every new per-universe name into the registry and through the
   resolver.
3. **Storage accounting.** `.runtime/` is excluded from the universe walk
   (`_NOT_USER_BYTES`). If the walk were left alone, every counted store moved
   under `.runtime/state/` would stop being charged, which would be an
   uncounted store created by a refactor. So `_universe_files` also walks
   `.runtime/state/` and skips only the names whose `counted` flag is false.
   Those are exactly the names that are uncounted today: `.workspace-staging`,
   and `workspaces`, which is its own store. A test fixes the invariant: one
   universe's totals are identical before and after migration.
4. **Operator reset.** `scoped_reset._walk_home_without_following` classifies
   home entries with hand-written sets (`_CREDENTIAL_NAMES`,
   `_HOME_AUDIT_PREFIXES`, `_HOME_OPERATIONAL_NAMES`). After the move those
   names are under `.runtime/state/`, and every home contains a dot directory
   it calls "unclassified". So the reset classifies `.runtime/state/` entries
   through the registry, and the hand-written sets are deleted.

The other paths that enumerate a universe by name:
- **Account deletion** removes the whole home directory
  (`account_deletion._stage_home`). `.runtime/state/` is inside it, so
  nothing changes. A test asserts that a migrated home leaves nothing behind.
- **The backup full tier** tars the whole volume, so the moved files are
  covered.
- **The backup brain tier** copies only data-root `*.db`. Per-universe
  databases were never in it, before or after this change. That is recorded
  as a gap, not changed here.
- **Restore** of a pre-migration backup yields a universe without the marker.
  The next resolve migrates it (below).

## One resolver, no fallback

```python
platform_path(universe_dir, name) -> Path   # .runtime/state/<name>, dirs made with O_NOFOLLOW
```

- Every daemon read and write of a platform name goes through it. Two pieces
  of tooling already exist to build it from:
  - `universe_files.open_runtime_dir`, which has been in place since harness
    S3a;
  - the storage-registry gate's source scan, which supplies the pattern for
    the new gate.
- **No fallback.** After migration, nothing reads the root location of a
  moved name. The gpt-6-astra review of #4172 (finding 6) is the reason: a
  fallback that reads the root once its file is absent is exactly the hole
  that lets an agent-planted root file be trusted.

## Migration

The migration is lazy, blocking and per universe. It is not a startup sweep,
because a startup sweep has two holes:
- a universe it skips (lock held, error) would be served by readers that
  resolve to an empty `.runtime/state/` and create fresh stores there, which
  is split-brain;
- a universe created or restored after the sweep would never migrate.

- `platform_path` calls `ensure_migrated(universe_dir)` before returning. A
  per-process set caches universes already confirmed, which is safe because
  migration is one-way.
- `ensure_migrated` takes an exclusive lock on
  `.runtime/state/.migrate.lock`, which is made no-follow and lives outside
  every moved name. The lock is a held file lock, so a migrator that dies
  releases it. It checks the marker `.runtime/state/.migrated-v1`. If the
  marker is absent, it moves every registry name still at the root, fsyncs
  `.runtime/state/`, and only then writes and fsyncs the marker. Every reader
  in every process blocks on that lock until the marker exists, so no
  connection ever opens on a half-moved store.
- **Crash mid-move.** Each `rename` is atomic on one filesystem. A run that
  dies after moving `x.db` but before its `x.db-wal` leaves both halves
  unopened, because no reader passes the marker check. The next run moves
  whatever is still at the root, `-wal` included. SQLite sidecars (`-wal`,
  `-shm`, `-journal`) move with their database, and a sidecar found alone
  still moves.
- **Both locations exist** (a root entry reappeared after a partial run, or
  was written by a workflow jail, which binds the universe read-write). The
  destination is never overwritten. The root copy is renamed into
  `.runtime/state/.legacy-conflicts/<name>.<ns>` and logged at ERROR. Nothing
  is deleted.
- **Links.** A root entry that is a symbolic link is renamed, as the link
  itself and never followed, into `.runtime/state/.legacy-links/` and logged
  at ERROR. It is not removed, because a host may have deliberately linked a
  large store, such as `lancedb/`, onto another disk. The production dry-run
  shows whether any exist before the build deploys.
- **A turn in flight.** A deploy recreates the container, so no old-image
  process survives the cutover. Inside the new image every reader goes
  through `platform_path`, so the first one migrates and the rest wait. The
  agent jail and workflow jails can still write root names, but after
  migration those names are user files that nothing reads.
- **Windows hosts** (desktop) cannot rename a file another process holds
  open. The rename raises, the lock is released, the marker is not written,
  the resolve fails loudly, and the next resolve retries. Nothing is half
  served.
- **One-way.** An image without the resolver must not serve a migrated
  universe. Deploys only move forward, and `release-reconcile` never rolls
  back across this marker. That is recorded in the change's deploy note.

## The writable root

Once the gate is green and migration has run, the tool jail's universe view
changes as follows:
- the root is a single read-write bind;
- `.runtime/` is masked by an empty tmpfs, and no other hidden entry needs a
  mask, because nothing else is trusted;
- the session log is a read-only bind at `/u/sessions` (harness S4).

The daemon-reads-universe-files rule still applies to every user file. Any
root entry the agent creates is user content by definition, and the daemon
reads it only through `universe_files`.

## Risks

1. **A reader missed by grep.** Mitigations: the source gate, plus a
   production listing check after deploy (no legacy name left at any root),
   plus `storage_accounting` totals unchanged before and after.
2. **Migration under live traffic.** Every reader blocks on the migration
   lock until the marker exists, so nothing is served from a half-moved
   universe. The jail binds the root read-write only when the marker exists.
3. **Disk space.** A rename stays on the same filesystem, so no copy is
   made.
