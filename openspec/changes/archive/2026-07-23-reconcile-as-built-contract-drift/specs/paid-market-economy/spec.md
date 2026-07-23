## ADDED Requirements

### Requirement: Payment-core conversions produce integers while legacy bids permit non-integer scalars
The payments core SHALL construct `MicroToken` through Python's `int` boundary
after rejecting values that compare below zero, and subtraction below zero
SHALL raise. Current money-action transports SHALL also call `int(...)`; a
fractional JSON number can therefore be truncated and `True` becomes `1`, while
`False` becomes `0` and mutating payment actions subsequently reject converted
amounts less than or equal to zero. A fractional string that `int(...)` cannot
parse SHALL be rejected. `NodeBid.bid` SHALL preserve the caller/YAML scalar
type without runtime coercion, so float bids are permitted, while v1 settlement
serialization SHALL coerce `bid_amount` to float.

#### Scenario: negative payment-core money is rejected
- **WHEN** code constructs `MicroToken(-1)` or subtracts past zero
- **THEN** a `ValueError` is raised

#### Scenario: current transport conversion can truncate a numeric fraction
- **WHEN** a money action receives a positive fractional JSON number such as `1.5`
- **THEN** current `int(...)` conversion passes `1` to the action rather than rejecting the fraction at transport
- **AND** a converted amount less than or equal to zero is rejected by the mutating payment action
- **AND** a fractional string such as `"1.5"` is rejected because `int(...)` cannot parse it

#### Scenario: legacy bid storage permits float amounts
- **WHEN** a `NodeBid` receives and serializes a fractional float bid
- **THEN** its runtime/YAML representation preserves that supplied scalar type
- **AND** a v1 settlement derived from it serializes `bid_amount` as a float

### Requirement: Settlement recording rejects pre-existing paths sequentially but is not race-atomic
`record_settlement_event` SHALL validate `outcome_status`, derive the v1
repo-root settlement path, reject a path that already exists, and then write the
YAML record with ordinary `Path.write_text`. This check-then-write boundary
SHALL protect sequential calls but SHALL NOT provide an atomic single-winner
guarantee for concurrent writers that both observe the path as absent.

#### Scenario: sequential double-settle is refused
- **WHEN** a settlement path already exists and recording is attempted again
- **THEN** `SettlementExistsError` is raised
- **AND** the existing record is left unchanged

#### Scenario: invalid outcome status is rejected
- **WHEN** a settlement is recorded with an `outcome_status` other than `succeeded` or `failed`
- **THEN** a `ValueError` is raised and no file is written

#### Scenario: concurrent creation has no single-winner guard
- **WHEN** two writers both pass the path-existence check before either ordinary write completes
- **THEN** the current recorder does not guarantee a single winner
- **AND** a later write may replace the earlier record

## REMOVED Requirements

### Requirement: All money amounts are integer MicroTokens, never floats
**Reason**: Positive fractional JSON numbers are coerced through `int(...)`, legacy node bids preserve caller/YAML scalar types, and v1 settlement serialization coerces the bid amount to float.
**Migration**: Use the accurate payment-core/legacy-boundary requirement above; the separate hardening lane owns strict parsing, typed bid coercion, and integer migration.

### Requirement: Settlement records are immutable and write-once
**Reason**: The current `exists()` followed by ordinary `write_text` rejects sequential overwrite but is vulnerable to concurrent check-then-write races.
**Migration**: Use the sequential-protection requirement above; the separate hardening lane owns exclusive atomic creation and race tests.
