## ADDED Requirements

### Requirement: Run reads expose honest stored node activity
Authorized run inspection SHALL include compact typed node-activity evidence
derived from existing run events without new execution, credentials, storage,
top-level tools or raw event-detail disclosure. Existing run status, output
retrieval, authorization, pinned universe selection and client envelopes SHALL
remain intact. Missing evidence SHALL remain explicitly unknown.

#### Scenario: A later node fails after a provider returned
- **WHEN** existing events record a completed provider response for one node and a later node fails
- **THEN** the run read includes the earlier node's stored returned-call evidence even without a success-only run aggregate
- **AND** normalized actual-model evidence is distinguished from an unreported model or configuration hint

#### Scenario: A node starts locally but has no returned provider evidence
- **WHEN** an event records local node start and no subsequent returned-call receipt
- **THEN** the read identifies local start and leaves provider acknowledgment and response evidence unknown
- **AND** it does not infer provider silence, non-start, upstream load or stopped execution from an outer timeout

#### Scenario: Timestamps and repeated starts are interpreted honestly
- **WHEN** a node has repeated starts or a return followed by output validation failure
- **THEN** returned-call evidence retains its observation step and time independently of latest node status
- **AND** local elapsed time uses an observed ordered start/terminal pair, not the near-zero span of a terminal record
- **AND** missing, invalid or nonfinite timing is unknown rather than fabricated

#### Scenario: Event details contain generated content or sensitive payloads
- **WHEN** stored details contain prompts, previews, responses, code, arbitrary errors, credentials or nested provider objects
- **THEN** the new activity projection excludes those raw fields and exposes only bounded typed metadata and strict normalized execution receipts
- **AND** exact authorized output remains available through the existing output read rather than being copied into diagnostic metadata

#### Scenario: A caller supplies an unauthorized or foreign-scope run
- **WHEN** a caller lacks run-read authority or a served run identifier is outside the pinned universe
- **THEN** the existing refusal occurs before activity is returned
- **AND** public visibility does not widen a served agent's pinned selector

#### Scenario: Large or legacy workflows are inspected
- **WHEN** a run has many nodes or legacy events with incomplete metadata
- **THEN** no new workflow-size restriction is imposed and no node is silently omitted merely for exceeding a diagnostic count
- **AND** per-node metadata remains bounded, existing result envelopes remain faithful and bounded, and unavailable facts are marked unknown
