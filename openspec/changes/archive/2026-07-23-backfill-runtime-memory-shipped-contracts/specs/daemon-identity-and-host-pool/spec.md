## ADDED Requirements

### Requirement: Project-loop soul selection is explicit and deterministic

The daemon registry SHALL select the last registry-ordered soul-bearing daemon
that is explicitly marked either `project_loop_default` or with both
`project_default` and `loop_primary`; it MUST ignore soulless and unmarked
daemons and return no daemon when no eligible identity exists.

#### Scenario: A newer eligible soul becomes the project loop identity

- **WHEN** multiple soul-bearing daemons are marked as project-loop defaults
- **THEN** `select_project_loop_daemon` returns the last eligible daemon in registry order and includes soul text only when explicitly requested

#### Scenario: A soulless default marker cannot opt into soul guidance

- **WHEN** a soulless daemon has a project-loop marker but no eligible soul-bearing daemon exists
- **THEN** `select_project_loop_daemon` returns no daemon

### Requirement: Daemon behavior history is ownership-scoped, versioned, and bounded

The daemon registry SHALL refuse an unauthorized behavior update without
mutating daemon metadata. An authorized update SHALL increment
`behavior_version`, append a proposal carrying its ID, version, proposer,
status, and payload, and retain only the newest 25 proposals; it MUST update
`behavior_policy` only when `apply_now` is true.

#### Scenario: Proposal-only update advances history without applying policy

- **WHEN** an authorized actor submits a behavior update with `apply_now=false`
- **THEN** the result is queued, the versioned proposal is retained as `proposed`, and the active `behavior_policy` is unchanged

#### Scenario: Applied update becomes the active policy

- **WHEN** an authorized actor submits a behavior update with `apply_now=true`
- **THEN** the result is applied, the proposal status is `applied`, and `behavior_policy` equals the submitted update

#### Scenario: Behavior history keeps only its newest entries

- **WHEN** an authorized actor records more than 25 behavior updates
- **THEN** daemon metadata retains only the newest 25 proposals while `behavior_version` continues increasing

## MODIFIED Requirements

### Requirement: The current host pool uses REST registration and heartbeat state

The current host-pool client SHALL register host rows through REST, provision a
capability row if absent, and retain the returned `host_id` for subsequent
operations. Registration SHALL always insert a new row, even for a repeated
owner-capability pair, and the typed result MUST retain owner, provider,
capability, visibility, optional `price_floor`, `max_concurrent`,
`always_active`, and version. When explicit capability components are absent,
registration MUST split `<node_type>:<llm_model>` on the first colon or use the
whole capability ID with model `unknown`; deregistration SHALL delete only the
supplied `host_id`. Host liveness MUST be represented by REST updates to
`updated_at`; the supplied heartbeat loop SHALL default to 300 seconds, reject
intervals below 30 seconds, and on `HostPoolError` set the first retry delay to
`min(30 seconds, configured maximum)`, then double the prior delay up to that
maximum. An exception raised by the optional error callback MUST be logged and
swallowed so the loop continues until stopped.

#### Scenario: Registration provisions capability before the host row

- **GIVEN** a host registering a declared capability without explicit node and
  model components
- **WHEN** its capability ID is of the form `<node_type>:<llm_model>`
- **THEN** registration SHALL first ensure the capability row using those
  components and SHALL return the newly registered host row and `host_id`.

#### Scenario: Repeated registration creates distinct host sessions

- **WHEN** the same owner registers the same capability twice
- **THEN** each call inserts and returns a newly created host row rather than reusing an owner-capability singleton

#### Scenario: Registration preserves economic and capacity fields

- **WHEN** registration supplies visibility, price floor, concurrency, and always-active values
- **THEN** the returned typed row retains those values together with its server version

#### Scenario: Capability fallback and exact deregistration remain bounded

- **WHEN** a capability ID has no colon and its registered host is later deregistered
- **THEN** capability provisioning uses the whole ID with model `unknown` and cleanup deletes only the retained `host_id`

#### Scenario: Heartbeat failure does not terminate the loop

- **GIVEN** a running heartbeat loop whose REST heartbeat raises
  `HostPoolError`
- **WHEN** that tick fails
- **THEN** the loop SHALL report the error to its optional callback, apply a
  bounded exponential backoff, and continue until stopped.

#### Scenario: A failing heartbeat error callback is isolated

- **WHEN** a heartbeat raises `HostPoolError` and the configured `on_error` callback also raises
- **THEN** both failures are logged, the computed bounded retry delay is retained, and the loop proceeds to a later tick

### Requirement: Current bid discovery is polling-only and does not claim work

The current host pool SHALL fetch only pending requests matching one capability
with `paid` or `public` visibility, ordered oldest first and limited per poll.
`BidPoller` SHALL default to a 60-second REST polling interval and forward only
new request IDs to its callback; it MUST NOT claim, settle, or otherwise mutate
the request. Modeled REST failures and exceptions raised by `on_requests` SHALL
be logged and swallowed so the poll loop continues; IDs are marked seen before
callback invocation and therefore remain suppressed even when the callback
raises.

#### Scenario: Repeated polling does not re-notify the same request

- **GIVEN** two poll ticks that both return a request with the same
  `request_id`
- **WHEN** the poller processes the second tick in the same process lifetime
- **THEN** it SHALL omit that request from the callback payload.

#### Scenario: A failing bid callback is isolated

- **WHEN** the bid poller receives new rows and `on_requests` raises
- **THEN** the callback error is logged, the loop continues, and those request IDs are not re-notified in that process

#### Scenario: Realtime and distributed matching are not claimed as current behavior

- **GIVEN** an implementation or acceptance review of host discovery
- **WHEN** it describes the as-built host-pool contract
- **THEN** it SHALL identify REST `updated_at` heartbeat and 60-second request
  polling as the current behavior, and SHALL NOT claim WebSocket/Presence,
  realtime delivery, atomic bid matching, or automatic claim as implemented.
