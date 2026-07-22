## ADDED Requirements

### Requirement: Connections are bidirectional resources bound to user grants
The platform SHALL support inbound MCP and outbound MCP connection classes through a resource ledger that records the owning user, scope, provider, destination, and revocation state. Connector definitions, including MCP client configuration and normalization workflows, SHALL be commons artifacts that can be remixed with attribution. A source or effector node SHALL bind only a declared connection class authorized by the current user's per-universe revocable grant; the universe SHALL never own the credential, and raw credentials SHALL never enter graph state or artifacts.

#### Scenario: a node binds an authorized connection class
- **WHEN** a user grants a universe access to an outbound connection class and a node requests that class
- **THEN** the runtime resolves a scoped proxy from the resource ledger without exposing the credential to the node

### Requirement: Action caps are independent of tool permission
Every value-moving or quota-consuming connection action SHALL enforce a machine-readable unprompted-action cap in addition to tool authorization and any spend cap. A below-cap authorized action SHALL execute automatically; an action above the cap SHALL hold for explicit confirmation without consuming funds or quota, with an actionable remediation surface rather than silent behavior.

#### Scenario: a high-value action holds for confirmation
- **WHEN** an otherwise authorized action exceeds its configured cap
- **THEN** the runtime returns a held receipt naming the cap and performs no external effect until an authorized confirmation is recorded
- **AND** the same action at or below the cap executes automatically

### Requirement: External effects are replay-safe and batch failures are explicit
Every external effect SHALL derive a deterministic idempotency key from durable goal, schedule-period, and item fingerprint identity; SHALL journal intent before firing; SHALL consult the journal before every replay; SHALL reconcile ambiguous outcomes with the destination when possible; and SHALL persist a terminal result. If any effect in a batch fails, the whole batch SHALL hold with remediation and SHALL NOT return a partial-silent result.

#### Scenario: a retried invoice effects once
- **WHEN** the same scheduled invoice item is retried after any process interruption
- **THEN** the durable journal and destination reconciliation return the existing result or complete one effect without creating a duplicate

#### Scenario: a failed batch holds as a whole
- **WHEN** any item in a batch cannot be admitted, effected, or reconciled
- **THEN** the batch is held or fails with every item and reason visible, and no silent partial-success result is returned

### Requirement: Goal and universe inboxes feed timezone-aware schedules
Each goal and universe SHALL have an addressable durable webhook URL and email address for typed items from approved connector and human-drop sources. The boundary layer owns ingress, receipt, typing, and eligibility cutoff; `demand-side` owns the standing goal's timezone-aware schedule and execution. Eligible items SHALL join the next scheduled batch exactly once.

#### Scenario: a dropped item joins the next local-time batch
- **WHEN** an approved item reaches a goal inbox before its timezone-aware cutoff
- **THEN** the next scheduled run receives the item exactly once and records the inbox receipt and cutoff used

### Requirement: Adapters are credential-blind daemon-side proxies
Adapter code SHALL receive only a scoped domain, verb, and redacted request/response contract. Secret lookup, network execution, cap enforcement, and effect receipts SHALL remain inside a trusted daemon-side proxy, and adapter output SHALL be unable to reveal the credential material.

#### Scenario: a malicious adapter cannot read a secret
- **WHEN** adapter code attempts to inspect graph state, environment, request metadata, or proxy errors for credential material
- **THEN** it receives no secret and the attempt is denied and auditable

### Requirement: Non-MCP APIs use reviewed commons adapters
Native MCP servers SHALL be discovered at connect time from `{server, auth, scopes}` grants. The non-MCP long tail SHALL use reviewed, remixable, attributed commons adapters generated mechanically from OpenAPI into MCP-shaped actions and run as workflows; their generated surfaces SHALL be scoped, typed, cap-aware, and credential-blind before a universe can bind them. Connecting to an API is a universe action, not a platform integration ticket.

#### Scenario: a reviewed REST adapter becomes bindable
- **WHEN** a user supplies an API description and approves the generated scoped actions
- **THEN** the resulting connection class can be granted through the resource ledger without a platform-specific support ticket

### Requirement: Typed artifact flows fail at design time
Node inputs and outputs SHALL reference content-addressed artifacts carrying MIME type and an optional validated schema. Decoders and encoders SHALL be ordinary commons-supplied capability-class nodes rather than hidden platform integrations. Graph compilation SHALL reject an incompatible edge or unknown required type before a run starts or token spend; it SHALL NOT silently map an unknown declared type to `Any`.

#### Scenario: an incompatible artifact edge is rejected
- **WHEN** a producer output cannot satisfy the consumer's declared MIME/schema contract
- **THEN** graph compilation fails with the producer, consumer, and incompatible types named
