## Why

The local OpenSpec drain lost useful time globally probing unrelated historical
worktrees and then stalled after a merged implementation because its foldback
worker interpreted the one-PR contract as including the prior worker's PR.
Fresh runtime evidence and the current Ringer re-check justify a narrow
hot-path correction while the generic cloud-owned drain is still being built.

## What Changes

- Apply `worktree_status.py --provider` selection before expensive per-worktree
  git probes and preserve the same matching output.
- Require disposable drain workers to use the exact identity-scoped diagnostic
  under a short finite cap while retaining exact claim/context checks.
- Clarify that the one-PR budget is per worker attempt and require a merged-slice
  continuation to open and return one fresh foldback PR.
- Add focused regression proof without changing claim, review, CI, merge, or
  OpenSpec authority.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `development-coordination-runtime`: bound worktree inspection on the
  disposable-worker hot path and make foldback delivery unambiguous.

## Impact

Affected code is limited to `scripts/worktree_status.py`,
`scripts/openspec_drain_supervisor.py`, their focused tests, and coordination
documentation. There is no public MCP/API, product runtime, storage, provider,
or cloud authority change.
