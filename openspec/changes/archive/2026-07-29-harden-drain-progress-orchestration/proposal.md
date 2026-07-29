## Why

The always-on OpenSpec drain can finish and merge a worker slice yet remain
apparently healthy until the provider launcher exits or times out. The
2026-07-29 run demonstrated this after PR #1857: a complete terminal artifact
was present while the controller stayed green and dispatched no foldback.

## What Changes

- Treat a stable, valid terminal result artifact as worker completion even when
  the provider launcher remains alive.
- Recover an unconsumed terminal artifact on controller restart before
  dispatching replacement work.
- Report the unconsumed-result handoff as waiting rather than healthy progress.
- After a target-local `BLOCKED`, immediately consider a different eligible
  candidate; preserve the idle interval when no alternative exists.
- Give each admission attempt a distinct deterministic branch/worktree lane so
  multiple verified slices can revisit one still-open target safely.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `development-coordination-runtime`: strengthen drain completion, recovery,
  health, and blocked-candidate scheduling requirements.

## Impact

The change affects the OpenSpec drain supervisor, watchdog health derivation,
mechanical admission naming, their focused tests, and the operator runbook. It
does not add parallel workers, change provider quotas, or clean up historical
worktrees.
