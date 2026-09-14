## ADDED Requirements

### Requirement: Experiences are editable compositions
The system SHALL represent an experience as an inspectable, versioned composition
with replaceable presentation, inputs, state bindings, action bindings, event
routing and device adaptation. First-party experiences SHALL use the same
contracts and authority checks as user-authored experiences.

#### Scenario: Replace an instance board with an office
- **GIVEN** an installed desktop board and phone view of the same instance
- **WHEN** the user remixes the board into an office and maps a room to that instance
- **THEN** selection and controls resolve to the same authorized instance
- **AND** no platform source edit or privileged first-party path is required

### Requirement: Sharing excludes installation and runtime data
A published definition SHALL preserve component lineage and source integrity
while excluding private bindings, credentials, device tokens, real instance IDs,
conversation history and runtime data. Import SHALL remain inert.

#### Scenario: Another user installs a shared experience
- **WHEN** a second account imports the published definition
- **THEN** it can inspect and remix the components before activation
- **AND** it must bind its own authorized instances and destinations
- **AND** neither the source user's private data nor authority is inherited

### Requirement: Device adaptation preserves meaning
A renderer SHALL check declared capabilities and show supported alternatives.
Unknown components SHALL remain exportable. Missing required capabilities SHALL
prevent activation on the affected device with an explicit reason.

#### Scenario: A spatial experience opens on a phone
- **WHEN** spatial rendering is unavailable and the composition declares a list alternative
- **THEN** the phone renders that alternative with the same semantic bindings
- **AND** unavailable behavior is identified rather than reported as successful

### Requirement: Interaction preserves canonical continuity and authority
Every input modality SHALL resolve actions through existing governed operations
and current private bindings. Switching experience or device SHALL preserve
canonical universe and conversation identity. Voice SHALL relay canonical replies.

#### Scenario: Continue from earbuds on a phone
- **WHEN** a user opens the phone from an earbud interaction
- **THEN** the phone resolves the same conversation and selected instance
- **AND** no new writer, grant, or background run is created by the handoff

#### Scenario: An old control targets revoked authority
- **WHEN** a cached control or notification action is used after revocation
- **THEN** the trusted boundary rejects it before any effect
- **AND** the experience presents the refusal without retrying under another identity

### Requirement: Event routing is composable and evidence-backed
Users SHALL be able to customize event routing across their authorized devices
and channels. Replay handling SHALL use stable event identities and documented
deduplication bounds. Delivery status SHALL reflect adapter evidence.

#### Scenario: A completion event arrives twice after reconnect
- **WHEN** an office view and phone receive a replay inside the deduplication window
- **THEN** each destination avoids duplicate presentation for that event
- **AND** acknowledgment resolves the shared event under a revision check
- **AND** acknowledgment alone does not authorize another action

#### Scenario: Phone delivery is unavailable
- **WHEN** the configured notification adapter cannot deliver
- **THEN** the experience reports the failure or unsupported capability
- **AND** any alternative destination is used only under its existing authorization

### Requirement: Experience evolution is reversible and user-controlled
Preview SHALL have no live effects or private subscriptions. Activation SHALL
pin a revision and reject conflicting updates. A user SHALL be able to disable
a broken experience and restore a compatible prior revision.

#### Scenario: Concurrent device edits
- **WHEN** two devices activate edits based on the same installation revision
- **THEN** only one revision update succeeds
- **AND** the other receives a conflict without losing its proposed edit

#### Scenario: Preview and rollback
- **WHEN** a user previews a remix containing action and notification bindings
- **THEN** only fixture behavior runs
- **AND** after explicit activation the user can disable or roll back the view
- **AND** rollback does not claim to undo completed external effects
