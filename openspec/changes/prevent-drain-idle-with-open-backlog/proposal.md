## Why

The local OpenSpec drain accepts `NO_CANDIDATE` when the STATUS claim checker
has no immediately claimable row, even when the OpenSpec flow inspector proves
that substantial delivery and coordination debt remains. On 2026-07-31 this
left 37 active changes and 832 unchecked tasks idle for ten consecutive worker
attempts because 30 provider-owned STATUS rows were dependency-blocked and 19
active changes were untracked.

## What Changes

- Treat exact-current-main OpenSpec flow pressure as part of drain candidate
  exhaustion instead of validating only claimable, stale, and owned STATUS rows.
- Give no-row workers one deterministic, bounded backlog-refinery target so they
  can promote or reconcile existing OpenSpec work without inventing product work.
- Make ordinary row lifecycle edits to `STATUS.md` an implicit coordination
  operation rather than a repository-wide write lock when the path appears in a
  Files cell.
- Preserve fail-closed admission: refinery work may triage an existing change or
  dependency, but it cannot bypass live claims, host gates, review, or product
  file collisions.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `development-coordination-runtime`: candidate exhaustion includes bounded
  OpenSpec backlog-refinery work, and STATUS row lifecycle edits use row-scoped
  coordination rather than global file overlap.

## Impact

The change affects `claim_check.py`, `openspec_flow.py`, the local drain
supervisor and their focused tests, plus the cross-provider coordination rules.
It adds no runtime dependency and does not alter public MCP or product behavior.
