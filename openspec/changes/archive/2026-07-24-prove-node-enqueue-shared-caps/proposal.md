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
- Derive one stable, server-owned lineage origin for every trusted root run so
  sibling enqueues cannot evade the lineage cap by minting child IDs.
- Preserve lifetime lineage admission truth across queue garbage collection;
  corrupt archive state fails closed instead of silently resetting that truth.
- Make the per-run enqueue budget atomic and shared across every source node in
  the compiled run.
- Bind the trusted enqueue universe to the physical queue being consumed and
  reject mismatched persisted metadata before execution.
- Keep epoch-1 in-node enqueue public-target-only until request-scoped actor
  authority exists; process-global identity cannot authorize private targets.
- Treat existing blank queue/archive files as corrupt persisted history rather
  than empty state.
- Correct stale test documentation that still describes the production flag as
  waiting to go live.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `graph-execution-substrate`: document the shipped in-node enqueue admission
  contract, stable root lineage, and atomic shared-cap containment
  requirements.
- `daemon-runtime-and-dispatch`: make archived branch-task history
  authoritative for lifetime lineage admission, bind execution to the physical
  queue universe, and fail closed when required history cannot be decoded.

## Impact

The change affects synchronous run-context construction, file-locked
branch-task admission and garbage collection, their packaged runtime mirrors,
the two canonical capability specs, and focused tests. It introduces no public
API, new storage file, dependency, deployment, or production configuration
change.
