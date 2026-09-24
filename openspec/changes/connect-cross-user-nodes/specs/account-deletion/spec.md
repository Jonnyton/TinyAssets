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

#### Scenario: A deleted sender leaves the receiver its accepted bytes
- **WHEN** a sender who delivered a file deletes their account
- **THEN** sender-side custody rows, physical bytes and the cross-owner file-provenance
  rows are removed ahead of their delivery parent under enforced foreign keys
- **AND** the receiver's independently owned copy, its binding and its bytes remain readable
  through the receiver's own run

#### Scenario: Operator scoped reset meets unerased delivery custody
- **WHEN** an operator scoped identity reset is attempted while root run history
  carries cross-owner delivery file-custody provenance
- **THEN** it refuses with an explicit unclassified-root-run-history blocker naming
  the custody table, because that reset path deletes only from the main database
- **AND** no delivery, provenance row or custody byte is altered by the refusal

#### Scenario: A store refuses one deletion
- **WHEN** an integrity failure interrupts the satellite transaction
- **THEN** all that store's deletes and sender-list edits roll back, no counts are committed,
  and the existing account workflow records the unfinished store phase
