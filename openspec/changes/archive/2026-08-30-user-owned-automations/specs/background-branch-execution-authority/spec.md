## ADDED Requirements

### Requirement: Background execution authority derives from the current serving assignment at run time
Authority to run a background branch SHALL be derived, at the moment the run is due, from the
universe's current provider assignment and credential custody and from the owner's current admin
ACL; it SHALL NOT be pinned to an executor runtime identity, to a provider recorded at
preparation time, or to any host-supplied enrollment manifest.

#### Scenario: Provider rebound since preparation
- **WHEN** the owner rebinds the universe's serving provider after an automation was created
- **THEN** the next due run launches on the rebound provider without re-preparation

#### Scenario: Owner authority revoked
- **WHEN** the owner no longer holds an admin ACL on the universe when a run comes due
- **THEN** the run is refused, the refusal is recorded against the automation, and no credential is used

### Requirement: A refused run is recorded and never aborts the pump
When a due run cannot be authorized, the daemon SHALL record exactly one refusal for that
automation and SHALL continue with other due runs; a single principal's failure SHALL NOT stop
execution for other universes.

#### Scenario: One bad principal among many
- **WHEN** one universe's run fails authorization and two other universes have due runs
- **THEN** one refusal row exists for the failing automation and the other two runs launch
