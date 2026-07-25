## ADDED Requirements

### Requirement: Recognized Goal actions use the configured authorization mode and contribution attribution is best-effort
Before dispatching any recognized `goals` action, the surface SHALL call
`require_action_scope("goals", canonical_action)`. Unknown actions SHALL return
the available-action error before authorization or handler dispatch. When
neither `is_auth_required()` nor `resolve_always_writes()` is true (dev/no-auth
mode), the gate SHALL perform no scope enforcement. In resolve-always mode,
including the optional and WorkOS providers, anonymous read-effect actions
SHALL pass, while write actions SHALL require an authenticated identity holding
the fine-grained OAuth scope or coarse effect grant. In legacy full-auth mode every recognized action
SHALL require an authenticated identity and the exact named scope. After a
successful write result, the surface SHALL attempt to append a
`goals.<action>` contribution entry. If that append raises, the surface SHALL
log a warning and return the original successful Goal result rather than
rolling back or failing the mutation.

#### Scenario: unknown action returns before authorization
- **WHEN** a caller supplies an unrecognized Goal action
- **THEN** the surface returns the available-action error without authorization or handler dispatch

#### Scenario: recognized action follows the configured auth mode
- **WHEN** a recognized Goal action reaches `require_action_scope`
- **THEN** dev/no-auth mode performs no scope enforcement
- **AND** resolve-always mode, including the optional and WorkOS providers, admits anonymous reads but requires an authenticated fine-grained scope or coarse effect grant for writes
- **AND** legacy full-auth mode requires authentication and the exact named scope for reads and writes
- **AND** an authorization rejection returns a structured error with `auth_scope_required: true`

#### Scenario: successful write attempts contribution attribution
- **WHEN** an authorized caller completes a Goal write action
- **THEN** the surface attempts to append a `goals.<action>` contribution entry identifying the target

#### Scenario: attribution failure does not fail the Goal mutation
- **WHEN** the Goal handler succeeds but the contribution-ledger append raises
- **THEN** a warning is logged
- **AND** the original successful Goal result is returned without rollback

## REMOVED Requirements

### Requirement: Goal writes are authorization-scoped and appended to the global contribution ledger
**Reason**: Authorization varies by configured provider mode, unknown actions return before the gate, and ledger attribution happens after mutation with every append failure caught rather than rolled back.
**Migration**: Use the best-effort attribution requirement above; the separate hardening lane owns any future atomic or fail-closed attribution contract.
