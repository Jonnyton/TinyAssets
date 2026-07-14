# Boundary Layer: Inputs, Outputs, Connectivity

## Purpose

Define how universes connect to the outside world in both directions: the
platform serves MCP inward (chatbots → universes) and universes speak MCP outward
as clients (Gmail, accounting, calendars, anything). The platform builds no
integrations; nodes hold connections exactly as nodes hold models, and connector
definitions are commons artifacts. This capability composes existing primitives
(the design law holds); its worked example is the weekly payables run.

Historical source of record (untouched): `docs/exec-plans/active/2026-07-09-boundary-layer-design.md`.

## Requirements

### Requirement: MCP both directions; connections live in the resource ledger

The platform SHALL serve MCP inward and SHALL let universes speak MCP outward as
clients. Connector definitions (MCP client config + normalization workflows) SHALL
be commons artifacts, remixable with attribution. Credentials SHALL be user
grants, scoped per-universe, revocable; universes SHALL never own them. A
source/effector node SHALL declare its needed connection class (`source:gmail`,
`sink:<payables>`) and bind against the ledger's grants at run time.

#### Scenario: a node binds a connection class against a user grant
- **WHEN** a source/effector node needs an external connection
- **THEN** it declares its connection class and binds against the resource-ledger grant
- **AND** the universe never owns the credential (scoped per-universe, revocable)

### Requirement: Action caps are the second autonomy column

Alongside unprompted-SPEND caps, the system SHALL enforce unprompted-ACTION caps
(e.g. `read: auto · file: auto · send: auto · pay <= $500: auto · pay > $500:
hold-for-confirmation`). Consequential effectors SHALL default to
hold-above-threshold with an actionable confirmation surface — writes get gates
with useful holds, never silent behavior in either direction.

#### Scenario: a high-value payment holds for confirmation
- **WHEN** an effector would pay above the configured action-cap threshold
- **THEN** it holds for confirmation with an actionable surface
- **AND** below-threshold actions run automatically

### Requirement: Exactly-once effects (HARD RULE — Opus must not improvise)

The system SHALL enforce these three exactly-once effect rules verbatim — a deterministic idempotency key per effector call, an intent-then-result effect-ledger journal consulted before every replay, and a fail-loud hold-the-whole-batch failure posture with no partial-silent effects:

- Every effector call carries a **deterministic idempotency key** = hash(goal_id, schedule_period, item_fingerprint). "Invoice #4471 in the 2026-07-10 run" can effect exactly once, ever, across any number of retries.
- Every external effect is journaled in an **effect ledger** (intent row before firing, result row after), keyed by idempotency key; replays consult the journal first.
- Failure posture: fail loud, HOLD THE WHOLE BATCH, surface the hold with remediation. Never partial-silent. This is the boundary sibling of settlement conservation.

#### Scenario: a retried invoice effects exactly once
- **WHEN** an effector call is retried any number of times with the same idempotency key
- **THEN** the external effect happens exactly once (replays consult the journal first)
- **AND** the intent row is written before firing and the result row after

#### Scenario: a batch failure holds the whole batch loudly
- **WHEN** any effect in a batch fails
- **THEN** the whole batch holds and the hold surfaces with remediation
- **AND** no partial-silent effect occurs

### Requirement: Human-as-sensor goal inbox and timezone-aware scheduling

Standing goals SHALL expose an inbox so a user can drop items in from any surface
(e.g. a phone photo of a paper invoice) to join the next scheduled batch — inputs
are APIs and humans, symmetrically. Standing goals SHALL carry a timezone-aware
cron-class schedule executed on the proactivity heartbeat, and the schedule SHALL
be part of the goal spec, visible in the commons archetype.

#### Scenario: a dropped inbox item joins the next scheduled batch
- **WHEN** a user drops an item into a standing goal's inbox
- **THEN** it joins the next scheduled batch on the goal's timezone-aware schedule

### Requirement: HARD RULE — adapters never see credentials

The system SHALL enforce this HARD RULE verbatim — the connection runtime injects auth at the boundary and adapters SHALL receive authenticated transport but never keys; grants SHALL scope domains and verbs; every outbound call SHALL land in the effect ledger:

Commons adapter code + user secrets = credential theft as a service. The connection runtime injects auth at the boundary (proxy pattern): adapters declare scopes and receive authenticated transport, never keys. Grants scope domains + verbs; every outbound call lands in the effect ledger. Worst-case malicious adapter = in-scope, fully-journaled calls — never exfiltrated credentials.

#### Scenario: a malicious adapter cannot exfiltrate credentials
- **WHEN** a commons adapter attempts to read the raw credential
- **THEN** it receives only authenticated transport, never the key
- **AND** its worst case is in-scope, fully-journaled calls

### Requirement: Non-MCP APIs are covered by commons adapters

Native MCP servers SHALL be discovered at connect time (grants = {server, auth,
scopes}). The non-MCP long tail SHALL be covered by adapters as commons artifacts
— small programs wrapping an API into MCP shape, generated mechanically from an
OpenAPI spec and run as a workflow. "Connect to X" is something the universe DOES,
not a platform integration ticket; coverage is community-shaped.

#### Scenario: connecting to a non-MCP API is a universe action, not a platform ticket
- **WHEN** a universe needs to connect to a non-MCP API
- **THEN** it uses or generates a commons adapter (OpenAPI → MCP-shape)
- **AND** no platform integration ticket is required

### Requirement: Addressable inboxes and typed artifact flows fail loud at design time

Every universe/goal SHALL expose a webhook URL and an email address (e.g.
`pay@<user>.tinyassets.io`); inbox items SHALL be typed artifacts entering the
next scheduled run. Every node input/output SHALL be a typed artifact
(content-addressed blob + MIME + optional schema); decoders/encoders SHALL be
ordinary commons-supplied capability-class nodes. Type mismatches SHALL be
graph-validation errors at design time — pipelines fail loud before a token is
spent, never silently at run time.

#### Scenario: a type mismatch fails at design time, not at run time
- **WHEN** a pipeline connects incompatible typed artifacts
- **THEN** it is a graph-validation error at design time
- **AND** no token is spent and it never fails silently at the scheduled run

## Open founder decisions

None currently open. This is a binding design note composing existing primitives;
its rules (the two HARD RULES above plus action-cap and typed-artifact
invariants) are pinned.
