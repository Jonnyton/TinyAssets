## ADDED Requirements

### Requirement: OpenSpec Drain Starts With The Interactive Windows Session

The development coordination runtime SHALL provide an idempotent current-user
Windows sign-in task that launches exactly one drain watchdog and one tray
indicator without requiring a daily prompt or terminal. It MUST use the
interactive user boundary rather than SYSTEM startup because provider
subscription credentials and the notification area belong to that session.

#### Scenario: User signs in after boot

- **WHEN** the configured Windows user signs in
- **THEN** Task Scheduler launches the drain tray/watchdog automatically
- **AND** duplicate task invocations do not start another watchdog

#### Scenario: Installer runs more than once

- **WHEN** the host installs the autostart integration again
- **THEN** the existing task is replaced with the current controller path
- **AND** no duplicate scheduled task remains

### Requirement: Drain Watchdog Preserves Identity Across Abrupt Shutdown

The drain watchdog SHALL attach to a live unfinished drain, SHALL resume an
unfinished drain whose recorded controller is dead using the same run directory
and exact identity, and SHALL start a fresh bounded run only when no unfinished
run exists. It MUST NOT automatically restart fatal or failure-budget terminal
outcomes.

#### Scenario: Existing manual drain is alive

- **WHEN** the watchdog starts while an unfinished drain lock belongs to a live
  controller
- **THEN** it attaches to that run for health monitoring
- **AND** it does not dispatch another worker

#### Scenario: Computer was shut down abruptly

- **WHEN** the newest drain has no `ended_at` and its recorded controller PID is
  dead
- **THEN** the watchdog resumes that run with stale-lock recovery
- **AND** replacement workers retain the original drain identity

#### Scenario: Previous run failed terminally

- **WHEN** the latest completed run ended at its failure budget or a fatal peer
  error
- **THEN** the watchdog reports down
- **AND** it waits for an explicit restart request instead of spending more
  subscription calls

#### Scenario: Clean budget ends during the signed-in session

- **WHEN** a supervisor ends at its runtime or slice budget while the watchdog
  remains active
- **THEN** the watchdog may start a new finite supervisor run
- **AND** it still runs only one worker at a time

### Requirement: Drain Health Is Continuously Visible And Actionable

The Windows integration SHALL maintain atomic health state and a system-tray
indicator that distinguishes running, waiting/recovering, and down/failure
states. The tray MUST provide actions to open status/logs, request a restart,
stop until the next sign-in, and exit only the indicator.

#### Scenario: Worker is active

- **WHEN** the watchdog observes a live controller with running state
- **THEN** the tray displays healthy/running status
- **AND** its tooltip identifies the active drain

#### Scenario: Drain is blocked or recovering

- **WHEN** the controller is idle, blocked, stopping, or being resumed
- **THEN** the tray displays a waiting/warning state rather than false healthy
  progress

#### Scenario: Drain is down

- **WHEN** health is stale, the watchdog exits unexpectedly, or the supervisor
  reaches a terminal failure
- **THEN** the tray displays an error/down state
- **AND** the diagnostic message and status folder remain accessible

#### Scenario: Host closes the tray icon

- **WHEN** the host selects exit indicator
- **THEN** the tray process exits
- **AND** it does not stop the watchdog or active drain
