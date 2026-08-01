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

#### Scenario: Host intentionally stops the drain for the session
- **WHEN** `stop.request` records the tray's explicit stop-until-next-sign-in action
- **THEN** neither stale-health recovery nor the periodic guard clears the marker or relaunches the watchdog during that session
- **AND** the next sign-in startup may clear the prior-session marker and resume the drain

#### Scenario: Tray host dies after sign-in
- **WHEN** the current-user scheduled tray action is no longer running during the configured interactive session
- **THEN** a separate periodic hidden current-user guard task relaunches the tray without waiting for another sign-in
- **AND** the named tray mutex and task single-instance policies prevent a second tray while the original remains alive

#### Scenario: Live observer integration is reinstalled
- **WHEN** the installer replaces an older running tray/watchdog integration
- **THEN** it recycles only processes matching the exact observer executable-and-argument grammar while preserving the live supervisor and unrelated diagnostics
- **AND** it returns success only after fresh versioned health and exactly one tray, watchdog, and supervisor prove the new runtime is active

#### Scenario: Integration is reinstalled while session stop is active
- **WHEN** `stop.request` exists during reinstall
- **THEN** the installer updates both task definitions without recycling or starting observers
- **AND** it reports that version activation is deferred until the next real sign-in

#### Scenario: Stop action races live reinstall
- **WHEN** a tray stop action and live reinstall overlap
- **THEN** a shared current-session control lock serializes the stop marker mutation and the installer's sample-through-verification transaction
- **AND** the stop is either observed before activation and causes deferral or is applied after activation without being cleared

#### Scenario: Control-lock owner exits unexpectedly
- **WHEN** a tray or installer process exits while owning the control mutex
- **THEN** the next waiter accepts the abandoned ownership transfer, continues exclusively, and releases the mutex on exit

#### Scenario: Supervisor is healthy but idle
- **WHEN** self-healing restores fresh watchdog health for a live idle supervisor
- **THEN** the tray reports waiting rather than false running progress
