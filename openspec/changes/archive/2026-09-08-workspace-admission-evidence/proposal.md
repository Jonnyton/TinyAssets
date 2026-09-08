## Why

The September 8 owner-supplied app retest reports completed overlapping workspace
runs but cannot establish whether either encountered contention. Current create
and checkout receipts expose lease generations, not admission observations.
Users cannot safely reconstruct internal lock checks from their graph data.

## What Changes

- Include measured admission attempts, observed lock conflicts and actual retry
  sleep duration in create/checkout results, including admission refusals.
- Preserve existing scheduling, lock lifetime, quotas, errors and timeout policy.
- Keep evidence scoped to the current operation, with no holder identity or path.
- Preserve missing evidence in historical results as unknown, not zero contention.

## Capabilities

### New Capabilities

None: no new tool, action, scheduler or graph primitive.

### Modified Capabilities

- `graph-execution-substrate`: workspace effects report factual admission evidence
  so callers can distinguish observed contention from merely overlapping runs.

## Impact

Workspace pool observation and effect receipts, focused tests and plugin mirror.
Additive result JSON on existing effect/read surfaces; no storage migration,
authority change, new dependency or private workflow edit. This is evidence, not
a claim that scheduling is fair or that the app's checklist passes. Delivery
destination restoration remains owner-controlled and outside this change.

Owner: codex. Branch: `codex/workspace-admission-evidence`. One PR for this intent.
Other in-flight workspace-node provisioning and repository proof remain separate.
