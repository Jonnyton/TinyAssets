## ADDED Requirements

### Requirement: Owner can remove connections without a model
The app SHALL expose redacted universe-owned HTTP connection inventory and an
explicit disconnect action to the authenticated owner without model execution.

#### Scenario: Unpowered owner disconnects
- **WHEN** an authenticated owner confirms removal of a listed connection
- **THEN** TinyAssets removes its local credential custody and future runtime
  access while retaining user content and independent connections
- **AND** the result does not claim cancellation of effects already dispatched or
  deletion of the upstream account/key

#### Scenario: Wrong owner or stale screen
- **WHEN** a caller targets another owner's connection or an obsolete incarnation
- **THEN** removal refuses without changing the current connection or its secret

### Requirement: Disconnect is an authority transition
Removal SHALL fence dependent model authority and old approvals, serialize with
connection mutation, and preserve unrelated owner/source authority.

#### Scenario: Remove and reconnect
- **WHEN** the owner removes a model connection and later reconnects its destination
- **THEN** old grants and approvals cannot authorize the new connection
- **AND** new model execution requires fresh explicit approval

#### Scenario: Interrupted removal
- **WHEN** a local cleanup step fails after authority withdrawal
- **THEN** the connection remains unavailable to execution, the UI reports an
  incomplete result, and retry cannot remove a newer connection incarnation

### Requirement: Guided reconnect preserves the universe
An intentionally disconnected owner SHALL be able to use normal hosted model
authorization again without deleting their universe or editing its workflows.

#### Scenario: Existing agent is reconnected
- **WHEN** the owner completes hosted authorization after deliberate disconnect
- **THEN** the app returns to fresh approval against the exact current agent
  revision, preserving agent content, history and saved model preferences
