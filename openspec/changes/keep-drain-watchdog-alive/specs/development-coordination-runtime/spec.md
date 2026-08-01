## ADDED Requirements

### Requirement: Local OpenSpec Drain Observability Self-Heals During The Interactive Session
The development coordination runtime SHALL recover a failed local drain watchdog or tray during the configured interactive Windows session without starting a second watchdog, supervisor, or worker. Recovery attempts MUST preserve atomic health publication and MUST NOT report stale, idle, blocked, or recovering state as healthy running progress.

#### Scenario: Health publication is transiently contended
- **WHEN** Windows prevents the watchdog from atomically replacing the health document after its bounded replace retries
- **THEN** the watchdog records the publication failure and continues monitoring the same supervisor
- **AND** the last complete health document remains intact and becomes stale until a later atomic publication succeeds

#### Scenario: Watchdog dies while tray remains alive
- **WHEN** tray health is missing or stale beyond the health freshness threshold
- **THEN** the tray makes a bounded-cadence watchdog relaunch attempt
- **AND** watchdog and supervisor locks prevent a duplicate monitor, supervisor, or worker
- **AND** the tray remains down until fresh health proves recovery

#### Scenario: Tray host dies after sign-in
- **WHEN** the current-user scheduled tray action is no longer running during the configured interactive session
- **THEN** a periodic hidden current-user trigger relaunches the tray without waiting for another sign-in
- **AND** the task's single-instance policy prevents a second tray while the original remains alive

#### Scenario: Supervisor is healthy but idle
- **WHEN** self-healing restores fresh watchdog health for a live idle supervisor
- **THEN** the tray reports waiting rather than false running progress
