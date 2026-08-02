## Why

Two shipped run-database surfaces were missed by the 2026-07-22 full-coverage
audit: typed run evidence receipts and the installation/data-root-local
teammate mailbox.
Both are publicly dispatchable and source-tested, but no canonical or active
OpenSpec requirement owns their behavior or their security limitations.

## What Changes

- Add the as-built contract for run-bound source-acquisition, claim-lineage,
  and revision receipts: type-specific normalization, contradiction checks,
  bounded compact size-check encoding, JSON-compatible extension preservation,
  run-existence validation, filtering, ordering, and public record/list
  authorization.
- Add the as-built contract for durable teammate-message send, receive, and
  acknowledgement: exact message types, JSON bodies, wildcard broadcasts,
  filtering, ordering, bounds, and current acknowledgement checks.
- State the current limitations explicitly: run receipts assign no truth rank
  and provide no caller idempotency; the declared receipt foreign key is not
  enforced and orphan receipt rows pass the current visibility predicate;
  receipt ACL derivation applies only when a run actor's `universe:` suffix
  trims to a non-empty ID while other or empty-suffix actor strings pass;
  extension keys are not validated; teammate
  recipients and reply targets are not storage-validated; empty-node reads
  enumerate the
  shared data-root mailbox; the message actions perform no run-visibility,
  universe-access, or resource-level actor check; caller node identity is not
  independently authenticated; acknowledgement time is returned but not
  stored; a public receive limit rejected by `int()` can escape the JSON error
  wrapper; and the callable graph-compiler message helpers are not integrated
  into `NodeDefinition` or the `compile_branch` execution path.
- Change OpenSpec only. Runtime behavior and public tool shape do not change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `graph-execution-substrate`: Own the shipped run evidence receipt store and
  the installation/data-root-local teammate mailbox as run/node coordination
  behavior.

## Impact

- Canonical target: `openspec/specs/graph-execution-substrate/spec.md`.
- Evidence only, unchanged:
  `tinyassets/runs.py`, `tinyassets/api/runs.py`,
  `tinyassets/api/runtime_ops.py`, `tests/test_run_receipts.py`,
  `tests/test_teammate_message.py`, and
  `tests/test_universe_server_isolation.py`.
- `distributed-execution`, `external-effect-receipts`,
  `evaluation-outcomes-and-attribution`, and
  `live-mcp-connector-surface` remain separate owners and are not modified.
