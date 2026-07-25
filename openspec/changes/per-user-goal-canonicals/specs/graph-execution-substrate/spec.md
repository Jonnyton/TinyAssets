## ADDED Requirements

### Requirement: Direct runs accept immutable Branch version targets
The runner SHALL accept a published `branch_version_id` as a first-class run target, reconstruct the Branch definition from that immutable snapshot, execute it through the shared run executor, and persist the version ID on the run record. It MUST NOT redirect a version-targeted run through the current live `branch_def_id` definition.

#### Scenario: Published version executes after live definition changes
- **WHEN** a caller starts a run with a published `branch_version_id` after the corresponding live Branch definition has changed
- **THEN** execution uses the published snapshot content and records that version ID on the run

#### Scenario: Unknown version fails loudly
- **WHEN** a caller starts a version-targeted run with an unknown `branch_version_id`
- **THEN** the runner rejects the request without starting the current live Branch definition

### Requirement: Gate rejection can route typed patch notes to the actor's Goal canonical
The evaluation contract SHALL support a `route_back` rejection decision containing a `goal_id` and typed `PatchNotes`. The route handler MUST derive `scope_actor` from the originating run actor, append the current `(goal_id, scope_actor)` hop to typed route history, resolve that actor's canonical with default and legacy fallback, and synchronously execute the resolved immutable `branch_version_id` with the patch notes as input. The decision MUST fail loudly for malformed notes, missing canonical/artifact, repeated hops, or route depth greater than three and MUST NOT accept caller-selected authority for another actor.

#### Scenario: Rejection routes to the actor's personal canonical
- **WHEN** a gate returns `route_back` with valid patch notes and the originating actor has a personal canonical for the Goal
- **THEN** the handler invokes that immutable version with the patch notes and records the route hop

#### Scenario: Rejection falls back to the Goal default
- **WHEN** a gate returns `route_back` and the originating actor has no personal canonical but the Goal has a default canonical
- **THEN** the handler invokes the immutable default version with the patch notes

#### Scenario: Missing canonical terminates the route
- **WHEN** neither an actor nor default nor legacy canonical can be resolved
- **THEN** the originating run terminates with a structured `no_canonical_bound` error

#### Scenario: Repeated route hop terminates the loop
- **WHEN** typed route history already contains the target `(goal_id, scope_actor)` or adding it would exceed three hops
- **THEN** the originating run terminates with a structured `route_back_loop` error and starts no routed run
