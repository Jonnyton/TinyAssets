## ADDED Requirements

### Requirement: Requester-owned provider rebind

The system SHALL allow an authenticated owner to rebind one provider in one
universe using only the provider name. The server MUST revoke the single
current binding and issue the current server-enrolled assignment. It MUST fail
closed without mutation when multiple matching bindings exist.

#### Scenario: Corrected enrollment replaces one binding

- **GIVEN** one active requester-owned binding and a changed server enrollment
- **WHEN** the owner requests `rebind_provider`
- **THEN** the old binding is revoked and one active binding is issued from the
  current enrollment
