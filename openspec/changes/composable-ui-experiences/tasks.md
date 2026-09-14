## Proposal

- [x] Inspect repository principles, current related specs, and delivery WIP.
- [x] Define the experience composition contract and acceptance scenarios.
- [x] Research and refine typed experience primitives, lossless authoring, upstream overlays, device races, voice/routing semantics, E-C1–E-C12 traces and harness parity.

## Before implementation

- [ ] Map responsibilities to current handlers and settle native extension, schema, asset bounds, and renderer isolation.
- [ ] Record Claude research/shape review of primitives.md and research.md in review.md; resolve bridge and profile findings before implementation.

## Implementation and proof

- [ ] Implement one composition with desktop and phone renderers through ordinary user bindings.
- [ ] Add inert import/preview, lineage, private-data exclusion, capability and authority checks.
- [ ] Prove edit/upgrade conflict, stale renderer rejection, accessible recovery, personalization preview, disable and rollback behavior using applicable E-C1–E-C12 vectors.
- [ ] Prove canonical voice handoff, committed input, replay-gap recovery and honest notification delivery outcomes.
- [ ] Retain first-party parity and second-account remix evidence from rendered interactions.
- [ ] Sync verified behavior into canonical specs and archive when implementation lands.
