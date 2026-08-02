## Why

The full-coverage audit found shipped core-runtime behavior that predates the
OpenSpec baseline but is absent from the three canonical capability owners.
Without these deltas, canonical specs understate dispatcher eligibility,
work-target review state, Goal protocols/discovery/gate claims, and persistent
outcome evidence.

## What Changes

- Extend the daemon runtime contract with current soul-guided selection and the
  complete persisted work-target review/artifact lifecycle.
- Extend shared Goals with author-defined ordered protocol metadata, common-node
  and archive-consultation discovery, and the flag-gated claim/retract/list/
  leaderboard/bonus lifecycle.
- Extend evaluation/outcomes with the persistent unverified outcome-event
  registry and make its separation from explicitly invoked evaluators clear.
- Record current limitations rather than target behavior: Goal protocol rollback
  is metadata only, discovery uses fixed server-side ranking/filtering, soul
  affinity remains advisory, and outcome recording performs no verification.

## Capabilities

### New Capabilities

<!-- none -->

### Modified Capabilities

- `daemon-runtime-and-dispatch`: add shipped soul-guidance and complete
  work-target review state without changing queue ownership.
- `shared-goals-and-convergence`: add shipped protocol, convergence-discovery,
  and outcome-gate claim lifecycle behavior.
- `evaluation-outcomes-and-attribution`: add the persistent outcome-event
  evidence registry while keeping generic evaluator ownership separate.

## Impact

- Delta specs under
  `openspec/changes/reconcile-core-runtime-spec-coverage/specs/`, later synced
  into the three existing canonical capability specs.
- No runtime, API, storage, deployment, website, or test behavior changes.
- Existing source and tests are evidence only; known stale test expectations
  are recorded as limitations and are not promoted into the as-built contract.
