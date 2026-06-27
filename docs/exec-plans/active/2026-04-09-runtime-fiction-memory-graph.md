# Execution Plan: Runtime Fiction Memory Graph

## Goal

Move TinyAssets from artifact-rich but weakly typed fiction memory toward a
runtime memory model that can support long-running complex fantasy through
scene packets, typed entity records, temporal ledgers, epistemic state, and
narrative debt tracking.

## Origin

- Idea source: user request plus runtime/output graph audit
- Related design note:
  [docs/design-notes/2026-04-09-runtime-fiction-memory-graph.md](../../design-notes/2026-04-09-runtime-fiction-memory-graph.md)
- Related pipeline item: `ideas/PIPELINE.md`

## Scope

- Included:
  - memory-model design and phased delivery plan
  - scene packet contract
  - typed canon/entity direction
  - timeline/promise/relationship/epistemic ledgers
  - generated human-readable indexes
  - retrieval-packet integration target
- Excluded:
  - immediate runtime rewrite in this documentation pass
  - final storage-engine choice for every ledger
  - full backfill of historical universe artifacts

## Architecture Decisions

- Keep live daemon state thin; durable ledgers and packets carry meaning.
- Treat markdown canon pages as human views over stronger typed state, not the
  only memory contract.
- Introduce new structured artifacts incrementally beside the existing runtime
  rather than via a big-bang migration.
- Make every committed scene emit a machine-readable packet.

## Phase 1: Packet Backbone

### Task 1: Define the scene commit packet contract

Acceptance criteria:

- `docs/specs/` or a focused design note records the exact packet schema
- packet includes participants, location, time position, facts introduced,
  facts changed, promises opened/advanced/resolved, and relationship/world
  deltas
- packet contract distinguishes objective facts from uncertain inference

Verification:

- schema doc exists and is linked
- at least one example packet is written against a real scene

### Task 2: Add packet emission on commit without breaking current scene flow

Acceptance criteria:

- commit path writes a packet artifact for newly committed scenes
- packet emission failure is explicit and visible
- current prose output still lands normally

Verification:

- tests for packet emission
- live commit on a test universe writes packet plus scene

## Checkpoint: Phase 1

- scene prose still commits
- one or more packet artifacts exist
- no regression in current daemon loop

## Phase 2: Temporal And Promise Ledgers

### Task 3: Add a timeline ledger

Acceptance criteria:

- scene packets update a durable timeline ledger
- scenes have stable temporal order refs
- timeline queries can answer “what happened before this scene?”

### Task 4: Add a promise ledger

Acceptance criteria:

- promises are opened, advanced, resolved, or broken explicitly
- unresolved promises can be listed for the active universe
- retrieval can filter by active promise pressure

Verification:

- tests over synthetic scene sequences
- manual query on a real universe

## Checkpoint: Phase 2

- timeline and promise queries work on a clean universe
- daemon can retrieve active debt instead of only raw notes

## Phase 3: Typed Entity Records

### Task 5: Introduce stable IDs and typed entity stores

Acceptance criteria:

- characters, locations, factions, artifacts, and other major entities get
  stable IDs
- current canon docs map onto typed records
- provenance and last-changed scene refs are stored

### Task 6: Regenerate or reconcile markdown canon pages from typed state

Acceptance criteria:

- human-readable pages remain useful
- markdown pages no longer drift independently from the typed layer
- entity pages link sideways by relationship and provenance

Verification:

- selected canon pages regenerate correctly
- no silent loss of existing canon content

## Checkpoint: Phase 3

- entity retrieval uses IDs and relationships
- human docs remain inspectable

## Phase 4: Epistemics And Relationships

### Task 7: Add epistemic state tracking

Acceptance criteria:

- per-character known/suspected/false-belief state can be recorded
- reader-visible vs. world-true distinctions are representable
- retrieval can ask “what does this POV actually know right now?”

### Task 8: Add relationship and faction-pressure ledgers

Acceptance criteria:

- relationship deltas attach to scenes/events
- faction and alliance pressure can be queried over time
- narrative planning can retrieve current social tension directly

Verification:

- tests for belief drift and relationship updates
- sample retrieval packets include epistemic and relational slices

## Phase 5: Retrieval And Generation Integration

### Task 9: Build targeted retrieval packets

Acceptance criteria:

- orient/plan/draft can request entity, event, promise, epistemic, and recent
  change slices separately
- broad compatibility blobs shrink
- retrieval favors typed neighborhoods over generic note dumps

### Task 10: Add generated indexes and writer-facing diagnostics

Acceptance criteria:

- universe subtree exposes generated indexes for scenes, characters, promises,
  and recent changes
- daemon/debug tooling can surface continuity pressure and unresolved debt
- human/operator can inspect why a retrieval packet was assembled

## Risks And Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Over-design before proving packet usefulness | High | Start with packet + promise/timeline backbone before larger schema work |
| Model extraction invents false state | High | Keep provenance, confidence, and verification surfaces explicit |
| Markdown and typed state drift apart | High | Treat markdown as regenerated or reconciled views, not separate truth |
| Migration burden across existing universes | Medium | Introduce backfill tools later; prove on clean universes first |
| Retrieval gets slower as ledgers grow | Medium | Use packet/ledger indexes and targeted queries rather than giant context blobs |

## Suggested Early Write Scope

1. packet schema doc
2. commit-path packet artifact emission
3. promise ledger
4. timeline ledger
5. one generated human-readable index

## Landing Notes

- Status row: add a pending work item for the runtime fiction memory graph
- Watch item: only after packet + ledger path works on a real universe
- Design context:
  [docs/design-notes/2026-04-09-runtime-fiction-memory-graph.md](../../design-notes/2026-04-09-runtime-fiction-memory-graph.md)
