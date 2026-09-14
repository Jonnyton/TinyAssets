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

### Requirement: Experience primitives have explicit governed interfaces
An experience SHALL connect versioned projection, view, input, action, routing
and device contracts through validated ports. Public source SHALL remain
independent from private bindings and canonical run/conversation state.

#### Scenario: Change presentation without changing the harness
- **GIVEN** a run shown by a board and a compact phone view
- **WHEN** the board is replaced by a compatible office component
- **THEN** both views continue observing the same authorized run and conversation
- **AND** changing the view creates no new runtime instance or writer

#### Scenario: A disposed renderer sends a delayed action
- **WHEN** a bridge request arrives from an old renderer lifecycle generation
- **THEN** the trusted bridge rejects it
- **AND** it does not act through the current installation's bindings

### Requirement: Event recovery cannot replay user authority
Projection updates SHALL carry documented revision/cursor semantics and
distinguish event identity, destination delivery and user action identity.

#### Scenario: Reconnect beyond retained history
- **WHEN** a saved cursor precedes the retained stream
- **THEN** the view obtains a fresh authorized snapshot and reconciles local state
- **AND** older deltas do not overwrite the snapshot
- **AND** reconnect does not silently dispatch saved external actions

#### Scenario: Speech is still being transcribed
- **WHEN** partial speech matches an action phrase
- **THEN** the experience waits for committed user input
- **AND** playback completion or notification display is not treated as approval

### Requirement: Custom experiences remain accessible and recoverable
Required semantic controls SHALL have operable non-spatial alternatives.
The trusted host SHALL retain an accessible way to disable a broken experience.

#### Scenario: Spatial rendering or custom input fails
- **WHEN** a user cannot operate a spatial view or a component stops responding
- **THEN** keyboard and accessible alternatives preserve required semantic controls where supported
- **AND** the trusted recovery surface can disable the experience

### Requirement: Personalization remains a proposed user-controlled revision
An agent-generated personalization SHALL produce an inspectable diff and
inert preview before activation. Learned private preferences SHALL NOT be
automatically published with a shared definition.

#### Scenario: A suggested improvement requests new capabilities
- **WHEN** an agent proposes a new route or component that needs additional access
- **THEN** the user can inspect the revision and its changed requirements
- **AND** activation cannot confer the missing authority

### Requirement: Editors and upgrades preserve user-authored customization
Supported editors SHALL preserve source outside their understood edit scope or
refuse an edit without loss. Upstream upgrades SHALL retain private modifications
and stage conflicts separately from the active experience.

#### Scenario: An editor encounters an unknown field
- **WHEN** the user edits a supported field and saves
- **THEN** unknown source is preserved or the edit is refused without modifying it

#### Scenario: Upstream deletes a customized component
- **WHEN** a candidate upgrade removes a component with private modifications
- **THEN** the user receives a conflict with the modifications retained
- **AND** the old active experience remains available for use, pinning or forking

### Requirement: Projection recovery has a defined consistency boundary
A projection adapter SHALL define snapshot/cursor consistency, gap recovery and
authority revalidation. Device timestamps SHALL NOT imply global event ordering.

#### Scenario: An event races snapshot and subscription
- **WHEN** state changes between snapshot retrieval and subscription establishment
- **THEN** reconciliation includes the change or a later snapshot covering it
- **AND** the view does not silently omit it or reissue its effects

#### Scenario: An expired cursor is followed by an old delta
- **WHEN** a new authorized snapshot replaces an expired delta chain
- **THEN** an older delta cannot regress state or trigger an action

### Requirement: Programmable routing preserves action and lifecycle meaning
Notification grouping, playback interruption and renderer recovery SHALL remain
distinct from canonical requests, approvals, runs and task completion.

#### Scenario: Notifications group distinct pending requests
- **WHEN** a route groups two notifications with different request targets
- **THEN** each target and action identity remains distinct
- **AND** grouping or viewing answers neither request

#### Scenario: Voice playback is interrupted
- **WHEN** the user interrupts a spoken reply or earbuds disconnect
- **THEN** playback policy applies without implicitly cancelling the run
- **AND** private audio does not move to a speaker without configured authorization

#### Scenario: A spatial renderer cannot be operated by dragging
- **WHEN** the user uses the non-drag pointer or keyboard alternative
- **THEN** it reaches the same semantic action and governed target
- **AND** trusted recovery remains reachable if the renderer fails

### Requirement: Prepared interactions retain target meaning
An experience SHALL bind prepared intent to its source/binding revision, selected
target and arguments. A material change SHALL invalidate the preparation before
dispatch. Accepted work SHALL be observed through its canonical reference.

#### Scenario: Selection changes before submission
- **WHEN** a prepared action targets one instance and selection changes to another
- **THEN** the prior preparation cannot silently act on the new target
- **AND** the new preparation exposes materially changed meaning

#### Scenario: A view remounts after action acceptance
- **WHEN** a renderer is replaced while accepted work remains in progress
- **THEN** the new authorized view observes the canonical work reference where supported
- **AND** missing local pending state does not cause a new run
- **AND** unsupported recovery is shown as uncertainty rather than retried blindly

### Requirement: Renderer communication and handoff convey no ambient authority
A renderer adapter SHALL define a confined bootstrap and message-validation
contract tied to its host-created session and lifecycle. Handoff links SHALL use
non-authorizing references resolved under current authentication.

#### Scenario: A different opaque-origin frame sends a bridge message
- **WHEN** the message has a valid payload and the origin string is null
- **THEN** the host verifies the expected source or bound port and session
- **AND** an unrelated frame receives neither private data nor action authority

### Requirement: Action status is accessible and evidence-backed
Required controls SHALL expose pending, refusal, uncertainty and completion through
accessible presentation consistent with canonical evidence. Routine status changes
SHALL NOT require focus movement merely to perceive them.

#### Scenario: Delivery is uncertain
- **WHEN** an accepted action has no conclusive external delivery result
- **THEN** the experience presents uncertainty and a supported inspection path
- **AND** it does not announce success or offer an unconditional safe retry
