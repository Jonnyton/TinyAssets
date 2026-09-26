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

### Requirement: An executable UI bundle runs only in an isolated, credential-free context

A universe SHALL be able to hold a user-authored executable UI bundle
(`tinyassets.app-ui.v1`: name, markup, style, script) that its own agent writes
through ordinary graph writes, with no platform code change per UI. The app SHALL
render such a bundle only inside a document served by a dedicated route whose
response carries a `Content-Security-Policy` granting `sandbox allow-scripts`
without `allow-same-origin`, and denying its own network (`connect-src 'none'`,
`default-src 'none'`, `form-action 'none'`, non-remote `img-src`). Bundle source
SHALL NOT be assigned into any node of the app's own document, and the app's own
`script-src` SHALL remain nonce-only. The bundle SHALL be treated as hostile
input; the platform SHALL NOT claim to sanitize its markup or script.

#### Scenario: Bundle cannot reach the app's credentials or DOM
- **WHEN** a bundle is rendered
- **THEN** its document has an opaque origin and no `allow-same-origin` grant
- **AND** it cannot read the app's session storage, cookies, or parent DOM
- **AND** the app's page policy permits frames only from its own origin while its
  script policy stays nonce-only

#### Scenario: Bundle has no network path of its own
- **WHEN** the isolated document's policy is inspected
- **THEN** it forbids outbound connections, form submission, remote images, and
  nested frames
- **AND** every capability the bundle has is reached through the message bridge

#### Scenario: Direct navigation to the frame route is still sandboxed
- **WHEN** the frame route is fetched as a top-level document rather than framed
- **THEN** the sandbox and its opaque origin still apply from the response header
- **AND** no user bundle content is present in that response

#### Scenario: A malformed bundle is refused with a reason
- **WHEN** a bundle carries an unexpected field, a wrong kind or version, a
  non-string body, or exceeds its byte bounds
- **THEN** it is reported unsupported with the reason and is not rendered
- **AND** the default chat experience stays in use

### Requirement: The bundle bridge is a closed allowlist acting as the viewing user

The bridge SHALL accept a message only from the rendering frame, SHALL resolve the
action against a fixed allowlist, and SHALL refuse an unlisted action by name
without guessing. Every handler SHALL pin its universe target to the viewing
user's own current home rather than accepting one from the bundle, SHALL carry no
credential, token, or raw provider material in any reply, and SHALL build replies
from explicitly picked fields rather than forwarding server payloads. A bundle
SHALL be able to address a named agent in the viewing user's universe.

#### Scenario: Unlisted action is refused
- **WHEN** a bundle requests an action outside the allowlist
- **THEN** the bridge returns a refusal naming the action
- **AND** no tool call is made

#### Scenario: Cross-user reach is unrepresentable
- **WHEN** a bundle supplies another universe's identifier in its request
- **THEN** the supplied value is ignored and the call targets the viewer's home
- **AND** a stale or changed home ends the bridge rather than serving the old target

#### Scenario: Replies carry no credentials
- **WHEN** an allowlisted handler returns
- **THEN** its reply contains only the fields the bridge picked
- **AND** no access token, refresh handle, or credential-shaped value is included

#### Scenario: Message reaches a named agent in the viewer's universe
- **WHEN** a bundle sends a message naming an agent
- **THEN** the message is relayed within the viewer's own universe
- **AND** the author's universe is not addressed

### Requirement: Switching is on the fly, remembered, and does not fork the layout system

The app SHALL offer an explicit choice between the default chat experience and any
installed bundle, SHALL apply it without reload, and SHALL persist it in the same
private `app_experience` binding configuration that holds the existing layout and
turn-consumer selection, under the same read-back and revision-guarded write
discipline. A universe with no bundle SHALL behave exactly as before.

#### Scenario: Choice survives a new sign-in
- **WHEN** a user selects an installed bundle and later signs in again
- **THEN** that bundle is applied from the persisted selection
- **AND** returning to default chat is available at all times

#### Scenario: Concurrent selection write is refused, not overwritten
- **WHEN** the binding revision observed before the write is stale
- **THEN** the write is refused as a conflict and the current selection is reloaded
- **AND** nothing is retried automatically

#### Scenario: A remixed bundle acts as the remixer
- **WHEN** a second account remixes a published bundle and runs it
- **THEN** its bridge resolves to the remixer's own universe and identity
- **AND** the original author's universe, conversation, and agents are unreachable
