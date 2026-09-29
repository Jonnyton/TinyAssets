## ADDED Requirements

### Requirement: A same-account rotation carries custody forward
The system SHALL keep a credential custody reference, and every authority record that pins it, unchanged when the platform itself refreshes the exact pinned subscription document, updating only the custody row's byte pin by compare-and-swap inside the same exclusive vault hold as the byte write; an owner deposit, an adopted on-disk rotation, a changed account identity, or a schema-version-1 custody row SHALL renew the accepted source instead.

#### Scenario: Platform refresh during an in-flight run
- **WHEN** a run holds a receipt and the platform rotates the same account's sign-in
- **THEN** the run's next launch succeeds on the rotated bytes and no binding, assignment or receipt is republished

#### Scenario: Different account
- **WHEN** the rotated document names a different account, or the rotation was adopted from a CLI home rather than performed by the platform
- **THEN** the accepted source renews as before and in-flight receipts are refused

#### Scenario: Bytes nobody pinned
- **WHEN** the stored bytes differ from the custody byte pin without a carry-forward
- **THEN** custody reads and launch snapshots refuse
