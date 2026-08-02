## ADDED Requirements

### Requirement: Authority-owner exits commit canonical authority atomically

When background authority owner records share a transactional store with canonical bindings and attempts, the system SHALL persist and transition the owner, binding, and attempt facts in one atomic transaction. A recovery exit SHALL compare-and-swap the exact canonical same-attempt fence before the owner becomes claimable. A reauthorization exit SHALL validate the exact canonical current owner and binding/attempt fences, validate the newer canonical binding, and insert or exactly replay the fresh reserved attempt before the owner becomes claimable. Resolver-supplied records MUST NOT become authoritative merely because they are typed or self-consistent. Missing, stale, malformed, conflicting, or non-canonical state, and any failure between writes, SHALL leave the owner held and SHALL NOT expose a pickable owner with an absent or stale attempt.

#### Scenario: Recovery rolls back as one unit

- **WHEN** same-attempt recovery updates the attempt but owner persistence fails before commit
- **THEN** the transaction rolls back both writes
- **AND** the canonical attempt and owner remain at their exact held fences

#### Scenario: Reauthorization cannot publish a resolver-only attempt

- **WHEN** authenticated reauthorization resolves a fresh attempt that is absent from canonical storage
- **THEN** the store validates it against the newer canonical binding and inserts it in the same transaction as the owner transition
- **AND** an invalid or conflicting attempt prevents the owner from returning to a pickable state

#### Scenario: Stale canonical authority wins over typed evidence

- **WHEN** the owner, current binding, current attempt, or replacement binding no longer matches the fenced record
- **THEN** the transition makes no write and returns the canonical conflict
- **AND** no resolver snapshot repairs or overrides the stale fence

#### Scenario: Corrupt storage fails closed

- **WHEN** an owner, binding, or attempt row has malformed JSON, a digest mismatch, or an indexed-field mismatch
- **THEN** the transition aborts without changing any owner, binding, or attempt record

#### Scenario: The persistence correction remains dark

- **WHEN** the owner store is installed
- **THEN** no BranchTask, queue, dispatcher, provider, public API, or runtime path imports or activates it until the separate integration requirements are complete
