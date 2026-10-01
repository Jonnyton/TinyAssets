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
| `.workspace-staging/` | platform | 5 | **Stays at the root, masked** (refute round 1: lease rows store absolute paths). |
| `provider_definitions.json`, `ledger.json`, `status.json` | platform | 1, 6, 5 | `.runtime/state/` |
| `story.db`, `knowledge.db*`, `checkpoints.db*`, `lancedb/`, `outbound.db` (per-universe uses) | platform indexes and stores | 4, 5, 5, 4, 22* | `.runtime/state/`. *Most `outbound.db` references are the data-root ledger, which is not per-universe and is untouched. |
| `branch_tasks.json.lock`, `auto_ship_attempts.jsonl.lock` | platform locks | 6, 2 | `.runtime/state/` |
| `workspaces/` | platform-managed checkouts | 12 | **Stays at the root, masked** (refute round 1: `workspace_leases.path` and `quarantine_path` are absolute and drive deletion). |
| `wiki/` | user content (universe wiki pages) | 9 | Stays at the root as user files, read through `universe_files`. |
| `soul_versions/`, `soul.edit.md` | soul governance | 5, 6 | **Stay at the root as the user's files** (build finding): once the agent can write `soul.md` directly, a policy restricting governed edits of it constrains nothing, and the daemon already reads both through `universe_files`. Harness S6 retires them. |
| `config.yaml`, `soul.md`, brain files, `voice.md`, `AGENTS.md` | user | many | Stay at the root, read through `universe_files` (already the case). |
| `skills/`, `prompts/`, `extensions/`, `workflows/`, `bin/`, `notes/` | user | — | Stay. |

### Names the first inventory missed

`storage_accounting.UNIVERSE_ENTRIES` already lists every per-universe name the
code creates, and `tests/test_storage_registry_complete.py` keeps that list
complete. Nine of its root-level entries are not in the table above:
`.usage_ledger.db`, `.external_write_receipts.db`, `.idempotency.db`,
`.runtime_status.json`, `.engine_mcp_config.json`, `.pause`,
`.authoring.db`, `.wiki_write_back_destination_markers.db` (which lives in
`wiki/`, a user directory) and `.langgraph_runs.db`. All of them are platform
state and all of them move. Two more of its entries, `.lock` and
`.credentials.json`, are files inside credential directories rather than root
entries, so they move with their directory. The production listing adds
`.idle_cycle_stamp.json`. A hand-assembled inventory missed a quarter of the set,
which is why the set is no longer hand-assembled (below).

## One registry, four readers

`universe_paths.PLATFORM_NAMES` is the only list. Each entry records the
name, its kind (file, directory, SQLite with sidecars, or a prefix such as
`.worker_supervisor.`), and its `reset` disposition. Four consumers derive from
it and from nothing else:

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
   `.runtime/state/`, skipping only the migration's own lock and marker. The
   two uncounted directories (`workspaces/`, `.workspace-staging/`) stay at
   the root, so no per-name flag is needed. A test fixes the invariant: one
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
- **Both locations exist.** This happens when a root entry reappeared after
  a partial run, or was written by a workflow jail. The migration **refuses**:
  it moves nothing more, writes no marker, and raises with both paths. Every
  resolve of that universe fails loudly until an operator decides which copy
  is authoritative. Picking one automatically would serve a database while
  discarding committed work in the other, or pair a database from one copy
  with sidecars from the other (refute round 1).
- **Links.** A root entry that is a symbolic link also **refuses** the
  migration, and nothing is moved. A host may have linked a large store such
  as `lancedb/` onto another disk. Parking the link and continuing would serve
  an empty replacement store while the real one sat outside. A relative link
  would also change meaning when moved, and a parked link would fail the
  restore script's blanket link check (refute round 1). The production
  dry-run on 2026-10-01 found no links and no conflicts in any universe.
