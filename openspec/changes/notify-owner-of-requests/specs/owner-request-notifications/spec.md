# owner-request-notifications (delta)

## ADDED Requirements

### Requirement: A device belongs to the signed-in user who registered it
Device registration SHALL take the owning subject from the authenticated request and SHALL ignore any subject, universe or destination named in the payload. Registering a token that is already recorded for a different subject SHALL move it: every prior row for that token SHALL be removed before the new row is written. A listing of devices SHALL return only the caller's own devices and SHALL never return a token.

#### Scenario: A payload cannot claim another subject
- **WHEN** a signed-in user registers a device with another user's subject in the body
- **THEN** the device is recorded against the authenticated caller and the supplied subject is ignored

#### Scenario: A phone that switches accounts stops receiving the old account's notifications
- **WHEN** a token registered by user A is registered again by user B
- **THEN** A's row for that token is removed, and a later notification for A reaches no device holding that token

#### Scenario: An alternate representation of one destination cannot alias
- **WHEN** the same destination is registered by a second user in a form that differs only in metadata the transport does not read, in key serialisation, in rotated keys on the same endpoint, or in a part of the address the transport does not send (a URL fragment, host case, the default port)
- **THEN** it is still recognised as that one destination and the prior owner's row is removed

#### Scenario: Two genuinely different destinations stay separate
- **WHEN** addresses differing in path, path case or query are registered
- **THEN** each is its own device, because merging real destinations would silently drop one

#### Scenario: One string on two transports is two destinations
- **WHEN** a token for one platform has the same characters as a destination registered for another platform
- **THEN** registering it affects only its own platform's destination, and the other user's device and its outstanding alert are untouched

#### Scenario: Relaunching keeps one device
- **WHEN** the same owner registers the same destination again
- **THEN** the existing device keeps its identifier and its stored token is refreshed, rather than a second device appearing

#### Scenario: Two addresses the transport distinguishes stay distinct
- **WHEN** registrations differ in a component the transport addresses separately — host, resolved port, path, or the presence of a query
- **THEN** they are separate destinations, including cases where naive rejoining of host and port would produce one string

#### Scenario: An address that cannot be parsed is its own destination
- **WHEN** an endpoint's authority cannot be parsed
- **THEN** it is treated as a distinct destination rather than merged with another

### Requirement: A change to destination identity migrates existing registrations
When the stored destination identity is computed differently than it was for existing rows, those rows SHALL be brought to the current computation before an ownership move is matched against them, and rows that collapse onto one destination SHALL be resolved to the most recent registration. The migration SHALL be idempotent and SHALL NOT fail a read when another writer holds the store.

#### Scenario: A device registered before the change still moves
- **WHEN** a destination was registered under a previous identity computation and a different user registers the same destination
- **THEN** the previous owner's row is removed and a later notification for them reaches no device holding it

#### Scenario: The same owner re-registering finds their own earlier row
- **WHEN** the owner re-registers a destination stored under the previous computation
- **THEN** the existing device keeps its identifier rather than a second device appearing for one handset

#### Scenario: Rows that collapse onto one destination resolve to the newest
- **WHEN** several stored rows prove to name one destination under the current computation
- **THEN** only the most recent registration survives

#### Scenario: Tokens are not readable back
- **WHEN** the owner lists their devices
- **THEN** each entry carries an id, platform, label, enabled flag and last-seen time, and no token material

### Requirement: A notification reaches only the request's own owner
Dispatch SHALL resolve the destination set from the owning subject of the universe that holds the request, and SHALL accept no destination, subject or device from a caller, a payload or the request's own content. A dispatch whose resolved owner does not match the subject that raised the request SHALL send nothing and SHALL record the refusal.

#### Scenario: Another user's devices are never a destination
- **WHEN** a request is raised in user A's universe while user B has registered devices
- **THEN** only A's devices are dispatched to, and B's devices receive nothing

#### Scenario: Request content cannot select a destination
- **WHEN** a request's title, body, fields or items name a device, token, endpoint or subject
- **THEN** the resolved destination set is unchanged and the named value is never used

#### Scenario: A disagreeing owner sends nothing
- **WHEN** the subject that raised the request is not the admin owner of the universe holding it
- **THEN** no notification is dispatched and the refusal is recorded

### Requirement: The platform composes the notification's identity
The notification title SHALL be derived by the server from the universe record and SHALL carry a fixed, server-owned indication that a universe is asking its owner something. Agent-supplied text SHALL appear only in the body, with control characters removed and a length bound applied. No field of a request SHALL be able to place text in the identity position or reproduce the fixed indication, and field values entered by the owner SHALL never appear in a payload.

