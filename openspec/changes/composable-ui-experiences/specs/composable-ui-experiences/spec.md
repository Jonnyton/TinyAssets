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

### Requirement: Switching is on the fly, remembered, and is the only app-design control

The app SHALL offer an explicit choice between the default chat experience and any
installed bundle, SHALL apply it without reload, and SHALL persist it in the
viewer's own UI row under a revision-guarded write. A universe with no bundle
SHALL behave exactly as before. Switch UI SHALL be the app's only design
control: arranging, spacing and conversation behaviour belong to custom UIs the
universe builds, and the Switch UI dialog SHALL carry the trusted conversation
recovery (current design, restore default, restore previous).

#### Scenario: Choice survives a new sign-in
- **WHEN** a user selects an installed bundle and later signs in again
- **THEN** that bundle is applied from the persisted selection
- **AND** returning to default chat is available at all times

#### Scenario: Concurrent selection write is refused, not overwritten
- **WHEN** the row revision observed before the write is stale
- **THEN** the write is refused as a conflict and the current selection is reloaded
- **AND** nothing is retried automatically

#### Scenario: A remixed bundle acts as the remixer
- **WHEN** a second account remixes a published bundle and runs it
- **THEN** its bridge resolves to the remixer's own universe and identity
- **AND** the original author's universe, conversation, and agents are unreachable

### Requirement: Egress paths outside CSP's reach are removed, not merely policed

A bundle SHALL have no path to move data out of the app other than its bridge.
Where an egress channel exists that content-security policy cannot express —
WebRTC ICE hostname resolution and DNS prefetch — the platform SHALL remove the
capability from the bundle's realm and SHALL NOT rely on an unenforced directive.
The removal SHALL hold, meaning the bundle's document SHALL have no route to a
fresh realm: nested frames, workers and popups SHALL all be refused by its policy.

#### Scenario: WebRTC is unavailable to a bundle
- **WHEN** a bundle attempts to construct a peer connection
- **THEN** the constructor is absent and cannot be reassigned
- **AND** the removal happened before any bundle code ran

#### Scenario: No fresh realm is reachable
- **WHEN** a bundle tries to obtain an unmodified global object
- **THEN** a nested frame, a worker and a popup are each refused by its own policy
- **AND** DNS prefetch is disabled by the response

### Requirement: A bundle's grant ends when the identity or home it was granted for changes

A bundle's bridge SHALL be scoped to one signed-in identity and one home universe.
Every transition of the app's home SHALL revoke a mounted bundle, and an
account-scoped clear SHALL do the same. Each bridge action SHALL re-verify the
signed-in identity and home before acting, and any read that resolves a universe
server-side SHALL name the granted universe and SHALL verify the universe the
answer describes.

#### Scenario: The account moves home while a bundle is mounted
- **WHEN** the app observes a different home for the same signed-in account
- **THEN** the mounted bundle is closed and its bridge stops answering
- **AND** no data from the new home reaches it

#### Scenario: A read answers about another universe
- **WHEN** a pinned read returns a universe other than the granted one
- **THEN** the result is refused rather than returned
- **AND** the refusal names that the access ended

#### Scenario: A reply is owed to the frame that asked
- **WHEN** the displayed bundle is replaced while a request is outstanding
- **THEN** the earlier bundle's result is not delivered to the replacement
- **AND** it does not disturb the replacement's own request accounting

### Requirement: Installing never destroys stored UIs it could not read

An install SHALL refuse when the stored library cannot be understood, SHALL build
its update from the configuration the guarded write observed rather than a cached
view, and SHALL bound the resulting configuration by the same byte limit the
server enforces, measured the same way. A limit visible before the write SHALL be
reported without marking the shared installation uncertain; a limit reached inside
the write window MAY.

#### Scenario: A stored bundle of an unsupported version is preserved
- **WHEN** the library holds a bundle this app cannot parse and another is installed
- **THEN** the install is refused and nothing is written
- **AND** the unparsable bundle is still stored

#### Scenario: The stored configuration grew since it was read
- **WHEN** the observed configuration allowed the install but the stored one does not
- **THEN** the guarded write refuses and reports the size
- **AND** nothing is written

#### Scenario: Size is measured as the server measures it
- **WHEN** a bundle's content is multi-byte
- **THEN** its size is counted in encoded bytes against the server's cap

### Requirement: A person's UI library and choice live in their own row

Each person SHALL have at most one UI row per universe, holding their UI library
and their UI choice, keyed by the authenticated caller and the universe and never
by a caller-supplied identity. It SHALL NOT be an agent binding and SHALL NOT
appear to, or change, any agent-binding reader. A first save SHALL create the row
with nothing published. Every save SHALL be compare-and-set on the revision the
caller read, SHALL write only the fields it names, and SHALL be refused as a
conflict rather than overwrite when the revision is stale. Deleting an account
SHALL remove that person's rows in every universe and no one else's, including
another person's row about the deleted account's own universe.

#### Scenario: A new account installs a UI having published nothing
- **WHEN** an owner with no row and no published definition installs a bundle
- **THEN** a first save at revision 0 creates their row holding it
- **AND** nothing about that account is published, and no agent binding is created

#### Scenario: Two first saves at once leave one row
- **WHEN** two saves for the same person and universe both name revision 0
- **THEN** exactly one row exists and exactly one save succeeded
- **AND** the other is refused as a conflict

#### Scenario: Saving a choice does not erase the library
- **WHEN** a save names only the UI choice
- **THEN** the stored library is unchanged

#### Scenario: Another person is never handed someone else's row
- **WHEN** a second person reads or saves in the same universe
- **THEN** they reach their own row, or are refused when they lack access
- **AND** the first person's row is neither readable nor changed through it

#### Scenario: Agent bindings keep their shape
- **WHEN** the UI store is created or written
- **THEN** every agent binding still requires a definition reference

### Requirement: The served surface names where an interface gets built

An agent asked to build an interface SHALL be able to find the primitive from the
served surface without guessing. The resident guidance index SHALL name a chapter
covering interface building, and that chapter SHALL state the storage call, the
component's exact fields and bounds, the bridge's complete capability list, and how
a UI is switched to and shared.

#### Scenario: An agent looking for a place to build a UI finds one
- **WHEN** the served guidance for the graph-writing handle is read
- **THEN** it names an interface chapter in the resident index
- **AND** that chapter names the UI component kind and the four bridge calls
