## ADDED Requirements

### Requirement: Every universe birth initializes deny-all engine authority

Every operation that makes a new universe observable as living SHALL persist
`engine_source="unassigned"`,
`engine_assignment_state="unassigned"`,
`engine_assignment_generation=0`, and `allowed_providers=[]` within the same
atomic birth transaction, including public, first-contact, internal migration,
and development creation. Failure to persist this state SHALL roll back the
partial universe before it can be indexed, selected, bound as home, or used for
provider work.

This invariant applies independently of the public birth contract owned by the
active `universe-creation` change. A caller-selected/internal ID exception,
different public entry point, or successful identity/soul seeding MUST NOT
omit engine authority initialization.

#### Scenario: public birth is provider deny-all before visibility
- **WHEN** a public or first-contact birth succeeds
- **THEN** unassigned source/state, generation zero, and an empty provider ceiling are durable before the universe is indexed or bound

#### Scenario: internal birth receives the same authority state
- **WHEN** authorized migration or development tooling creates a universe through its internal ID exception
- **THEN** the same unassigned generation-zero deny-all state is persisted

#### Scenario: authority initialization failure rolls birth back
- **WHEN** any birth path fails to persist engine authority
- **THEN** the partial universe is removed before the error returns
- **AND** no bare or authority-uninitialized directory is observable as living

### Requirement: Provider authority holds render the canonical setup-required envelope

The universe action layer SHALL catch `ProviderAuthorityHeldError` from any
first-contact or `converse` provider phase and map it directly to the existing
canonical `engine_setup_required_payload`. This mapping SHALL NOT require an
`AllProvidersExhaustedError`, non-null provider chain state, provider attempt,
or credential lookup. It SHALL preserve a completed birth/home binding and
return `status=held`, `reason=setup_required`, the materialized `universe_id`,
typed missing setup elements, and requester-facing supported setup paths
without generic failure prose.

Runtime SHALL NOT enable newborn deny-all state or provider-authority
enforcement until this exact typed-held mapping has a failing-then-passing
test and rendered connector proof.

#### Scenario: pre-provider authority hold renders setup
- **WHEN** a newborn or existing universe raises `ProviderAuthorityHeldError` before provider-chain access
- **THEN** the action returns the canonical setup-required payload without requiring chain state
- **AND** `converse` relays that structured hold rather than generic failure prose

#### Scenario: bare deny-all is not misclassified as exhaustion
- **WHEN** unassigned source/state and `allowed_providers=[]` hold first-contact execution
- **THEN** no provider attempt or exhaustion evidence is required
- **AND** the completed universe remains available for later supported engine setup
