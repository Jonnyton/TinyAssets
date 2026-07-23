## Why

PR #1485 shipped a typed, fail-closed per-job sandbox runner seam, but the
2026-07-22 full-coverage audit omitted that seam from its final backfill table.
The behavior therefore has tests and a live task marker but no canonical
OpenSpec requirement. Leaving it only inside the incomplete
`distributed-execution` change would make proposed future authority and the
small landed protocol indistinguishable.

## What Changes

- Create the as-built canonical base for the `distributed-execution`
  capability using only the shipped `runner/v1` seam.
- Specify its immutable capability/action vocabulary, strict JSON-object
  payload boundary, fail-closed backend preflight, and
  result/enforcement-receipt validation.
- Record that the only built-in backend is unavailable, no production caller
  invokes the seam, and no real confinement, authority, lease, persistence, or
  secret-removal guarantee has shipped.
- Leave the active `distributed-execution` delta and its PR stack unchanged;
  that change continues to own future authenticated external execution.

## Capabilities

### New Capabilities

- `distributed-execution`: the currently landed, backend-neutral per-job runner
  protocol, its only built-in unavailable backend, and its unwired boundary.

### Modified Capabilities

None.

## Impact

This is current-behavior reconciliation. It adds canonical requirements and
updates the coverage audit, but changes no runtime code, plugin payload,
storage, public MCP surface, credential path, compute source, or deployment.
Primary evidence is `tinyassets/sandbox_runner.py`, its packaged plugin mirror,
and `tests/test_sandbox_runner.py`.
