---
status: active
---

# 2026-04-09 Runtime Fiction Memory Graph

## Problem

TinyAssets already accumulates substantial long-run fiction artifacts, but the
daemon still risks treating universe memory as a pile of notes and markdown
files rather than a typed world model. That is good enough for local context
lookups and weakly structured retrieval, but not good enough for hundred-scene
coherence, promise tracking, belief management, or long-horizon revision.

## Context

- [PLAN.md](../../PLAN.md) already points toward hybrid retrieval plus durable
  memory tiers instead of flat transcript stuffing.
- [PLAN.md](../../PLAN.md) also says live state should stay thin and rich
  durable artifacts should become authoritative.
- `output/<universe>/notes.json` is currently a dense note/event stream, not a
  clean narrative memory graph.
- canon pages such as
  [output/default-universe/canon/character-corin-ashmark.md](../../output/default-universe/canon/character-corin-ashmark.md)
  are valuable for humans but not yet a strong machine contract.
- generated scene files are currently prose leaves, but each committed scene
  should also leave behind machine-readable state changes.

## Goal

Give the daemon a memory system that can support long-running complex fantasy
by separating:

1. world truth
2. event history
3. epistemic state
4. narrative debt

The daemon should reason over typed state and generated retrieval packets, then
project that back into human-readable docs and indexes.

## Proposed Runtime Memory Shape

### 1. World Truth Graph

Durable entities and relationships:

- characters
- locations
- factions
- artifacts
- institutions
- magic rules
- canon-level constraints

Each entity should have:

- stable `id`
- type
- summary
- current status
- source/provenance
- confidence / trust
- links to related entities
- last-changed scene/event ref

### 2. Event Graph

Every committed scene should emit a structured scene packet:

- scene id
- book / chapter / scene position
- POV
- time position
- location
- participants
- explicit events
- facts introduced
- facts changed
- promises opened
- promises advanced
- promises resolved
- relationship deltas
- world-state deltas

This is the real backbone of long-run continuity.

### 3. Epistemic Graph

The daemon needs to distinguish:

- objective world truth
- what each character knows
- what each character suspects
- what each character falsely believes
- what the reader has seen
- what the narrator can currently assert

Fantasy often derives tension from asymmetry of knowledge, hidden history, and
misread signs. The system should model that directly instead of collapsing
everything into neutral canon.

### 4. Narrative Debt Graph

Long-form quality depends on tracking open obligations, not just facts.

Track:

- open promises
- unresolved mysteries
- foreshadowing obligations
- political tensions
- relationship pressure
- travel / logistics obligations
- thematic or stylistic protections worth carrying forward

This graph is what keeps the daemon from becoming locally clever but globally
forgetful.

## Proposed Artifact Layout

Target shape per universe:

```text
output/<universe>/
  PROGRAM.md
  progress.md
  canon/
    characters/<id>.md
    locations/<id>.md
    factions/<id>.md
    artifacts/<id>.md
  scenes/
    book-1/chapter-01/scene-01.md
  packets/
    scene-01.json
  ledgers/
    timeline.json
    promises.json
    relationships.json
    epistemics.json
  indexes/
    scene-index.md
    character-index.md
    open-threads.md
    recent-changes.md
```

The markdown docs are for human inspection. The packet and ledger layer is for
runtime reasoning and retrieval.

## Commit Pipeline

Target commit flow:

`draft -> commit -> extract -> update ledgers -> regenerate human docs -> build retrieval packets`

A scene is not truly committed until:

1. prose lands
2. structured deltas are extracted
3. affected ledgers/entities are updated
4. human-facing indexes regenerate
5. retrieval packets for the next loop are refreshed

## Retrieval Implications

The daemon should not retrieve only by semantic similarity. It should query by:

- entity neighborhood
- recent event neighborhood
- active promise neighborhood
- current POV epistemic state
- current location and travel adjacency
- unresolved contradiction / tension surfaces

Hybrid retrieval stays right, but the routing policy should ask for the right
state slice rather than a generic context blob.

## Human-Facing Docs

Markdown should become generated or semi-generated views over the typed model:

- character pages
- location pages
- timeline summaries
- open promises
- relationship maps
- recent change summaries

The docs should be inspectable and link-rich, but they should not be the only
canonical memory substrate.

## Phased Direction

### Phase 1

Add scene commit packets and a promise/timeline ledger without breaking current
scene generation.

### Phase 2

Split canon into typed entity records with stable IDs and provenance.

### Phase 3

Add epistemic and relationship ledgers.

### Phase 4

Regenerate human-readable markdown indexes from the underlying model.

### Phase 5

Route orient/plan/draft against typed retrieval packets rather than broad note
blobs.

## Open Questions

- What minimal packet schema can be introduced without stalling the current
  runtime?
- Which ledgers should be treated as fully canonical versus derived caches?
- How much extraction should be symbolic vs. model-generated with verification?
- What should happen when prose and extracted structured state disagree?

## Next Home

Implementation is staged in
[docs/exec-plans/active/2026-04-09-runtime-fiction-memory-graph.md](../exec-plans/active/2026-04-09-runtime-fiction-memory-graph.md).
