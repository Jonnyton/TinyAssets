## ADDED Requirements

### Requirement: Storage utilization exposes a reconciled accounting equation
`get_status.storage_utilization` SHALL expose `volume_bytes_used`,
`attributed_bytes`, `unattributed_bytes`, `attributed_fraction`, and
`accounting_complete` in addition to the existing volume and per-subsystem
fields. For a normal under-attributed snapshot, `attributed_bytes` SHALL equal
the sum of `per_subsystem[*].bytes` and `attributed_bytes +
unattributed_bytes` SHALL equal `volume_bytes_used`.

#### Scenario: Most used bytes are not itemized
- **WHEN** the backing filesystem has 90 bytes used and the itemized subsystems total 10 bytes
- **THEN** `attributed_bytes` is 10 and `unattributed_bytes` is 80
- **AND** `attributed_fraction` is approximately 0.1111
- **AND** `accounting_complete` is false

### Requirement: Universe overlays cannot stale the accounting fields
The storage accounting equation SHALL be recomputed after `get_status` replaces
root placeholder sizes with the requested universe's checkpoint, activity log,
and output sizes.

#### Scenario: Requested universe has a checkpoint DB
- **WHEN** the requested universe has a non-zero checkpoint DB
- **THEN** its bytes are included in both `per_subsystem.checkpoint_db.bytes` and `attributed_bytes`
- **AND** the final `unattributed_bytes` still reconciles to `volume_bytes_used`

### Requirement: Pressure level never claims green from unknown inputs
`pressure_level` SHALL be one of `unknown`, `ok`, `warn`, or `critical`.
Unavailable volume measurements and incomplete accounting below the existing
volume thresholds SHALL produce `unknown`, not `ok`. The existing thresholds
SHALL remain 80% for `warn` and 95% for `critical`.

#### Scenario: Incomplete accounting below warning threshold
- **WHEN** the volume is below 80% used but some used bytes are unattributed
- **THEN** `pressure_level` is `unknown`

#### Scenario: Near-full volume
- **WHEN** the volume is at or above 95% used
- **THEN** `pressure_level` is `critical`
- **AND** it is never `ok`, regardless of attribution completeness

#### Scenario: Filesystem usage cannot be read
- **WHEN** the filesystem usage probe fails
- **THEN** `pressure_level` is `unknown`
- **AND** `accounting_complete` is false

### Requirement: Policy remains out of scope
This accounting change SHALL NOT configure cap values, add retention or
reclamation behavior, or synthesize a growth estimate without historical data.

#### Scenario: No growth history or cap configuration exists
- **WHEN** status is requested in the current deployment configuration
- **THEN** `growth_estimate` remains `null`
- **AND** cap fields preserve their configured/unconfigured values
