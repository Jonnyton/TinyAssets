## ADDED Requirements

### Requirement: Delivery control records do not block either party's erasure
Account deletion SHALL remove indirect delivery attempts and personal two-party
receipts before their scoped link, receiver and run parents, within the existing
satellite-store transaction. Each affected row SHALL be counted once before
deletion. Surviving receivers SHALL remove only the deleted permitted sender.
Unrelated peer records and peer-owned runs SHALL remain intact.

#### Scenario: Either party deletes their account
- **WHEN** a sender or receiver deletes their account after accepting a delivery
- **THEN** the scoped FK children are removed without a foreign-key failure
- **AND** no delivery receipt or permitted-sender reference to that principal remains
- **AND** the other party's independent runs and unrelated connections survive

#### Scenario: A store refuses one deletion
- **WHEN** an integrity failure interrupts the satellite transaction
- **THEN** all that store's deletes and sender-list edits roll back, no counts are committed,
  and the existing account workflow records the unfinished store phase
