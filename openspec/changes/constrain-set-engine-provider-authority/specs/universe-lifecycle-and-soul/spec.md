## ADDED Requirements

### Requirement: Every universe birth initializes deny-all engine authority

After gated cutover, every universe birth SHALL initialize deny-all engine
authority. Once `TINYASSETS_PROVIDER_AUTHORITY_V2` is true, every operation
that makes a new universe observable as living SHALL persist
`engine_source="unassigned"`, `engine_assignment_state="unassigned"`,
`engine_assignment_generation=0`, and `allowed_providers=[]` within the same
atomic birth transaction, including public, first-contact, internal migration,
and development creation. Failure to persist this state SHALL roll back the
partial universe before it can be indexed, selected, bound as home, or used
for provider work.

While the flag is false, birth SHALL preserve the shipped defaults: it writes
neither target `engine_source="unassigned"` nor `allowed_providers=[]`, and
optional assignment state/generation remain absent. This keeps current
readiness, vault/source classification, and bare-exhaustion behavior unchanged.

This invariant applies independently of the public birth contract owned by the
active `universe-creation` change. A caller-selected/internal ID exception,
different public entry point, or successful identity/soul seeding MUST NOT
omit engine authority initialization.

#### Scenario: public birth is provider deny-all before visibility
- **WHEN** a public or first-contact birth succeeds after the cutover flag flips
- **THEN** unassigned source/state, generation zero, and an empty provider ceiling are durable before the universe is indexed or bound

#### Scenario: internal birth receives the same authority state
- **WHEN** authorized migration or development tooling creates a universe through its internal ID exception after cutover
- **THEN** the same unassigned generation-zero deny-all state is persisted

#### Scenario: authority initialization failure rolls birth back
- **WHEN** any birth path fails to persist engine authority
- **THEN** the partial universe is removed before the error returns
- **AND** no bare or authority-uninitialized directory is observable as living

#### Scenario: pre-cutover birth preserves shipped engine semantics
- **WHEN** any birth path succeeds while `TINYASSETS_PROVIDER_AUTHORITY_V2=false`
- **THEN** it does not write target unassigned source/state/generation or an empty ceiling
- **AND** shipped default, vault/source readiness, and bare-exhaustion behavior remain unchanged
