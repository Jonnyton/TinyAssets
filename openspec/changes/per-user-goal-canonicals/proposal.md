## Why

Goal canonicals are still exposed as one author-controlled default even though
the immutable runner can already execute published Branch versions. This leaves
an actor unable to bind and run their own canonical for a shared Goal, and leaves
gate rejection without a typed, Goal-aware route for returning patch notes.

## What Changes

- Add an additive `goal_canonicals` store keyed by `(goal_id, scope_actor)` with
  active published `branch_version_id` values and setter audit metadata.
- Keep the legacy `goals.canonical_branch_version_id` field during transition:
  default author/host writes update both stores, and reads fall back to the
  legacy field when no new-table row exists.
- Extend `goals action=set_canonical` so an authenticated actor may set or unset
  only their own actor-scoped canonical while author/host default semantics stay
  unchanged.
- Make canonical resolution and `run_canonical` actor-aware, preferring the
  caller's immutable version and otherwise preserving the default fallback.
- Specify a future Goal-aware gate-rejection routing decision that carries typed
  patch notes, resolves the rejecting actor's canonical, detects route loops,
  and invokes the immutable runner.
- Record the already-landed immutable `branch_version_id` runner contract as a
  prerequisite, not as new implementation work.
- Add PostgreSQL storage migration `011`; migration number `010` remains owned by
  its parallel lane and this change will not renumber around its temporary
  absence.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `shared-goals-and-convergence`: Add actor-scoped canonical storage,
  authorization, fallback resolution, dual-write transition behavior, and
  actor-aware immutable canonical dispatch.
- `graph-execution-substrate`: Make the immutable version runner contract
  explicit and define Goal-aware gate-rejection route-back behavior.

## Impact

The change affects the Goal SQLite store and PostgreSQL prototype migrations,
Goal action handling in `tinyassets/api/market.py`, canonical resolution in
`tinyassets/api/canonical_dispatch.py`, and focused canonical/runner tests.
Future route-back implementation will additionally affect evaluation result
types and the run orchestration seam. It adds no dependency and does not modify
`tinyassets/api/universe.py` or `universe_server.py`.
