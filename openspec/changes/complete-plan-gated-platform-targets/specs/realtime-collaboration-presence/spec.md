## ADDED Requirements

### Requirement: Presence is an advisory signal and never a write authority

Presence SHALL indicate that a principal is currently viewing or editing an artifact and SHALL be surfaced so collaborators can choose to coordinate. Presence SHALL NOT grant, deny, delay, or reserve the ability to write. A held presence record SHALL NOT block another authorized principal's write, and an absent or lost presence record SHALL NOT relax any authority or conflict check. Compare-and-swap on the artifact version SHALL remain the sole conflict authority.

#### Scenario: Presence does not block a writer

- **WHEN** one principal holds presence on an artifact and another authorized principal writes it with the current version
- **THEN** the write is applied
- **AND** the presence record does not cause refusal or delay

#### Scenario: Losing presence does not weaken conflict control

- **WHEN** a writer's presence record has expired or was never created
- **THEN** their write is still subject to the same compare-and-swap check
- **AND** a stale-version write is still refused

### Requirement: Presence records expire on a heartbeat and are scoped per artifact

A presence record SHALL be bound to one authenticated principal and one artifact, SHALL be refreshed by an explicit heartbeat, and SHALL be treated as absent once its heartbeat interval has lapsed by a bounded margin. Presence SHALL NOT persist indefinitely after a client disconnects, crashes, or loses network, and SHALL NOT require an explicit release to clear. Presence SHALL NOT be inherited across artifacts, sessions, or principals.

#### Scenario: Abandoned presence clears on its own

- **WHEN** a client stops heartbeating without releasing presence
- **THEN** the record is treated as absent within the bounded expiry margin
- **AND** no manual intervention is required to clear it

#### Scenario: Presence does not span artifacts

- **WHEN** a principal holds presence on one artifact
- **THEN** no presence is implied on any other artifact, including its parents, children, or containing collection

### Requirement: Realtime delivery is versioned-row broadcast, not convergent replicated editing

Realtime collaboration SHALL be delivered as broadcast of committed versioned changes plus presence, matching the architecture's chosen strategy. The system SHALL NOT introduce a character-level convergent-replication or operational-transform substrate for collaborative artifacts under this capability. Broadcast payloads SHALL identify the artifact and its resulting version so a receiving client can detect that its view is behind and refetch. Where a specific artifact later requires character-level concurrent editing, it SHALL be introduced per artifact type through its own change with its own acceptance evidence, and SHALL NOT be adopted as a platform-wide substrate by default.

#### Scenario: Broadcast carries the resulting version

- **WHEN** a write is committed to a subscribed artifact
- **THEN** the broadcast identifies the artifact and its resulting version
- **AND** a client behind that version can detect the gap and refetch

#### Scenario: No convergent-replication substrate is introduced

- **WHEN** this capability's realtime path is implemented
- **THEN** collaborative state remains committed versioned rows
- **AND** no character-level replication layer becomes a precondition for editing

### Requirement: Presence and realtime streams enforce the same visibility as reads

A principal SHALL receive presence records and change broadcasts only for artifacts they are authorized to read, evaluated at delivery time against current authority rather than at subscription time only.

The subscription request, the presence heartbeat, and the change broadcast SHALL be carried by the **already-approved non-MCP web transport** fixed by the architecture's realtime strategy. They are transport operations, not MCP handles: this capability SHALL NOT add an advertised MCP handle for subscription, presence, or delivery, and the advertised tool list SHALL remain exactly the seven canonical handles per the cross-capability handle invariant. The transport SHALL resolve authority from the same authenticated subject as the canonical handles, never from a transport-supplied identity claim.

A subscription request naming an artifact the caller cannot read SHALL NOT confirm the artifact's existence, and SHALL be indistinguishable from a subscription to an artifact that does not exist. When a principal's authority over an artifact is revoked, delivery SHALL stop without requiring the client to unsubscribe. Presence SHALL NOT reveal the identity of a principal the observer is not authorized to see as a collaborator.

#### Scenario: Subscription does not confirm existence

- **WHEN** a caller subscribes to an artifact they are not authorized to read
- **THEN** the response is indistinguishable from subscribing to a nonexistent artifact
- **AND** no presence or change event for that artifact is ever delivered

#### Scenario: Revoked authority stops delivery

- **WHEN** a subscribed principal's read authority over an artifact is revoked
- **THEN** further presence and change events for that artifact are not delivered to them
- **AND** the change takes effect without the client unsubscribing

#### Scenario: The realtime transport adds no MCP handle

- **WHEN** the connector's advertised tool list is inspected after presence and streaming ship
- **THEN** no subscription, presence, or delivery handle appears
- **AND** the transport authorizes from the same authenticated subject as the canonical handles

#### Scenario: Collaborator identity respects visibility

- **WHEN** presence would expose a collaborator the observer is not authorized to see
- **THEN** that collaborator is omitted rather than shown anonymized in a way that reveals an additional participant

### Requirement: Realtime is a degradable enhancement and never a precondition for collaboration

Every collaborative operation — read, write, revision, revert, discovery, remix, and convergence — SHALL complete correctly with the realtime transport fully unavailable. Loss of realtime SHALL degrade the experience to explicit refresh and SHALL NOT cause data loss, write refusal, stuck locks, or an unrecoverable client state. Clients unable to hold a persistent connection, including browser-constrained and intermittently connected clients, SHALL retain full functional access through ordinary request/response calls.

#### Scenario: Collaboration continues with realtime down

- **WHEN** the realtime transport is entirely unavailable
- **THEN** reads, writes, revisions, reverts, discovery, remix, and convergence all still complete
- **AND** conflict detection still works through compare-and-swap

#### Scenario: Reconnection recovers without loss

- **WHEN** a client reconnects after a realtime outage
- **THEN** it recovers current state by refetching
- **AND** no write made during the outage is lost or duplicated

### Requirement: Realtime fan-out is bounded by subscription rather than by global change volume

Delivery cost SHALL scale with the number of matching subscriptions rather than with the product of total changes and total subscribers; a change to an artifact with no subscribers SHALL produce no fan-out work beyond its recorded commit. The system SHALL apply a documented per-connection subscription bound and a documented per-connection delivery rate bound, and SHALL shed or coalesce delivery under load in preference to delaying or failing the underlying write. Exceeding a bound SHALL produce an explicit bounded refusal that names the limit, not a silent drop. Before this capability is treated as implemented, its fan-out behavior SHALL be proven under the project's concurrency and load matrix at the stated multiple of projected load.

#### Scenario: Unsubscribed changes cost nothing to broadcast

- **WHEN** an artifact with no subscribers is written
- **THEN** the commit completes and no per-subscriber delivery work is performed

#### Scenario: Load sheds delivery, not writes

- **WHEN** delivery demand exceeds the configured rate bound
- **THEN** delivery is coalesced or shed with an explicit signal to affected clients
- **AND** commit latency and success of the underlying writes are unaffected

#### Scenario: Bounds refuse explicitly

- **WHEN** a connection exceeds its subscription bound
- **THEN** the request is refused with the limit named
- **AND** existing subscriptions on that connection continue to function
