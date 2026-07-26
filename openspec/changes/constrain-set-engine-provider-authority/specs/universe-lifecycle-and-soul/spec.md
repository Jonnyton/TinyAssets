## ADDED Requirements

### Requirement: Every universe birth initializes deny-all engine authority

When the effective V2 gate applies, every universe birth SHALL initialize
deny-all engine authority. The gate applies when
`TINYASSETS_PROVIDER_AUTHORITY_V2` is true or the new universe's canonical ID
is present in configured/registered server-owned isolated-canary state. For
public/first-contact birth whose ID is generated internally, an authenticated
principal pre-listed in the separate server-owned canary-principal set SHALL
be preflight-proven to have no existing home/universe, and the server SHALL
register the generated ID durably before target initialization or visibility.
Every operation that makes such a universe observable as living SHALL persist
`engine_source="unassigned"`, `engine_assignment_state="unassigned"`,
`engine_assignment_generation=0`, and `allowed_providers=[]` within the same
atomic birth transaction, including public, first-contact, internal migration,
and development creation. Failure to persist this state SHALL roll back the
partial universe before it can be indexed, selected, bound as home, or used
for provider work.

While the global flag is false and the canonical ID is absent from
configured/registered canary state,
birth SHALL preserve the shipped defaults: it writes neither target
`engine_source="unassigned"` nor `allowed_providers=[]`, and optional
assignment state/generation remain absent. This keeps current readiness,
vault/source classification, and bare-exhaustion behavior unchanged. Caller
data cannot add a principal or ID to canary state, and an existing user
universe MUST NOT be migrated merely to obtain pre-flip proof.

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
- **WHEN** any birth path succeeds while the global flag is false and its canonical ID is absent from configured/registered canary state
- **THEN** it does not write target unassigned source/state/generation or an empty ceiling
- **AND** shipped default, vault/source readiness, and bare-exhaustion behavior remain unchanged

#### Scenario: isolated canary birth proves target initialization
- **WHEN** an isolated acceptance-test ID is pre-listed by server-owned canary configuration while the global flag is false
- **THEN** its birth persists the same target unassigned generation-zero deny-all state
- **AND** no caller-selected or existing user universe can opt into that behavior

#### Scenario: generated public birth is canary-provable
- **WHEN** an isolated server-listed test principal with no existing home or universe performs public or first-contact birth
- **THEN** the server registers the generated canonical ID before deny-all initialization and visibility
- **AND** later enforcement keys on that registered ID rather than principal alone
