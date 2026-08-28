## ADDED Requirements

### Requirement: A terminally successful receipt increments the owning universe's effect meter
Receipt finalization SHALL be the single point at which an effect is counted. A receipt
reaching terminal success SHALL increment the owning universe's effect meter exactly once.
A receipt that fails, is held, is released, or remains pending SHALL NOT increment it, and a
replayed or idempotently-deduplicated receipt SHALL NOT increment it a second time.

The meter increment SHALL NOT be able to authorize an effect: it observes an effect that
already happened and never gates one.

#### Scenario: only terminal success counts
- **WHEN** a receipt is finalized as failed or held
- **THEN** the owning universe's effect meter is unchanged

#### Scenario: a replayed effect counts once
- **WHEN** the same effect is finalized more than once through replay-safe execution
- **THEN** the effect meter reflects exactly one effect

#### Scenario: metering never gates the write
- **WHEN** the effect meter cannot be written
- **THEN** the effect's own outcome and receipt are unaffected
