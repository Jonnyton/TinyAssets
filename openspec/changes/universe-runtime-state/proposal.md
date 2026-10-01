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
  - It runs lazily inside the resolver, under a per-universe migration lock
    that every reader waits on, so nothing reads a half-moved universe. A
    link is moved aside as a link and never followed.
  - After it has run, the old root location is **never read**. There is no
    fallback.
- A source gate fails the build on any platform name joined onto a universe
  directory outside the resolver. It uses the same shape as
  `test_storage_registry_complete.py`.
- Only after every reader moves does the tool jail bind the universe root
  read-write. `.runtime/` stays masked from the jail, and the agent sees
  `.runtime/agent-sessions` read-only only where the session log is exposed.
- **Files that are the user's stay the user's.** `config.yaml`, `soul.md`,
  the brain files, `soul.edit.md` and `soul_versions/` stay at the root and
  are read through `universe_files`. Once the agent can write `soul.md`
  directly, the governance files constrain nothing, so the S6 history store
  retires them rather than this change moving them.
- `.worker_supervisor.*.json` files move with the rest and are written under
  `.runtime/state/` from then on. The ones with no live owner (683 in
  production) are deleted only after every reader is verified.

## Capabilities

### Modified Capabilities

- `universe-agent-harness`: one requirement is added. Platform state lives
  only under `.runtime/`, and the agent's root is writable.

## Impact

- **Storage:** about 35 names move (design.md's inventory plus every name in
  `storage_accounting.UNIVERSE_ENTRIES`), each through a single resolver and a
  gate. `.runtime/` is excluded from the universe byte walk
  (`storage_accounting._NOT_USER_BYTES`), so the walk is changed to count
  `.runtime/state/` too: per-universe totals are
  identical before and after, and that equality is a test.
- **Migration:** one-way and idempotent. An old image must not serve a
  migrated universe, so the image carries a state-layout label and
  `deploy_fail_safe.sh` refuses to converge any image, forward or rollback,
  below the data's layout.
- **Authority:** the agent gains write access to its root. The cross-user
  floor is unchanged.
- **Readers:** listed per name in design.md, from a grep of
  `tinyassets/` on 2026-10-01.

Owner: Claude. This is a design PR. The build is one PR, and it is proven
live before the next harness slice.
