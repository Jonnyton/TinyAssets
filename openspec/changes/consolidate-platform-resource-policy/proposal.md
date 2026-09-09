## Why

Ten workspace operations exhausted a duplicate starts counter during ordinary
app-owned diagnostic work, despite released leases and already-raised general
activity limits. The owner's direction is simpler accounting of actual platform
use, not private workflow repair or another isolated larger number.

## What Changes

- Remove workspace jobs-per-hour enforcement from both lease admission and
  operation reservations. Keep the existing job rows as observations.
- Preserve existing execution admission, generic effect dispatch, transport-byte,
  pool/lease, storage, identity, consent and cleanup protections.
- Expose authorized, read-only usage evidence through existing status: existing
  activity counts and their actual scope, current workspace allocations,
  transport-window reservations, and explicit unavailability where retained
  storage cannot be safely measured.
- Label dimensions and unavailable observations honestly. Do not present
  transport bytes as stored bytes, or ledger-local locks as global concurrency.
- No schema migration, policy epoch, provider change, commercial change or
  blanket new accounting system.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `engine-run-admissions`: workspace job counts are observational, not another
  starts quota; existing actual-resource checks remain.
- `graph-execution-substrate`: resource observations distinguish throughput,
  occupancy and unavailable values without changing lock policy.
- `live-mcp-connector-surface`: existing authorized status includes scoped
  resource evidence; canary and unauthorized callers see no private usage.

## Impact

Owner: Codex. Branch: `codex/platform-resource-policy`. Primary changes:
`workspace_pool.py`, a read-only API usage projection, authorized status assembly,
focused tests and generated plugin parity. One bounded implementation PR.
Diagnosis/evidence is docs-only PR #3555.

This is a concrete correction toward the owner's direction, not completion of
all resource-policy simplification or Patches. Unified retained-storage coverage,
host-wide capacity enforcement and remaining redundant policies stay explicitly
open. No private workflows or duplicate app test requests.

Independent shape review rejected the first draft's new ledger/epochs as
unnecessary. This revised slice reuses current stores and makes no storage
migration. The review/disposition is in `REVIEW.md`.
