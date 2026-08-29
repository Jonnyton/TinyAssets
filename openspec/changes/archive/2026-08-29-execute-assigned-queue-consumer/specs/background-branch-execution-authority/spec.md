## ADDED Requirements

### Requirement: Assigned consumer launches revalidate background authority
Before each provider launch, the system MUST re-read the exact current background binding and attempt, require the task's universe and immutable branch/version/digest, require the current activation epoch and consumer lease, and reject stale, revoked, held, exhausted, expired, or mismatched authority.

#### Scenario: Lease or epoch is stale
- **WHEN** the task lease, background attempt lease, or activation epoch differs from the claimed fence
- **THEN** the provider launch is refused and the attempt is projected to a retryable authority-held condition

#### Scenario: Approved immutable branch roles
- **WHEN** the pinned immutable branch requests only its recorded supported provider roles
- **THEN** those roles may consume the bounded `background_branch_run` authority and no other branch or role can use it
