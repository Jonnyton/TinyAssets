## Why

The full-coverage audit proves the canonical OpenSpec tree accurately describes
its bounded shipped behavior, but four intentional full-platform outcomes still
have no complete active OpenSpec owner and do not depend on the unresolved
canonical-store/private-data PLAN decision:

1. moderation, abuse response, appeals, and rate limits;
2. production one-click tray installation across supported desktop platforms;
3. node/evaluator authoring, file I/O, and bounded autoresearch;
4. explicit real-world handoff and outcome linkage beyond generic effect
   adapters.

Legacy execution specs describe these targets, but `docs/specs/` is provenance,
not behavioral authority. Without active requirements and implementation tasks,
the outcomes can be lost, mistaken for shipped behavior, or rebuilt through
standalone RPC families that conflict with the current minimal-handle surface.

## What Changes

- Add a target-only `moderation-and-abuse-response` capability covering
  community flagging, soft-hide, independent review, appeals, moderator
  integrity, rate limits, and scale proof.
- Add a target-only `packaged-tray-installation` capability covering native
  Windows/macOS/Linux artifacts, first-run account binding, safe autostart and
  updates, offline behavior, privacy, and clean-machine acceptance.
- Add a target-only `node-authoring-and-autoresearch` capability covering
  owner-scoped draft sessions, inspectable code, typed file I/O, sandboxed test
  runs, explicit publication, evaluator authoring, bounded optimization, and
  concurrent experiment proof.
- Add a target-only `real-world-handoffs-and-outcomes` capability covering
  consented/idempotent connector handoffs, outcome evidence levels, verification
  lifecycle, deduplication, moderation, and load proof.
- Keep the behaviors behind the canonical MCP handle routers and web/tray
  surfaces. This change adds no standalone advertised MCP handle.
- Keep every requirement active and unsynced until implementation and its
  acceptance evidence land.

## Capabilities

### New Capabilities

- `moderation-and-abuse-response`
- `packaged-tray-installation`
- `node-authoring-and-autoresearch`
- `real-world-handoffs-and-outcomes`

### Modified Capabilities

- `evaluation-outcomes-and-attribution`: Evolve the existing `outcome_event`
  registry into the single evidence-lifecycle owner used by user attestations
  and receipt-bound handoffs; keep `gate_events` as its existing specialized
  cited-in attestation owner rather than creating a parallel outcome registry.

## Impact

The implementation will add moderation, desktop packaging, authoring/
optimization, and handoff services plus evolve the existing extensions outcome
registry through focused storage migrations, API-router actions, CI, security
tests, scale tests, and rendered user-surface acceptance. The exact
implementation files are bounded in `tasks.md`. No runtime or canonical spec is
changed by this proposal.
