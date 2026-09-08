## Why

The app's owner-approved heartbeat cleanup is blocked because the served agent
cannot inspect or control an attached automation, although the canonical
connector already supports its lifecycle. Users need to manage their own
intentional recurring work through the app they use.

## What Changes

- Expose existing universe-scoped automation reads and lifecycle operations
  through the served graph handles, with explicit operation documentation.
- Preserve existing creation preflight, owner/admin checks, revision conflicts,
  scheduler behavior and secret custody; choose direct versus owner-confirmed
  execution semantics in the independently reviewed design before implementation.
- Return factual control/readback results, distinguishing a paused or retired
  trigger from cancellation of an already-running job.
- Test discovery-to-dispatch reachability and cross-universe refusals so the
  app no longer advertises or requests controls it cannot actually execute.

## Capabilities

### New Capabilities

None: reuse existing automation lifecycle and coarse-grained graph handles.

### Modified Capabilities

- `user-owned-automations`: make the owner's existing lifecycle reachable from
  the served app, with the same ownership/revision and execution semantics.

## Impact

Served tool routing/descriptions, existing automation adapter integration,
focused tests and plugin mirror. No private workflow edit, direct deletion of
the reported private automation, new scheduler, provider-specific control path,
or raw secret exposure. Other missing tools are recorded separately in the
capability-parity concern rather than expanding this into a platform rewrite.

Proposed owner: codex. Proposed branch: `codex/served-automation-lifecycle`.
One PR for this intent, after the workspace receipt delivery lane lands.
This is planning only; admission and shape review precede implementation.
