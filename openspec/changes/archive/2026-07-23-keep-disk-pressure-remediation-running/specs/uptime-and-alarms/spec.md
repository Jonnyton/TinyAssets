## RENAMED Requirements

- FROM: `Disk-pressure timer composes alert, rotation, and disposable-host reclamation with a stop-on-error seam`
- TO: `Disk-pressure timer preserves ordered alert, rotation, and disposable-host remediation`

## MODIFIED Requirements

### Requirement: Disk-pressure timer preserves ordered alert, rotation, and disposable-host remediation
The system SHALL provide a persistent systemd timer definition with five-minute post-boot, one-hour-since-active, and minute-27 calendar triggers plus a 180-second oneshot service sourcing `/etc/tinyassets/env`; the repository artifact alone SHALL NOT claim that a particular host installed or enabled it. The service SHALL declare three sequential commands in this order: disk alerting, run-transcript rotation, and disk auto-prune. Disk alerting SHALL return 1 at or above `DISK_WARN_PCT` (default 80) whether it opens an issue, lacks a token, or runs dry, and the service SHALL accept status 1 so that the ordered rotation and auto-prune commands still execute. Auto-prune SHALL trigger at or above `DISK_AUTOPRUNE_PCT` (default 85), run Docker system prune and builder prune without volumes plus a best-effort three-day journal vacuum, and treat a completed non-zero cleanup as logged but non-fatal. Unexpected process statuses other than 0 or 1 SHALL still fail the unit.

#### Scenario: Below warning threshold reaches all three commands
- **WHEN** the watched path is below the warning threshold and earlier commands otherwise succeed
- **THEN** disk alerting returns 0 and systemd proceeds to transcript rotation and the auto-prune threshold check

#### Scenario: Pressure alert preserves the cleanup chain
- **WHEN** disk usage is at or above the warning threshold
- **THEN** `disk_watch.py` returns 1 after its issue or warning path
- **AND** systemd accepts status 1 and proceeds to transcript rotation and auto-prune in their declared order

#### Scenario: Unexpected failure still fails the unit
- **WHEN** a service command returns a status other than 0 or 1
- **THEN** systemd treats the oneshot as failed

#### Scenario: Auto-prune reclaims disposable host data without volumes
- **WHEN** execution reaches auto-prune at or above its threshold
- **THEN** it invokes Docker system and builder prune without `--volumes`, then attempts a three-day journal vacuum

#### Scenario: Missing watched path is non-fatal
- **WHEN** disk alerting or auto-prune cannot stat its configured path
- **THEN** that script logs a warning and returns 0 rather than failing the timer solely because the path is absent
