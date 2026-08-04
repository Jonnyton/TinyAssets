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

### Requirement: External app events authenticate before normalization

The boundary SHALL authenticate an external app callback against the exact
bounded raw request body before parsing or normalizing it. For Slack Events API
callbacks, authority SHALL require the current app signing secret, a
constant-time match for the HMAC-SHA256 `v0` signature over
`v0:{request_timestamp}:{raw_body}`, and a request timestamp within five
minutes. A deprecated verification token, payload field, route parameter, or
caller-supplied tenant identifier SHALL NOT authenticate or redirect a request.

Only after authentication, the boundary SHALL validate a Slack
`event_callback` envelope and derive installation identity from its exact
`api_app_id` and `team_id`. It SHALL atomically journal
`(provider, installation_id, event_id)` with a digest of the authenticated raw
body and content-free routing evidence. An exact replay SHALL return the first
admission record without another write; the same identity with a different
digest SHALL fail closed. Authentication or envelope rejection SHALL write no
row. The ledger SHALL NOT persist the signing secret, signature, raw body,
message text, deprecated token, or normalized event payload.

This admission evidence SHALL NOT itself map a TinyAssets user, organization,
universe, agent binding, conversation, or runtime authority; issue a custody
grant; invoke a model; perform an effect; expose a public route; or add an MCP
handle.

#### Scenario: a signed Slack event is admitted once

- **WHEN** Slack delivers a bounded, current, correctly signed
  `event_callback` envelope for the configured app
- **THEN** the boundary verifies the raw bytes before parsing and persists one
  content-free admission record derived from the authenticated app, workspace,
  and event identity
- **AND** an exact concurrent or later replay returns that same record without
  creating a second admission

#### Scenario: forged or conflicting input has no authority

- **WHEN** the signature is absent, malformed, stale, wrong, or covers different
  bytes; the app identity is wrong; the envelope is malformed or oversized; or
  an admitted event identity is reused with a different body digest
- **THEN** admission fails closed before identity mapping, custody, runtime, or
  effects
- **AND** authentication or shape rejection writes no admission row

### Requirement: Adapters are credential-blind daemon-side proxies
Adapter code SHALL receive only a scoped domain, verb, and redacted request/response contract. Secret lookup, network execution, cap enforcement, and effect receipts SHALL remain inside a trusted daemon-side proxy, and adapter output SHALL be unable to reveal the credential material.

#### Scenario: a malicious adapter cannot read a secret
- **WHEN** adapter code attempts to inspect graph state, environment, request metadata, or proxy errors for credential material
- **THEN** it receives no secret and the attempt is denied and auditable

### Requirement: Execution admission binds opaque egress and credential requirements

The trusted outbound boundary SHALL resolve the
`egress_requirement_ref` and digest carried by an Engine OS logical
`ExecutionRequirement`, while the active credential-custody owner resolves its
`credential_requirement_ref` and digest. The boundary SHALL require the exact
resolved objects, digests, workload, profile, grant, destination, and proxy
authority to agree before network or credential access. A caller-supplied
object, replacement digest, generic connection grant, or proxy handle SHALL NOT
satisfy either requirement.

An admitted `source_exec/runner_source_exec` pairing SHALL provide deny-all
egress and no credential to the workload. An admitted
`inference_only/provider_cli` pairing SHALL expose only a redacted request to a
credential-blind provider transport and SHALL expose no raw key, token, auth
file, native-store locator, or other recoverable credential to model-controlled
work. Requester-owned remote HTTP SHALL use only the non-serializable scoped
proxy on the same attested requester-controlled host as native custody, and
that proxy SHALL resolve the provider-custody native reference rather than a
legacy vault `llm_api_key` record.

No profile SHALL be admissible until the outbound and credential owners publish
an exact compatible pairing for it. This requirement defines neither a
complete egress or credential taxonomy nor a complete compatibility matrix.
Missing, stale, mismatched, malformed, unknown, or unpublished bindings SHALL
fail before proxy creation, credential access, or network I/O.

#### Scenario: source execution has no outbound or credential path

- **WHEN** `source_exec/runner_source_exec` reaches boundary admission
- **THEN** its owner-published pairing resolves to deny-all egress and no credential available to the workload
- **AND** no grant, proxy, ambient route, or caller-supplied reference widens it

#### Scenario: provider inference remains credential-blind

- **WHEN** `inference_only/provider_cli` uses requester-owned remote HTTP
- **THEN** the exact egress and credential references and digests resolve to a jointly published compatible pairing
- **AND** only the same-host non-serializable proxy may resolve native custody and perform network I/O
- **AND** model-controlled work receives no recoverable credential material

#### Scenario: unpublished compatibility fails closed

- **WHEN** either owner binding is absent or valid on its own but no exact compatible pairing is published
- **THEN** admission fails before proxy creation, credential access, or network I/O
- **AND** the runtime does not infer compatibility from matching names, grants, or digests

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

### Requirement: Value-moving boundary effects settle through the single market transport
The boundary layer SHALL NOT create, hold, or reconcile monetary balances of its own. A boundary effect that moves value SHALL bind its journaled intent and terminal receipt to the single authenticated transaction transport owned by `paid-market-economy`, and any priced comparison it needs SHALL be read from the price/quote owner rather than computed at the boundary. The boundary contributes authority, caps, journaling, reconciliation, and receipts only. Real-fund wallet and chain effects remain owned by the separately reviewed §18.6 successor, which the boundary consumes and never re-implements.

#### Scenario: a value-moving effect has no boundary-local ledger
- **WHEN** an outbound effect transfers value
- **THEN** the accounting transition is recorded by the single market transaction transport and the boundary persists only its authority decision, journal entry, and terminal receipt

#### Scenario: the boundary does not compute its own price
- **WHEN** an outbound effect requires a priced comparison or an executable total
- **THEN** it consumes the quote owner's result and does not derive a competing price at the boundary

### Requirement: Outbound authority comes only from a current user grant
Every outbound effect SHALL execute under a current, unrevoked, per-universe grant bound to the authenticated owning user. An absent, revoked, expired, or ambiguous grant SHALL fail closed with an auditable denial. The boundary SHALL NOT fall back to host, maintainer, or ambient credentials, and SHALL NOT treat a retired or unresolved connection as permission to proceed.

#### Scenario: a revoked grant stops an in-flight retry
- **WHEN** a grant is revoked between an effect's journaled intent and its retry
- **THEN** the retry is denied and recorded rather than completing under the prior authority

#### Scenario: a missing grant never escalates to ambient credentials
- **WHEN** no grant resolves for the requested connection class
- **THEN** the effect fails closed and no host or maintainer credential is used
