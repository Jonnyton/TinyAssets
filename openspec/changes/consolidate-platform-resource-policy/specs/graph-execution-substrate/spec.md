## ADDED Requirements

### Requirement: Workspace resource observations distinguish allocation and transfer
Resource observations SHALL distinguish observational workspace starts, current
lease allocations, retained workspace bytes and rolling transport reservations.
They SHALL NOT change admission, locks, outbox ownership or authorization.
Unavailable measurements SHALL remain unknown, and a universe-local lock
observation SHALL NOT claim host-global exclusion.

#### Scenario: Released lease remains in a rolling window
- **WHEN** a lease is released but its job/byte observations remain within the hour
- **THEN** live allocation and historical consumption are reported separately

#### Scenario: Broader universe storage is not measured
- **WHEN** only retained workspace bytes are available
- **THEN** evidence labels that coverage rather than claiming total universe storage
