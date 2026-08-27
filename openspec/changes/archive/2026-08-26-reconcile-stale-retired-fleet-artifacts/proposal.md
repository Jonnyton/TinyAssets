## Why

Retiring the fixed cloud-worker fleet can strand old epoch-2 tasks and provisioned runtime records whose legacy capacity will never return. Operators need a reviewable, fail-closed cleanup tool that preserves audit history and cannot mutate a plan different from the one they inspected.

## What Changes

- Add an on-demand `stale-fleet` CLI whose default mode prints a stable task/runtime plan and digest without writes.
- Require an exact reviewed digest and exact task/runtime counts before any apply begins.
- Add CAS-guarded stale task cancellation that reuses the existing request-admission cancellation lifecycle and retains payloads.
- Add CAS-guarded stale cloud-worker runtime retirement that reuses the existing runtime lifecycle and retains definitions and history.
- Exclude queue consumption, scheduler behavior, compose fencing, background authority, deployment, automatic execution, and destructive deletion.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `daemon-runtime-and-dispatch`: Add the operator-reviewed, dry-run-first reconciliation contract for artifacts stranded by the retired cloud-worker executor class.

## Impact

The change adds one CLI module and focused planner/apply seams in the epoch-2 task adapter, request-admission store, daemon registry, and daemon runtime lifecycle. It uses only Python and existing SQLite/storage primitives, adds no dependency or public MCP surface, and must be exercised only with explicitly selected test or operator-provided data directories.
