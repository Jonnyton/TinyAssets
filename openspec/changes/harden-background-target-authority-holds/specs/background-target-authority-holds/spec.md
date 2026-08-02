## ADDED Requirements

### Requirement: Unsafe authority records become one typed non-runnable hold
The dark background target-authority record service SHALL transition the same reserved, claimed, or running attempt record into `target_authority_held` through an exact fence when fresh canonical evidence classifies target authority as missing, stale, revoked, expired, exhausted, unauthorized, source-mismatched, or indeterminate. The transition MUST clear the lease, monotonically advance claimant fencing, preserve immutable attempt identity and budgets, and append no replacement authority record. Queue rows and source-owned holds remain requirements of the parent integration capability and are not implemented by this seam.

#### Scenario: Claimed attempt loses canonical target authority
- **WHEN** fresh resolver and store evidence classify a claimed attempt with one closed hold reason
- **THEN** the exact attempt becomes non-runnable `target_authority_held`
- **AND** its lease is cleared and stale claimant generations cannot mutate it
- **AND** no new attempt, queue row, provider access, or external effect is created

#### Scenario: Stale hold writer loses the race
- **WHEN** two writers hold the same observed attempt fence
- **THEN** at most one exact compare-and-swap is applied
- **AND** the loser receives a typed stale result without overwriting the winner

### Requirement: Hold projections disclose no private authority material
The system SHALL project a held attempt only as its opaque attempt ID, typed lifecycle and reason, binding/claim/lease generations, and one closed permitted-exit class. The projection MUST exclude principal, universe, target/source identifiers, digests, executor identities, resolver details, credentials, bearer values, and timestamps, and MUST NOT authorize any transition.

#### Scenario: Caller reads a held projection
- **WHEN** a held attempt is converted to its public-safe dark projection
- **THEN** the result identifies the closed reason and permitted exit class
- **AND** serialized output contains none of the excluded authority or private fields

### Requirement: Recovery exits only on conclusive same-attempt evidence
The dark service SHALL return a held attempt to reserved work without rotating its binding only when trusted evidence proves the predecessor dead or invalidated and the irreversible boundary not crossed or durably closed. Recovery MUST keep the same attempt and binding identity, advance only attempt claimant fencing, clear the hold reason, remain inside the pinned executor domain, and append no replacement work.

#### Scenario: Dead predecessor is conclusively recoverable
- **WHEN** a held attempt has a dead predecessor and a not-crossed boundary under fresh evidence
- **THEN** the same attempt returns to reserved with advanced claim and lease generations
- **AND** its binding generation, immutable identity, and budgets remain unchanged

#### Scenario: Boundary is indeterminate
- **WHEN** predecessor death is known but the irreversible boundary is indeterminate
- **THEN** the attempt remains held with no mutation
- **AND** the service does not guess, rotate a binding, or append replacement work

### Requirement: Reauthorization consumes one authenticated and exhaustive newer binding
The dark service SHALL exit a held attempt through reauthorization only after the canonical authority store contains an active, authenticated, exactly newer binding generation and fresh resolver evidence proves the same binding ID, authorizer, universe, operation, exact target version/content, source identity/revision/digest/generation, permitted executor domain and constraints, unexpired lifetime, and an attenuation envelope that contains every remaining attempt budget. The attempt update MUST atomically consume that exact binding and resolver fence, advance claimant fencing, clear the hold reason, and refuse stale attempts, skipped generations, changed or unverifiable pins, authority widening, identity transfer, revocation regression, or caller-authored authority.

#### Scenario: Authenticated binding rotation releases the hold
- **WHEN** the exact held attempt observes the canonical next active binding generation and every attempt-bound target, source, executor, expiry, and budget fact revalidates
- **THEN** the same attempt returns to reserved under the new binding digest and generation
- **AND** no second attempt or binding is minted by the hold service

#### Scenario: Forged or non-adjacent binding is supplied
- **WHEN** reauthorization evidence changes or cannot prove any attempt-bound fact, skips a generation, regresses revocation, or is absent from the current store snapshot
- **THEN** the held attempt remains unchanged
- **AND** no projection or caller-built record grants authority

### Requirement: Target-authority holds remain dark until queue activation
This capability SHALL remain private and non-authorizing until separate queue/source integration, cancellation, garbage collection, cap accounting, recovery, and live-activation requirements land. Model or service availability MUST NOT make a BranchTask pickable, start a dispatcher/runtime, access a provider, or change the public MCP surface.

#### Scenario: Dark hold seam is installed
- **WHEN** the target-authority hold model and service are present
- **THEN** existing queue, dispatcher, provider, graph, and public-handle behavior remains unchanged
