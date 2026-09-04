## Why

`run_graph` currently accepts a branch run whose required initial state is
unresolved, creates a durable run row, and only then fails inside graph
execution. The defect was reproduced through the live bound-universe surface on
2026-09-04: provider authority was healthy, but a workflow with a missing
`context` input failed before its first node. Invalid submissions should be
actionable before they consume run, queue, provider, billing, or effect
resources.

## What Changes

- Preflight the exact authorized Branch definition or immutable Branch version
  before run admission and before a run id is minted.
- Treat caller-supplied inputs and declared state-schema defaults as initially
  available. Treat a statically mandatory template/code access as internally
  available only when graph execution proves an earlier superstep produces it.
- Refuse unresolved required inputs with the stable failure class
  `missing_required_inputs`, an exact sorted key list, and schema-derived type and
  example guidance suitable for an agent to repair and retry.
- Create no run row or id, queue work, provider call, admission/billing record, or
  effect on refusal.
- Apply the same preflight semantics to live-definition and immutable-version run
  targets, without changing branch or universe authority. Authorization remains
  ahead of contract disclosure.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `engine-run-admissions`: an invalid initial-state submission is rejected before
  any run or budget admission exists.
- `graph-execution-substrate`: statically mandatory state is resolved from
  supplied inputs, schema defaults, and execution-guaranteed predecessor outputs,
  while declared-but-optional access remains valid.

## Impact

- Run dispatch in `tinyassets/api/runs.py` and shared execution admission in
  `tinyassets/runs.py`.
- Branch topology/state-schema analysis and focused unit/integration tests.
- Public `run_graph` error responses gain a stable failure class and structured
  missing-input guidance; the advertised MCP handle set and authority model do
  not change.
- No migration or user-owned branch mutation is required.
