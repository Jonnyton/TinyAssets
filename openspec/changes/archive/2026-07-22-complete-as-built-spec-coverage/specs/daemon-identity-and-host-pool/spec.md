# Daemon identity and host pool

## ADDED Requirements

### Requirement: Daemon identities preserve explicit soul and lineage state

The current daemon registry SHALL create a named `daemon::` identity backed by
the author store, with `soulless` and `soul` modes, owner/tenant metadata,
domain claims, and a stable soul hash. A soul-mode daemon MUST have non-empty
soul text; equal soul hashes across differently named identities MUST name the
source daemon as `lineage_parent_id`.

#### Scenario: A soul identity records its claims and fingerprint

- **GIVEN** a caller creates a `soul` daemon with non-empty soul text and
  domain claims
- **WHEN** it reads that daemon with `include_soul=True`
- **THEN** the returned identity SHALL expose the soul mode, claims, and
  SHA-256 soul hash, and SHALL expose the soul text only on that explicit read.

#### Scenario: An unrecorded copied soul is refused

- **GIVEN** an existing soul daemon with a particular soul hash
- **WHEN** a caller creates a differently named daemon with the same soul text
  and no matching `lineage_parent_id`
- **THEN** creation SHALL fail rather than creating an unrecorded copy.

### Requirement: Runtime instances bind the daemon identity to an allowed model

The current daemon runtime SHALL persist each summoned instance with its daemon
ID, universe, provider, model, and copied daemon identity metadata. If a daemon
has an allowed-model binding, summon MUST reject a model outside that binding;
`ensure_daemon_runtime` SHALL reuse a matching worker slot or adopt one matching
unassigned slot before creating another instance.

#### Scenario: A bound daemon cannot be summoned with another model

- **GIVEN** a daemon whose metadata binds it to `gpt-5.5`
- **WHEN** a caller summons it with `gpt-5.4`
- **THEN** the current runtime SHALL reject the request with a model-identity
  mismatch and SHALL not create a runtime instance.

#### Scenario: A stable worker refreshes its existing slot

- **GIVEN** a provisioned runtime for the same daemon, provider, model,
  universe, and worker ID
- **WHEN** the worker calls `ensure_daemon_runtime` again
- **THEN** the current registry SHALL return the same runtime-instance ID and
  refresh it as `provisioned` rather than duplicating the slot.

### Requirement: Daemon control and behavior updates remain ownership scoped

The current daemon control API SHALL apply pause, resume, restart, banish, and
behavior-update effects only for an owner, delegated host, or applicable local
host scope. An unauthorized actor MUST receive a refused, proposal-only result
without changing runtime state; a restart SHALL be reported as queued rather
than claimed as an immediate restart.

#### Scenario: A non-owner cannot pause a runtime

- **GIVEN** a runtime whose daemon is owned by `host`
- **WHEN** another actor sends the `pause` control action
- **THEN** the result SHALL have `effect=refused` and `authority_scope=none`,
  and the runtime status SHALL remain unchanged.

#### Scenario: An owner pauses a runtime

- **GIVEN** that same runtime
- **WHEN** its owner sends the `pause` control action
- **THEN** the control result SHALL be applied and the persisted runtime status
  SHALL become `paused`.

### Requirement: The current host pool uses REST registration and heartbeat state

The current host-pool client SHALL register host rows through REST, provision a
capability row if absent, and retain the returned `host_id` for subsequent
operations. Host liveness MUST be represented by REST updates to `updated_at`;
the supplied heartbeat loop SHALL default to 300 seconds, reject intervals
below 30 seconds, and back off after transport failures.

#### Scenario: Registration provisions capability before the host row

- **GIVEN** a host registering a declared capability without explicit node and
  model components
- **WHEN** its capability ID is of the form `<node_type>:<llm_model>`
- **THEN** registration SHALL first ensure the capability row using those
  components and SHALL return the newly registered host row and `host_id`.

#### Scenario: Heartbeat failure does not terminate the loop

- **GIVEN** a running heartbeat loop whose REST heartbeat raises
  `HostPoolError`
- **WHEN** that tick fails
- **THEN** the loop SHALL report the error to its optional callback, apply a
  bounded exponential backoff, and continue until stopped.

### Requirement: Current bid discovery is polling-only and does not claim work

The current host pool SHALL fetch only pending requests matching one capability
with `paid` or `public` visibility, ordered oldest first and limited per poll.
`BidPoller` SHALL default to a 60-second REST polling interval and forward only
new request IDs to its callback; it MUST NOT claim, settle, or otherwise mutate
the request.

#### Scenario: Repeated polling does not re-notify the same request

- **GIVEN** two poll ticks that both return a request with the same
  `request_id`
- **WHEN** the poller processes the second tick in the same process lifetime
- **THEN** it SHALL omit that request from the callback payload.

#### Scenario: Realtime and distributed matching are not claimed as current behavior

- **GIVEN** an implementation or acceptance review of host discovery
- **WHEN** it describes the as-built host-pool contract
- **THEN** it SHALL identify REST `updated_at` heartbeat and 60-second request
  polling as the current behavior, and SHALL NOT claim WebSocket/Presence,
  realtime delivery, atomic bid matching, or automatic claim as implemented.
