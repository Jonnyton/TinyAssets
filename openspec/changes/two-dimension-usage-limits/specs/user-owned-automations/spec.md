# user-owned-automations (delta)

## REMOVED Requirements

### Requirement: Automations and schedules are limited by usage, not by count or cadence floor

**Reason:** the half of this requirement that charged registration and every
fire to a rolling admission window is a rate meter, which founder directive
2026-09-30 replaces with seats and storage. The half that removed structural
caps — no automation ceiling, no per-owner schedule count, no cadence floor —
is kept and respecified below, because "limit USAGE, not shape" still holds.

**Migration:** `run_rate_limited` and `usage_limited` are deleted, not
renamed. A due run that cannot start now WAITS for a seat; it is never refused
and never leaves a rate-limit reason on the automation's projection.

## ADDED Requirements

### Requirement: A due automation run waits for a seat instead of being rate-refused

Registering an automation, a node wake, an event wake or a schedule SHALL NOT be charged to any usage window and SHALL NOT be refused for usage. A due run SHALL resolve its own per-agent overlap policy first, and then — if it is going to run — SHALL wait for one of its universe's seats. It SHALL NOT be refused, skipped or dropped for want of a seat, and the owner's projection SHALL show it as waiting for a free seat with the number running, carrying the inline upgrade link. There SHALL continue to be no per-universe automation ceiling, no per-owner schedule or subscription count, and no cadence floor beyond the tick loop's own period.

#### Scenario: A due run waits rather than being refused
- **WHEN** an automation becomes due while its universe's background seats are all held
- **THEN** it waits, starts when a seat frees, and its projection shows "waiting for a free seat" with the number running, not a rate-limit reason

#### Scenario: A fast cadence on a busy universe still only ever waits
- **WHEN** an automation on a one-second interval becomes due repeatedly while no seat is free
- **THEN** the missed instants collapse into one owed run per its overlap policy, and nothing is recorded as rate-limited

#### Scenario: Registration is never metered
- **WHEN** an owner registers many automations, wakes and schedules in quick succession
- **THEN** every registration succeeds and none is refused for usage
