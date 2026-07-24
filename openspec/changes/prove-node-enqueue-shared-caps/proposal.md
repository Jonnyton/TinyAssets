## Why

The approved in-node enqueue primitive is enabled by the production deploy, but
its canonical capability spec does not describe the shipped containment
contract and its §14 concurrency proof covers only per-run budgets and
lock-safe appends. Exact global active-queue and per-origin lineage boundaries
must be proven under shared contention before this uptime surface can be
treated as complete.

## What Changes

- Backfill the shipped, trusted-context in-node enqueue contract into the graph
  execution substrate.
- Add deterministic concurrent compile-and-invoke coverage proving that the
  global active-queue cap cannot be overshot.
- Add deterministic concurrent compile-and-invoke coverage proving that one
  origin lineage cannot exceed its cap while unrelated origins remain
  independently admissible.
- Correct stale test documentation that still describes the production flag as
  waiting to go live.
- Make no runtime behavior change unless the boundary proof exposes a defect.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `graph-execution-substrate`: document the shipped in-node enqueue admission
  and atomic shared-cap containment requirements.

## Impact

The change affects the canonical graph execution substrate spec and
`tests/test_node_enqueue_concurrency.py`. It introduces no API, storage,
dependency, deployment, or production configuration change.
