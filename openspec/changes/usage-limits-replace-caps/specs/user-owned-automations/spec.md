# user-owned-automations (delta)

## ADDED Requirements

### Requirement: Automations and schedules are limited by usage, not by count or cadence floor

Registering an automation or a schedule SHALL be charged to the universe's
admission window as an engine edit, and SHALL be refused with a usage reason
when that window is full. This includes a node's wake and an event wake.
There SHALL be no per-universe automation ceiling, no per-owner schedule or
subscription count, and no 300-second cadence floor. An interval SHALL be any
positive number of seconds (a schedule's at least the tick loop's period), and
any valid cron expression SHALL be accepted.

#### Scenario: Registrations are refused by the meter
- **WHEN** a universe's admission window is full
- **THEN** a new automation or schedule is refused with a usage reason and nothing is stored

#### Scenario: A one-minute cadence is a cadence
- **WHEN** an owner registers `* * * * *` or a 60-second interval
- **THEN** it is stored, and each run it fires is charged as a run
