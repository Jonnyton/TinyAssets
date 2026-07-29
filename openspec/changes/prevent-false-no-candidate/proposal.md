## Why

The automatic OpenSpec drain reported `NO_CANDIDATE` with 834 unchecked tasks
and eight claims already classified as stale. This turns conservative
coordination into a permanent throughput stall and makes the visible waiting
state misleadingly passive.

## What Changes

- Release claims that the host confirmed belong to closed sessions without
  discarding their durable worktrees, branches, or change artifacts.
- Require a drain worker to reap policy-qualified stale claims and revalidate
  stale blockers before it may report no candidate.
- Add a controller-side gate that rejects `NO_CANDIDATE` whenever
  `claim_check.py` still exposes a claimable row, stale-claim candidate, or row
  owned by the exact drain identity.
- Snapshot a bounded ordered set of canonical candidates immediately before
  dispatch and require the worker to claim the first still-valid lane before a
  broad audit or backlog scan.
- Preserve fail-safe behavior for genuinely live claims and host-only work.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `development-coordination-runtime`: Make drain idling conditional on
  machine-checked absence of claimable and policy-reapable work.

## Impact

The change affects the OpenSpec drain supervisor prompt/result validation,
focused supervisor tests, the coordination runbook, AGENTS process rules,
STATUS claims, and the existing development-coordination runtime specification.
It adds no service dependency or public API.
