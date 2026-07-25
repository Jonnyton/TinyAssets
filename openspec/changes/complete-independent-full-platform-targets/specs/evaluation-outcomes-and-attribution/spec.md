## ADDED Requirements

### Requirement: Recorded outcome events are persistent evidence records with an explicit lifecycle

The `extensions` outcome registry SHALL remain the single generic owner for
real-world outcome records. Each accepted outcome SHALL persist as a unique
`outcome_event` with a non-empty source run ID, registered outcome kind, outcome
ID, recorded timestamp, attesting actor, evidence level/status, and optional
evidence URL, gate-event linkage, JSON payload, note, immutable artifact/node/
evaluator version and output hash, handoff/receipt linkage, and normalized
external identifier. The registry SHALL retain the existing
`published_paper`, `merged_pr`, `deployed_app`, `won_competition`, and `custom`
kinds and MAY accept additional versioned registered kinds required by
handoff adapters.

Direct `record_outcome` calls SHALL create `user_attested` evidence and SHALL
NOT invoke a network prober, evaluator, or adapter merely because an evidence
URL is present. Receipt-bound handoff services MAY append `submitted`,
`accepted`, or externally `verified` evidence only from the exact canonical
effect receipt and provider contract. Later `disputed`, `rejected`, `orphaned`,
or `retracted` evidence SHALL preserve prior events. Evidence changes SHALL be
append-only transitions with actor/provider, time, source, and rationale; they
SHALL NOT silently replace the attestation. Multiple internal sources MAY link
to one normalized external artifact without double-counting it or erasing
per-source attribution.

The existing `gate_events` owner SHALL remain a separate specialized cited-in
Goal/Branch attestation lifecycle. An outcome MAY cite a gate event, but status
changes SHALL NOT automatically mirror between the two registries. Generic
outcome adapters remain owned by `evaluation-runtime-and-scenarios` and run
only when explicitly invoked.

#### Scenario: User attestation round-trips without ambient verification

- **WHEN** an authorized caller records a registered outcome kind against a
  non-empty source run ID with optional evidence and payload
- **THEN** the registry returns a generated outcome ID and timestamp and
  retrieves the stored source/provenance/evidence fields
- **AND** the initial evidence level is user-attested with no external verifier
- **AND** recording performs no network probe, evaluator call, or handoff

#### Scenario: Receipt-bound acceptance appends stronger evidence

- **WHEN** a canonical handoff receipt and provider contract prove destination
  acceptance for the exact source run/output/version
- **THEN** the same outcome registry appends accepted evidence linked to that
  receipt and provider proof
- **AND** it does not claim later publication, peer review, citation, sales, or
  production impact without separate evidence

#### Scenario: Unsupported outcome kind is rejected before persistence

- **WHEN** `record_outcome` receives a kind outside the built-in and versioned
  registered kind set
- **THEN** it returns an error containing the accepted kind/registry evidence
- **AND** it writes no outcome or evidence event

#### Scenario: Multiple sources link one external artifact

- **WHEN** two authorized runs link to the same normalized
  outcome-kind/external-id pair
- **THEN** the external artifact contributes once to aggregate counts
- **AND** both source links and their independent attribution remain stored

#### Scenario: Outcome listing applies explicit filters and positive bounds

- **WHEN** outcomes are listed by source run, kind, evidence state, external
  id, or resolvable branch with a numeric limit
- **THEN** matching records return newest first under a positive default and
  maximum bound
- **AND** an explicit run filter takes precedence over branch resolution
- **AND** zero, negative, invalid, or excessive limits cannot bypass the
  positive maximum

#### Scenario: Gate-event status remains independent

- **WHEN** an outcome cites a gate event and either record changes evidence
  status
- **THEN** the other record remains unchanged until its own authorized
  transition is explicitly invoked

#### Scenario: Retraction or orphaning preserves history

- **WHEN** authorized evidence retracts an attestation or proves an accepted
  external artifact is no longer present
- **THEN** a retracted or orphaned transition is appended
- **AND** the original attestation, acceptance proof, and source attribution
  remain available to authorized audit readers

## REMOVED Requirements

### Requirement: Recorded outcome events are persistent unverified evidence records

**Reason:** The same `outcome_event` registry is upgraded from a permanently
unverified row shape to an explicit append-only evidence lifecycle supporting
both user attestations and receipt-bound handoffs. Keeping the old requirement
alongside the replacement would create two contradictory owners for one
registry.

**Migration:** Existing rows migrate to the replacement requirement as
user-attested evidence with their original ids, run/type/evidence/payload/note,
timestamps, and nullable verification fields preserved. Existing callers keep
the `record_outcome`, `get_outcome`, and `list_outcomes` routes while receiving
the extended shape and positive list bounds.
