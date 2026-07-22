# Test identity and reset

## ADDED Requirements

### Requirement: Reset is scoped to one identity and repeatable

The platform SHALL provide a reset scoped to a single identity that is safe to run repeatedly, and it
SHALL NOT require a global wipe to return that identity to a first-contact state.

#### Scenario: Resetting one identity leaves another untouched

- **GIVEN** two identities each owning universes
- **WHEN** one identity is reset
- **THEN** that identity returns to first-contact state, and the other identity's universes, the
  branch commons, run history and wiki SHALL be unchanged.

### Requirement: The platform is exercisable as multiple distinct founders

The platform SHALL support presenting as several distinct founders against the live surface, and the
test path SHALL NOT be more privileged than a real user's path.

#### Scenario: A second user cannot reach the first user's universes

- **GIVEN** two distinct authenticated founders
- **WHEN** the second enumerates and reads
- **THEN** the first founder's private universes SHALL NOT be enumerable, readable, or writable by
  the second.

### Requirement: A caller can observe its resolved identity without seeing secrets

The platform SHALL let a caller determine which principal its own request resolved to, reporting only
whether a bearer was present and the resolved subject. It SHALL NOT expose the bearer or token.

#### Scenario: A test establishes identity instead of inferring it

- **GIVEN** a request whose authentication state is unknown to the tester
- **WHEN** the tester asks what principal it resolved to
- **THEN** the platform SHALL report `bearer_present` and the resolved subject, so identity is
  established rather than guessed from cookies or UI.

### Requirement: Status reports the evidence class behind provider auth

Provider authentication status SHALL state the evidence it rests on rather than implying live
verification. When no live probe was performed, the response SHALL NOT read as a live auth check.

#### Scenario: A cached verdict is not reported as a live check

- **GIVEN** a status call made with live probing disabled
- **WHEN** provider auth is reported
- **THEN** the response SHALL identify the evidence as cached, timestamp-derived, deferred, or
  config-presence — and SHALL NOT be phrasable as "passing live auth checks".
