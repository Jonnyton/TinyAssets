## ADDED Requirements

### Requirement: Recorded outcome events are persistent unverified evidence records

The `extensions` outcome registry SHALL persist each accepted outcome as a
unique `outcome_event` row with a caller-supplied non-empty run ID, one of
`published_paper`, `merged_pr`, `deployed_app`, `won_competition`, or `custom`,
a generated outcome ID and recorded timestamp, and optional evidence URL,
gate-event linkage, JSON payload, and note. Recording MUST leave `verified_at`
and `verified_by` unset, MUST NOT require that the run ID already exists, and
MUST NOT invoke an evaluator, prober, or produce `EvalResult`; generic outcome
adapters remain owned by `evaluation-runtime-and-scenarios` and run only when a
caller explicitly invokes them.

#### Scenario: An outcome round-trips without ambient verification

- **WHEN** a caller records a supported outcome type against a non-empty run ID
  that is not present in the run store, with optional evidence and payload
- **THEN** the registry returns a generated outcome ID and timestamp and `get_outcome`
  retrieves the stored run ID, type, evidence, linkage, payload, and note
- **AND** the retrieved `verified_at` and `verified_by` fields remain unset
- **AND** recording performs no network probe or evaluator call

#### Scenario: An unsupported outcome type is rejected before persistence

- **WHEN** `record_outcome` receives an outcome type outside the five supported
  values
- **THEN** it returns an error containing the valid type set
- **AND** it writes no outcome row for that request

#### Scenario: Outcome listing applies current filters and bounds

- **WHEN** `list_outcomes` is called with a run ID and/or outcome type, or with
  a branch whose runs can be resolved and no explicit run ID
- **THEN** it returns matching records newest first, defaults an invalid limit
  to 50, and caps a positive requested limit at 200 rows
- **AND** an unresolved branch filter returns an empty list rather than
  inventing outcome records

#### Scenario: Explicit run filtering takes precedence over branch filtering

- **WHEN** `list_outcomes` receives both `run_id` and `branch_def_id`
- **THEN** the current handler filters on the explicit run ID and does not
  resolve or apply the branch filter

#### Scenario: A negative outcome limit is not safely bounded

- **WHEN** `list_outcomes` receives a negative numeric limit
- **THEN** the current handler passes that negative value to SQLite rather than
  clamping it to a positive bound
- **AND** the query can therefore return more than 200 records under SQLite's
  negative-limit semantics