#### Scenario: An ask cannot impersonate the platform or another user
- **WHEN** a request's kind or title is crafted to read as a platform or other-user notice
- **THEN** the delivered title is still the universe's own server-derived name plus the fixed indication, and the crafted text appears only as body content

#### Scenario: An unnamed universe does not borrow the platform's name
- **WHEN** the universe has no display name of its own, or its record cannot be read
- **THEN** the title is a neutral phrase carrying the same fixed indication, and never the platform's own name alone

#### Scenario: A universe name cannot counterfeit the structure
- **WHEN** the universe's own name already ends with the fixed indication, or consists of characters that occupy no space, or contains a direction override
- **THEN** the delivered title carries the indication exactly once, is visible text, and cannot be visually reordered

#### Scenario: The invisible characters are a class, not a list
- **WHEN** a name uses any Unicode format, control, surrogate, private-use or unassigned character, including bidi isolates and marks
- **THEN** it is removed, and a name of only such characters falls back to the neutral phrase

### Requirement: Delivery addresses a destination verified at claim time
Dispatch SHALL obtain the destination it sends to from the same transaction that claims the notification and verifies current ownership, not from an earlier read. A device that ceased to be this owner's, or was retired, between the start of dispatch and its own claim SHALL NOT be sent to.

#### Scenario: A handset reassigned mid-dispatch is not sent to
- **WHEN** a destination is registered by a different user while an earlier device in the same dispatch is being sent to
- **THEN** that destination receives nothing for this owner

#### Scenario: A destination whose token changed is sent the current one
- **WHEN** the stored token for a device is refreshed after dispatch began
- **THEN** the transport is handed the refreshed token, not the one read before the loop

### Requirement: One notification per request, per item, per destination
Delivery SHALL be deduplicated on exactly the request, the item, the destination and the kind, and on nothing else. There SHALL be no notification-specific rate, quota or outstanding-alert bound: cost is bounded by the concurrent agent-run seat a raising run holds and by the ceiling on unanswered requests. Every one of the owner's enabled destinations SHALL receive a request's notification.

#### Scenario: A request notifies a destination once whatever happens to it
- **WHEN** the same request is dispatched again after being answered, withdrawn or re-read
- **THEN** the destination that already received it receives nothing further, and the repeat is reported as a replay

#### Scenario: Every one of the owner's devices is told
- **WHEN** a request is raised and the owner has several enabled destinations
- **THEN** each of them receives the notification

#### Scenario: Distinct requests each notify
- **WHEN** a universe raises several genuinely different requests
- **THEN** each is delivered, and the pile is bounded by the unanswered-request ceiling rather than by a notification limit

### Requirement: A notification the request surface accepted is deliverable
Composition SHALL bound the notification in bytes, not only in characters, and SHALL fit the whole serialised payload within the transport's record so that any request the ask surface accepted can be delivered. Truncation SHALL fall on a character boundary, and SHALL reduce the agent's words before the identity line or the identifiers a client needs to open the request.

#### Scenario: Multi-byte text at the accepted limits still sends
- **WHEN** a request is raised at the accepted limits of kind, title and item count using multi-byte characters, in a universe whose name is also multi-byte
- **THEN** the notification is delivered rather than refused by the transport

#### Scenario: What survives trimming is what makes it actionable
- **WHEN** a notification must be trimmed to fit
- **THEN** the identity line and the request identifier remain

### Requirement: Persisted device state records codes, never transport text
A device's retirement reason SHALL be drawn from a fixed set of codes; a reason a transport supplies that is not one of them SHALL be recorded as unknown. No transport-supplied text SHALL be readable back from a device listing.

#### Scenario: A transport error carrying a credential is not stored
- **WHEN** a transport reports the destination gone with a message containing credential material
- **THEN** the device's recorded reason is the unknown code and the message is not readable from any read

#### Scenario: A known code is still recorded
- **WHEN** a transport reports a recognised gone code
- **THEN** that code is recorded, so the retirement stays diagnosable

#### Scenario: Answered field values never leave in a payload
- **WHEN** a request carries fields and items whose values the owner has filled in
- **THEN** no dispatched payload contains any field value

### Requirement: Notifications are owner-controlled
Dispatch SHALL send nothing when the owner has turned notifications off or has no enabled device. The owner's setting SHALL be readable and changeable by that owner only. A dispatch that sends nothing SHALL NOT prevent the request from being raised, read or answered.

#### Scenario: Notifications off means nothing is sent
- **WHEN** the owner has turned notifications off and a request is raised
- **THEN** no transport is invoked and the request is still pending in the rail

