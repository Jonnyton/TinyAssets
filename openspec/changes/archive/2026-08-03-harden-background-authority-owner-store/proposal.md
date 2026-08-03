## Why

PR #2162 added a dark typed owner/service seam for background authority holds, but its owner store is only a protocol and its tests use an in-memory fake. Recovery and reauthorization can therefore publish a resolver-supplied attempt fence without atomically proving or committing that attempt in the canonical background authority store. This contradicts the crash-consistency requirement and makes umbrella task 2.6 only partially complete.

## What Changes

- Persist dark queue/source authority-owner records in the existing SQLite background authority database.
- Make owner hold/recovery/reauthorization compare-and-swap validate the exact canonical binding and attempt rows inside one transaction.
- Atomically advance the same attempt with its owner during recovery, and atomically insert/replay the fresh attempt with its owner during reauthorization.
- Fail closed on missing, stale, malformed, conflicting, or resolver-only authority; no owner becomes pickable with an absent or stale attempt fence.
- Keep the seam dark and leave concrete BranchTask/queue/runtime integration to umbrella task 5.3.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `background-branch-execution-authority`: authority-owner persistence becomes crash-consistent with canonical binding and attempt state.

## Impact

The change is limited to the dark background authority owner model/service, its existing SQLite store, packaged runtime mirrors, focused tests, and the umbrella task truth. It adds no queue, dispatcher, provider, public API, credential access, or runtime activation.