- **Tombstones.** After each entry moves, the migration creates a read-only
  directory at its old name holding only `.universe-runtime-state-tombstone`
  (a mode-`000` directory cannot be recognized on Windows, where the desktop
  host runs the same code). Prefix entries (`.worker_supervisor.*`) and SQLite
  sidecars leave none. A reader the conversion missed
  then fails loudly (`IsADirectoryError`, or SQLite "unable to open") instead
  of creating and trusting an empty store at the root. Tombstones always
  exist, so the jails can mask them. Agents cannot remove or replace them, so
  a file planted under a legacy name is impossible, even if the marker is
  lost and the migration retries. A retry skips a name whose root entry is
  its tombstone.
- **Durability order.** For each entry the migration renames it and creates
  its tombstone. Then it fsyncs, in order, the state directory, every
  directory it created, and the root. Then it creates the marker, fsyncs the
  file, and fsyncs the state directory again. Power-loss tests cut the
  sequence at every boundary (a rename seam is simulated by failing the Nth
  rename or fsync) and assert that the next resolve finishes with every byte
  in one place.
- **Eager as well as lazy.** Daemon start migrates every registered universe
  before serving, so the window in which a migration can overlap a backup is
  the seconds after a deploy. The lazy resolve still covers a universe
  created or restored later.
- **A turn in flight.** A deploy recreates the container, so no old-image
  process survives the cutover. Inside the new image every reader goes
  through `platform_path`, so the first one migrates and the rest wait. The
  agent jail and workflow jails can still write root names, but after
  migration those names are user files that nothing reads.
- **Windows hosts** (desktop) cannot rename a file another process holds
  open. The rename raises, the lock is released, the marker is not written,
  the resolve fails loudly, and the next resolve retries. Nothing is half
  served.
- **One-way, enforced.** An image without the resolver must not serve a
  migrated universe: it would find the root databases missing (tombstoned)
  and fail, or, without tombstones, create empty ones. A deploy note cannot
  stop that, because two paths roll back automatically:
  `deploy/deploy_fail_safe.sh` restores the previous image when health
  fails, and `deploy-prod.yml` rolls back after a red public canary (refute
  round 1). So the image carries a label, `io.tinyassets.state-layout=2`.
  The first migration on a host writes `/data/.state-layout` containing `2`.
  Both rollback paths, and `release-reconcile`, read the candidate image's
  label and refuse to start an image whose layout is below the data's
  (exit 3, manual). An image without the label counts as layout 1.

## What only the build could find

- **A universe's own `.runs.db` is the workspace pool.** Production's holds
  only `workspace_leases` (514 rows), `workspace_ledger`, `workspace_outbox`
  and `workspace_push_intents`. A lease row's absolute path drives deletion,
  so an agent able to write this file at the root could aim cleanup at any
  path, another user's included. `runs.universe_runs_db_path()` is now the
  only route to it, and `runs_db_path()` names the data root's database
  only. Every other per-universe store in production (`story.db`,
  `knowledge.db`, `checkpoints.db`, `outbound.db`) was empty.
- **Enumerators must never migrate.** A reader that walks the data root
  (`providers.definition.list_commons_definitions`) would have run the
  migration inside a backup directory, which holds `.runs.db` and
  `outbound.db`, or inside the data root itself. Such readers use
  `migrated_platform_path()`, which returns nothing for an unmigrated
  directory. The migration also refuses any directory whose name starts with
  `_` or `.`, the reserved operational names, and any directory holding a
  data-root marker (`.tinyassets.db`, `.auth.db`, `.storage_accounting.db`).
  Daemon start migrates exactly `daemon_server.owned_universe_ids()`.
- **The layout is recorded before the first move**, not after the last. A
  boot that dies halfway has already made the data unreadable to an older
  image.

## Every jail masks the state, not only the tool jail

`provider_jail.hidden_dir_masks` exempts `.runtime` from masking, because a
launch needs its provider home and credential snapshot from under it. A
workflow jail binds the universe read-write, so without a further mask a
workflow shell could truncate `.runtime/state/knowledge.db`, delete a WAL, or
unlink `.migrate.lock` so that another process locks a replacement inode
(refute round 1). Every provider view therefore mounts an empty tmpfs over
`.runtime/state` and over every tombstone. The provider home and launch
credentials stay under `.runtime/` and are unaffected.

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

