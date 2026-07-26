## ADDED Requirements

### Requirement: Accepted-Market Remote Readiness Stores A Non-Executable Activation Mandate, Not A Future Job Grant

For `engine_source="accepted_market"`, the provider-routing assignment owner SHALL
publish `engine_assignment_state="remote_ready"` with
`allowed_providers=[]` only through its atomic activation transaction. That
transaction SHALL bind the exact accepted-agreement reference, current
non-executable B13 activation-mandate reference, assignment generation, and
idempotency identity. The mandate is the B13-side readiness fact referenced by
the existing provider-routing B2/B13 language; it is not a B2 grant and grants
no job, capsule, host, lease, provider, funding, capacity, or execution
authority.

The assignment owner MUST NOT mint, request, store, or require a future-job B2
during activation. A B2 exists only after a later `converse` establishes its
exact demand/job/capsule and B13 composes every current owner-native
allocation, capacity, logical-accounting, real-fund, S14/B36, claimant-host,
and execution-admission result. A per-job B2 SHALL remain job-scoped execution
authority and MUST NOT become reusable universe assignment configuration.

#### Scenario: Activation mandate permits remote-ready without job authority

- **WHEN** the activation transaction has a current accepted agreement and provisional non-executable B13 mandate for the exact universe and atomically commits their references
- **THEN** the mandate reference becomes current and assignment publishes `accepted_market + remote_ready + []`
- **AND** no B2, job, capsule, host, lease, capacity, funding, or execution authority is created or stored

#### Scenario: Future-job B2 cannot be pre-minted at activation

- **WHEN** activation lacks a concrete later message, job, demand, capsule, allocation, claimant host, capacity, funding, or admission result
- **THEN** provider routing requires only the current non-executable activation mandate for remote-ready state
- **AND** refuses any attempt to store a speculative or reusable B2 as assignment authority

### Requirement: Accepted-Market Pre-Routing Delegates Per-Job Composition Without Converting The Mandate Into Execution

For each accepted-market `converse`, the pre-routing seam SHALL revalidate the
current assignment generation, agreement, and non-executable activation
mandate, then delegate the exact concrete job to B13's per-job composition
path before ordinary provider routing. The seam MUST NOT convert the activation
mandate itself into remote execution. Dispatch may proceed only when B13
returns the fresh matching per-job B2 after all named owner-native results and
independent execution admission are current.

If the agreement/mandate is absent, expired, revoked, fenced, cancelled,
superseded, overspent, or inconsistent, the assignment owner SHALL atomically
downgrade stale `remote_ready` to `held + []` and expose the accepted-market
repair/renewal cause. If only per-job composition fails, that job remains held
and no ordinary provider chain or maintainer resource is consulted.

#### Scenario: Current mandate routes to per-job composition

- **WHEN** a current accepted-market assignment receives a concrete `converse`
- **THEN** provider routing bypasses ordinary chains and delegates the concrete job to B13 for fresh owner-native composition and exact B2 production
- **AND** the stored activation mandate remains non-executable

#### Scenario: Missing per-job B2 holds one job without widening

- **WHEN** assignment mandate is current but B13 cannot produce the exact per-job B2
- **THEN** the concrete job holds with a typed accepted-market cause
- **AND** no ordinary provider, maintainer quota, local, BYOC, free, desktop, or environment fallback is attempted

#### Scenario: Stale mandate downgrades assignment

- **WHEN** the assignment's agreement or activation mandate is no longer current
- **THEN** the assignment owner atomically publishes `held + []` and the repair/renewal path
- **AND** neither historical per-job B2 nor a mutable market row preserves remote-ready state
