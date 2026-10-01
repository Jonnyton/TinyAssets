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

- It runs once per universe, under the universe's existing lock, at daemon
  start and before any tool jail opens on that universe.
  - Each legacy entry that is a regular file or directory, and **not a link**,
    is renamed into `.runtime/state/`. A link is removed and logged.
  - SQLite databases move together with their `-wal`/`-shm` sidecars while
    no connection is open. Startup ordering makes that possible: migration
    runs before the stores open.
- A marker file `.runtime/state/.migrated-v1` makes it idempotent.
- It is one-way. An image without the resolver must not serve a migrated
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
2. **Migration under live traffic.** It runs before serving. A universe whose
   lock is held is skipped and retried at the next start, and it keeps the
   old read-only root until it has migrated (the jail checks the marker).
3. **Disk space.** A rename stays on the same filesystem, so no copy is
   made.
