## ADDED Requirements

### Requirement: Authority-owner exits commit canonical authority atomically

When background authority owner records share a transactional store with canonical bindings and attempts, the system SHALL persist and transition the owner, binding, and attempt facts in one atomic transaction. A recovery exit SHALL apply only to an owner with a present attempt fence and SHALL compare-and-swap that exact canonical same-attempt fence before the owner becomes claimable. Queue-owner reauthorization SHALL validate the exact canonical current owner and applicable binding/attempt fences, validate the newer canonical binding, and insert or exactly replay a fresh reserved attempt before the owner becomes claimable. Source-owner reauthorization MAY omit a replacement attempt only after validating the newer canonical binding and any prior attempt fence; the rotated binding SHALL leave the prior attempt stale/non-runnable and the owner SHALL NOT revive or mutate it. Resolver-supplied records MUST NOT become authoritative merely because they are typed or self-consistent. A closed missing-authority hold reason SHALL treat exact canonical absence as evidence and MAY atomically persist only the held owner while preserving any missing-row fence as non-authorizing audit context. Unexpected missing, stale, malformed, conflicting, or non-canonical state, and any failure between writes, SHALL leave the owner held and SHALL NOT expose a pickable owner with an absent or stale attempt.

#### Scenario: Recovery rolls back as one unit

- **WHEN** same-attempt recovery updates the attempt but owner persistence fails before commit
- **THEN** the transaction rolls back both writes
- **AND** the canonical attempt and owner remain at their exact held fences

#### Scenario: Reauthorization cannot publish a resolver-only attempt

- **WHEN** authenticated reauthorization resolves a fresh attempt that is absent from canonical storage
- **THEN** the store validates it against the newer canonical binding and inserts it in the same transaction as the owner transition
- **AND** an invalid or conflicting attempt prevents the owner from returning to a pickable state

#### Scenario: Source reauthorization may wait for later attempt issuance

- **WHEN** a source-owned hold is authenticated against a newer canonical binding without resolving a replacement attempt
- **THEN** the store validates the newer binding and any prior attempt fence before returning the source owner to active
- **AND** binding rotation leaves the prior attempt stale and non-runnable without reviving or mutating it

#### Scenario: Exact absence is valid hold evidence

- **WHEN** a closed missing-authority classification matches an absent canonical binding or attempt row
- **THEN** the store atomically persists the non-runnable held owner without inventing the missing record
- **AND** any preserved missing-row fence remains non-authorizing audit context

#### Scenario: Stale canonical authority wins over typed evidence

- **WHEN** the owner, current binding, current attempt, or replacement binding no longer matches the fenced record
- **THEN** the transition makes no write and returns the canonical conflict
- **AND** no resolver snapshot repairs or overrides the stale fence

#### Scenario: Recovery requires a present attempt

- **WHEN** a held owner has no attempt fence or the fenced attempt is absent
- **THEN** same-attempt recovery is refused without changing the owner
- **AND** the owner remains held for authenticated repair or reconciliation

#### Scenario: Corrupt storage fails closed

- **WHEN** an owner, binding, or attempt row has malformed JSON, a digest mismatch, or an indexed-field mismatch
- **THEN** the transition aborts without changing any owner, binding, or attempt record

#### Scenario: The persistence correction remains dark

- **WHEN** the owner store is installed
- **THEN** no BranchTask, queue, dispatcher, provider, public API, or runtime path imports or activates it until the separate integration requirements are complete
