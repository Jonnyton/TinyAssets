# daemon-identity-and-host-pool Specification

## Purpose
Define daemon identity, ownership-scoped control, runtime binding, and the current REST registration, heartbeat, and non-claiming bid-polling host pool.
## Requirements
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
