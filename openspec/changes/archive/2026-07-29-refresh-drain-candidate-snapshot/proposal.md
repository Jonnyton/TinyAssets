## Why

The long-lived detached drain controller selects candidates from its checkout's
old `STATUS.md`, while mechanical admission correctly revalidates against a
fresh worktree from `origin/main`. After PR #1866 removed the selected
`build-forward successors` state, attempts 4 and 5 selected the same stale hint,
failed admission, and exhausted the run's failure budget.

## What Changes

- Let `claim_check.py` classify a caller-selected Git ref without changing its
  default working-tree behavior.
- Refresh `origin` before each controller-side candidate selection and read the
  exact `origin/main:STATUS.md` snapshot.
- Keep admission-time revalidation against the newly created worktree so the
  claim mutation remains visible.
- Preserve finite budgets and fail closed when fetch or ref inspection fails.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `development-coordination-runtime`: require long-lived drain candidate
  selection to use freshly fetched current-main coordination state.

## Impact

The change affects the claim helper, drain supervisor, watchdog health
classification, focused tests, and the operator runbook. It does not move the
controller checkout, select market compute, change priority policy, or replace
the separately proposed main-universe cloud loop.
