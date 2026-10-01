## Why

Slice S3 of `universe-agent-harness` gives the universe agent its whole root
folder to write, the way pi, OpenClaw and Claude Code give an agent its
project. That is not possible today because platform state is stored in the
same root as the user's files. A production read on 2026-10-01 counted
entries across the three universes on the box.

The platform's state there includes:
- **Hidden entries:** the credential vault, `.credentials/`, the
  conversation, request, consent, subscription and run databases with their
  SQLite sidecars, `.oauth-refresh/`, locks, `.workspace-staging/`, and 680
  `.worker_supervisor.*.json` files (362 of them in the founder's universe).
- **Visible files:** `provider_definitions.json`, `ledger.json`,
  `status.json`, `story.db`, `outbound.db`, `knowledge.db`, `checkpoints.db`,
  `lancedb/`, `soul_versions/`, `soul.edit.md`, `config.yaml`, `workspaces/`,
  `branch_tasks.json.lock` and `auto_ship_attempts.jsonl.lock`.

The tool jail is fail-closed today, but only because of three measures:
- the root is mounted read-only;
- only ten brain files and six harness directories are writable;
- hidden entries are left out entirely.

Making the root writable without moving that state would let the agent create
a file the daemon then trusts. The gpt-6-astra design review gives an
example: a `.effector_consents.db` the agent plants at the root would carry
forged grants.

## What Changes

- Every platform-owned path in a universe resolves through one function,
  `universe_paths.platform_path(universe_dir, name)`, and the result lives
  under `.runtime/state/`. The function creates the directories with
  no-follow descriptors.
- A one-time migration moves each legacy root entry into `.runtime/state/`.
  - It runs under the universe's lock, before the universe serves its first
    tool call after deploy, and refuses on a link.
  - After it has run, the old root location is **never read**. There is no
    fallback.
- A source gate fails the build on any platform name joined onto a universe
  directory outside the resolver. It uses the same shape as
  `test_storage_registry_complete.py`.
- Only after every reader moves does the tool jail bind the universe root
  read-write. `.runtime/` stays masked from the jail, and the agent sees
  `.runtime/agent-sessions` read-only only where the session log is exposed.
- **Files that are the user's stay the user's.** `config.yaml`, `soul.md`
  and the brain files are user configuration, so they stay at the root and
  are read through `universe_files`. `soul.edit.md`, the `soul_versions/`
  governance and `voice.md` are retired with the S6 history store, not moved.
- `.worker_supervisor.*.json` files with no live owner are deleted, and new
  ones are written under `.runtime/state/supervisors/`.

## Capabilities

### Modified Capabilities

- `universe-agent-harness`: one requirement is added. Platform state lives
  only under `.runtime/`, and the agent's root is writable.

## Impact

- **Storage:** about 25 names move, each with a single resolver and a gate.
  Byte accounting is unchanged because `.runtime/` is inside the universe
  walk.
- **Migration:** one-way and idempotent. Rollback means reading the new
  location, so an old image must not serve a migrated universe. The deploy
  is single-direction, and this is recorded in the deploy notes.
- **Authority:** the agent gains write access to its root. The cross-user
  floor is unchanged.
- **Readers:** listed per name in design.md, from a grep of
  `tinyassets/` on 2026-10-01.

Owner: Claude. This is a design PR. The build is one PR, and it is proven
live before the next harness slice.
