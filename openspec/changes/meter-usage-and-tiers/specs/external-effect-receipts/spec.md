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

### Requirement: Effect settlement is a single transition-sensitive, exactly-once operation
Effect budget SHALL be settled by one operation keyed by receipt identity that fires only on
an actual transition **into** terminal success. A call that finds the receipt already in
terminal success SHALL NOT settle again, even where the underlying update reports success.

Settlement SHALL cover every path by which an effect reaches terminal success — ordinary
finalization, reconciled finalization, and confirmed-hold activation — so that no success
path can settle twice and none can escape settlement.

Confirmed-hold activation SHALL reserve effect budget before invoking the effect, exactly as
the ordinary path does. A held effect SHALL NOT be able to fire without quota admission.

The ledger write SHALL be atomic with the receipt transition, or SHALL go through a uniquely
keyed outbox. A sequence of "update the receipt, then increment the ledger" SHALL NOT be
treated as exactly-once.

#### Scenario: replaying a finalization does not settle twice
- **WHEN** finalization is applied to a receipt already in terminal success
- **THEN** the effect budget is unchanged

#### Scenario: a reconciled success still settles
- **WHEN** an ambiguous effect later reconciles to success without passing through ordinary finalization
- **THEN** the effect budget settles exactly once for that effect

#### Scenario: a confirmed hold cannot bypass quota
- **WHEN** a held effect is confirmed and activated while the effect budget is exhausted
- **THEN** the effect is refused rather than invoked

#### Scenario: a crash between write and increment does not lose or duplicate the charge
- **WHEN** the process fails between the receipt transition and the ledger write
- **THEN** recovery settles that effect exactly once