#### Scenario: Another user cannot read or change this setting
- **WHEN** a different signed-in user reads or writes the notification setting
- **THEN** they act only on their own setting and this owner's is unchanged

### Requirement: Only a genuinely new request notifies
Dispatch SHALL be invoked only for a newly stored pending request. A request that was deduplicated against an existing pending row, a settled standing decision, or a storage refusal SHALL dispatch nothing.

#### Scenario: A retried ask does not notify again
- **WHEN** the universe raises the same ask twice and the second is deduplicated onto the existing pending row
- **THEN** exactly one notification was dispatched for that request

#### Scenario: A standing decision notifies nothing
- **WHEN** an ask matches a suppression the owner already settled
- **THEN** no request is stored and no transport is invoked

### Requirement: Delivery is idempotent, redacted and fails closed
Dispatch SHALL be idempotent on the request, item, device and kind, so a retry after a lost response does not deliver twice. Persisted delivery evidence SHALL contain no body, field value or token — only identifiers, a kind and a failure or success class. A transport error SHALL become a bounded class and SHALL NOT surface exception text, credential material or an unbounded retry instruction. A transport that reports the destination gone SHALL retire that device.

#### Scenario: A retry does not notify twice
- **WHEN** the same request is dispatched twice to the same device
- **THEN** the transport is invoked once and the second attempt is reported as a replay

#### Scenario: A transport's return value is also bounded
- **WHEN** a transport returns a value that is not one of the defined outcomes
- **THEN** it is recorded and reported as an unavailable outcome, and the returned value appears in no ledger row or dispatch result

#### Scenario: A transport exception carrying a secret leaks nothing
- **WHEN** the transport raises an exception whose text contains credential material
- **THEN** the recorded evidence holds only a fixed failure class and the caller receives no exception text

#### Scenario: A gone device is retired
- **WHEN** the transport reports the registration unknown or gone
- **THEN** the device row is retired with a reason and is not dispatched to again

### Requirement: No transport configured never costs the request
When no transport is configured, dispatch SHALL report that plainly, SHALL log it, and SHALL neither fabricate a receipt nor fail the request that was raised.

#### Scenario: Push unconfigured
- **WHEN** a request is raised with no transport configured
- **THEN** the request is stored and answerable, the dispatch reports no transport, and no receipt claims a delivery

### Requirement: Answering on one device clears the others
Closing a request — by answering it, dismissing it, or the universe withdrawing it — SHALL dispatch a content-free clear carrying its request id, and ONLY to destinations whose notification may still be displayed. A destination whose notification was claimed but whose outcome is not yet recorded SHALL count as possibly displaying it, because clearing one that never received a notification is harmless while failing to clear one that did leaves a resolved request on the owner's screen. Resolving one item of a request SHALL NOT dispatch a clear, because a notification names the request rather than an item. The clear SHALL be best effort and SHALL never fail or delay the closure.

#### Scenario: An answer while the notification is still in flight still clears
- **WHEN** the owner resolves a request after its notification was claimed but before its outcome was recorded
- **THEN** a clear is dispatched to that destination

#### Scenario: A withdrawn request's notification comes down
- **WHEN** the universe withdraws a request it had raised
- **THEN** a clear naming that request is dispatched, so no notification points at a request that no longer exists

#### Scenario: The other phone's notification goes away
- **WHEN** the owner answers a request on one registered device
- **THEN** a clear naming that request is dispatched to their other devices that were holding it, and not to the answering one

#### Scenario: A device that never received the notification is not woken
- **WHEN** a request is resolved and one of the owner's devices never received its notification
- **THEN** that device is not dispatched to

#### Scenario: Working through an itemised request costs one clear
- **WHEN** the owner answers every item of a request with many items
- **THEN** one visible notification and one clear are dispatched per device, not one per item

#### Scenario: A clear that cannot be sent does not undo the answer
- **WHEN** the transport fails while clearing
- **THEN** the answer stands and the failure is recorded

### Requirement: A notification is answerable from where it lands
The dispatched data SHALL carry the request id, the universe id and the item ids, so a client can open directly at that request. Any action offered on the notification SHALL be answered through the signed-in user's own app session; no device-scoped credential SHALL be stored or accepted for answering.

#### Scenario: Tapping opens the request
- **WHEN** the owner taps a notification
- **THEN** the app opens with that request expanded

#### Scenario: No second custody of the owner's authority
- **WHEN** a notification action is used
- **THEN** the answer is submitted under the app's own authenticated session and no credential is read from or written to device-local storage