`workspaces/` and `.workspace-staging/` stay at the root. Their lease rows
store absolute paths, and cleanup deletes whatever those paths name, so
moving the directories would turn cleanup on whatever the agent later put at
the old path (refute round 1). The daemon creates both directories before a
jail launches, and the jail masks them with an empty tmpfs, like
`.runtime/`.

## The gate: an API boundary plus a tripwire

A text scan alone cannot prove that every reader moved (refute round 1).
`test_storage_registry_complete.py` scans only `tinyassets/`, recognizes a
few literal forms, and accepts a name classified in any scope. Indirect
joins such as `udir / dbname` pass it. So completeness rests on three layers:

1. **One API per scope.** Universe state goes through `platform_path`.
   Data-root stores keep their existing path functions. The names shared
   between the two scopes (`.runs.db`, `outbound.db`, `ledger.json`,
   `checkpoints.db`, `knowledge.db`, `story.db`, `.effector_consents.db`,
   `.idempotency.db`, `.external_write_receipts.db`) are reached through a
   constant imported from the module that owns the store, never as a
   literal.
2. **The source gate** covers every executable tree: `tinyassets/`,
   `fantasy_daemon/`, `domains/` and `scripts/`. The packaging mirror is
   covered by `mirror-parity`. The gate refuses a registry name as a string
   literal anywhere except `universe_paths.py` and an allowlist of data-root
   owners. Each allowlist entry is a file and a reason, and an entry that no
   longer matches fails the test.
3. **The tripwire.** Tombstones make any missed reader fail loudly in tests
   and in production instead of serving an empty store. The test suite runs
   every universe fixture through `ensure_migrated`, so a legacy-root read in
   any exercised path is an error rather than a silently green test.

Refute round 1 also named the `fantasy_daemon` startup path
(`fantasy_daemon/__main__.py`: root database paths, knowledge and LanceDB
singletons, a long-lived checkpointer). It is converted with the rest, and it
calls `ensure_migrated` before opening anything.

## Reset dispositions

Each registry entry also carries a `reset` disposition: `credential`
(blocks a scoped reset), `audit` (archive first), `operational` (no reset
adapter yet, so it blocks), or `resettable`. These replace scoped reset's
hand-written sets one for one. Tests pin that credentials, receipts and
migration metadata are never resettable.

## Risks

1. **A reader missed by grep.** Mitigations: the source gate, plus a
   production listing check after deploy (no legacy name left at any root),
   plus `storage_accounting` totals unchanged before and after.
2. **Migration under live traffic.** Every reader blocks on the migration
   lock until the marker exists, so nothing is served from a half-moved
   universe. The jail binds the root read-write only when the marker exists.
3. **Disk space.** A rename stays on the same filesystem, so no copy is
   made.

## Refute round 1 (gpt-6-astra, 2026-10-01): REJECT, and what changed

Seven P1 findings, each verified against the cited line before folding:

| Finding | Change |
|---|---|
| Automatic rollback (`deploy_fail_safe.sh`, `deploy-prod.yml`) can start an old image on migrated data | Image label `io.tinyassets.state-layout` and a data-side layout file. Every rollback path refuses an image below the data's layout. |
| Workflow jails can write `.runtime/state` and unlink the migration lock | Every provider view masks `.runtime/state` and the tombstones. |
| Moving `workspaces/` leaves absolute lease paths that drive deletion | `workspaces/` and `.workspace-staging/` stay at the root and are masked. |
| The `fantasy_daemon` startup path opens root stores outside `tinyassets/` | Converted, and it calls `ensure_migrated` first. The gate covers `fantasy_daemon/`, `domains/` and `scripts/`. |
| Conflicts park the root copy and serve the destination, losing committed work | A conflict refuses the migration and the resolve fails loudly. |
| Parking a symlink serves an empty replacement store | A link refuses the migration. |
| A source scan cannot prove reader completeness | API-per-scope, a wider gate, and tombstones as a runtime tripwire. |

The P1 concerns (power-loss ordering; backups overlapping the migration) are
answered by the specified fsync order, the tests that cut it at every seam,
and eager startup migration. The P2 concern (reset dispositions) is answered
by a `reset` field in the registry.
