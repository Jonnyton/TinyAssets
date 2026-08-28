## ADDED Requirements

### Requirement: The effect budget is reserved before the write and settled on its outcome
Effect quota SHALL be enforced through the receipt reservation lifecycle, not by counting
completed effects alone. Reserving a receipt slot SHALL reserve effect budget and SHALL
refuse when the budget is exhausted, so the limit is enforced **before** the outbound write
occurs. Releasing a reservation after a failed write SHALL release the reserved budget, so a
failed attempt costs the universe nothing. Finalizing a receipt as terminally successful
SHALL commit the reserved budget.

Counting only completed effects SHALL NOT be sufficient: an outbound write is irreversible,
so a budget that moves only after success is an accounting record and not a control.

Reservation SHALL be atomic, so concurrent effects cannot both reserve the last slot. A
replayed or idempotently-deduplicated effect SHALL settle against its existing reservation
rather than taking a second one.

Quota accounting SHALL NOT be able to authorize an effect that the existing authority,
consent, and destination gates would refuse; it may only refuse one they would allow.

#### Scenario: the budget is enforced before the write, not after
- **WHEN** a universe with an exhausted effect budget attempts an outbound write
- **THEN** the reservation is refused and no outbound request is made

#### Scenario: a failed outbound attempt costs nothing
- **WHEN** a reservation is released after the destination rejects the write
- **THEN** the reserved effect budget is returned to the universe

#### Scenario: concurrent effects cannot both take the last slot
- **WHEN** two effects concurrently reserve against a budget with one slot remaining
- **THEN** exactly one reservation succeeds

#### Scenario: a replayed effect settles once
- **WHEN** the same effect is finalized more than once through replay-safe execution
- **THEN** the effect budget reflects exactly one effect

#### Scenario: quota never widens authority
- **WHEN** available effect budget exists but authority or destination consent is absent
- **THEN** the effect is still refused
