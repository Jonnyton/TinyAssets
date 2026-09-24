# user-owned-automations (delta)

## ADDED Requirements

### Requirement: An automation read shows when it fires next

Every automation projection SHALL include `next_due_at`. It is the instant the
pump will next owe a run, derived from the same trigger rules the pump uses to
decide that a run is due. It SHALL be empty for a paused or retired automation.
An instant at or before the read time SHALL mean the run is owed and starts on
the pump's next poll.

#### Scenario: Interval automation
- **WHEN** an active interval automation is read before its first period elapses
- **THEN** `next_due_at` is its anchor plus one interval, and the pump finds it due at exactly that instant

#### Scenario: Cron automation
- **WHEN** an active cron automation is read
- **THEN** `next_due_at` is the next minute the pump's cron match accepts

#### Scenario: Paused or retired automation
- **WHEN** the automation is paused or retired
- **THEN** `next_due_at` is empty
