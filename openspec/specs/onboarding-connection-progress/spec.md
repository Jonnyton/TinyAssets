# Onboarding connection progress

## Purpose

Show truthful progress when the signed-in app saves and enables a Claude
subscription, without replaying credentials or carrying work across logins.

## Requirements

### Requirement: Observe credential saving and enabling separately

The Claude connection control SHALL clear the pasted token before any await,
show Saving token while depositing it, and advance to enabling only when the
deposit response explicitly reports `status: deposited`. Empty or ambiguous
responses SHALL remain unconfirmed. Saved model preferences SHALL be unchanged.

#### Scenario: Confirmed connection
- **WHEN** deposit confirms success and the serving bind confirms serving
- **THEN** the app reports the credential saved and enabled
- **AND** it may navigate only while the same login and connection view remain current

#### Scenario: Bounded observation without credential replay
- **WHEN** either stage has not settled after 30 seconds
- **THEN** the app reports that stage as unconfirmed without cancelling or replaying it
- **AND** the control remains guarded until the original request settles
- **AND** the app explains checking the model picker and reloading if still pending

#### Scenario: Late save and user-directed enabling
- **WHEN** a deposit confirms after its observation deadline or after leaving the connection view
- **THEN** the app reports the saved token and offers Enable Claude using the existing button
- **AND** only that explicit action starts a bind, without another credential deposit
- **AND** a late bind result never navigates automatically

#### Scenario: Refusal or failed enabling
- **WHEN** deposit is definitively refused
- **THEN** normal submission is available again
- **WHEN** the saved credential cannot yet be enabled
- **THEN** the app preserves the distinction between saved and enabled and offers Enable Claude after settlement

### Requirement: Pending requests belong to their original login

Sign-out SHALL invalidate the connection attempt and the MCP transport login
generation immediately. Delayed work SHALL neither modify the new login's UI
nor send the previous login's arguments under the new bearer. This fence SHALL
apply to initial handshakes and every automatic transport recovery path.

#### Scenario: Delayed credential request encounters a session rejection
- **WHEN** a credential request returns 401 or 404 after sign-out or a login change
- **THEN** it is not replayed or refreshed under the replacement login
- **AND** a delayed handshake cannot proceed to deposit the original token
- **AND** stale handshakes cannot clear a replacement login's session
