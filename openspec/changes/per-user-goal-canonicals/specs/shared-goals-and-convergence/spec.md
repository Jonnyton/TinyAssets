## MODIFIED Requirements

### Requirement: A canonical branch version records the Goal's best-known version, author/host-only
A Goal SHALL retain at most one default `canonical_branch_version_id`, while the system SHALL additionally store at most one active published Branch version per `(goal_id, scope_actor)` in `goal_canonicals`. `scope_actor=''` SHALL represent the default canonical; a non-empty scope SHALL be the exact authenticated actor ID. `goals action=set_canonical` with empty or absent `scope` SHALL retain the existing Goal-author or canonical-capability authorization, update both the legacy Goal column and the default `goal_canonicals` row, and preserve canonical history. A non-empty action `scope` SHALL be persisted as `scope_actor`, be writable only when it exactly equals the authenticated actor, and SHALL NOT update the legacy Goal column or default row. A supplied version SHALL be validated as a published branch version whose status is `active`; an empty `branch_version_id` SHALL unset only the authorized scope.

#### Scenario: Author sets the default canonical version
- **WHEN** the Goal author invokes `goals action=set_canonical` with a published active `branch_version_id` and no `scope`
- **THEN** the Goal's legacy `canonical_branch_version_id` and `goal_canonicals` default row are updated to that version
- **AND** the prior default is recorded in canonical history

#### Scenario: Actor sets their own personal canonical
- **WHEN** an authenticated actor invokes `set_canonical` for a visible Goal with `scope` equal to their actor ID and an active published version
- **THEN** the actor-scoped row is upserted without changing the Goal default or another actor's row

#### Scenario: Cross-actor personal write is rejected
- **WHEN** any actor, including the Goal author or a capability holder, supplies a non-empty `scope` different from the authenticated actor
- **THEN** the call is rejected and all canonical rows remain unchanged

#### Scenario: Default non-author without capability is rejected
- **WHEN** an actor who is neither the Goal author nor holder of the canonical-branch capability invokes `set_canonical` without a personal scope
- **THEN** the call is rejected and the default canonical is unchanged

#### Scenario: Non-active or unpublished version is rejected
- **WHEN** `set_canonical` is called with a `branch_version_id` that is not a published version, or whose status is not `active`
- **THEN** the call is rejected with an error explaining only active published versions may be canonical

#### Scenario: Personal unset falls back without changing default
- **WHEN** an actor invokes `set_canonical` for their own scope with an empty `branch_version_id`
- **THEN** only that actor-scoped row is deleted and subsequent resolution falls back to the default canonical

#### Scenario: Transition read falls back to the legacy column
- **WHEN** no matching actor row and no default `goal_canonicals` row exists but the legacy Goal column is populated
- **THEN** canonical resolution returns the legacy `canonical_branch_version_id`

#### Scenario: Goal get reports the current actor's resolved canonical
- **WHEN** an authenticated actor invokes `goals action=get` for a Goal
- **THEN** the response keeps `goal.canonical_branch_version_id` as the legacy default
- **AND** separately reports the current `scope_actor` and that actor's resolved canonical version

### Requirement: run_canonical executes against the canonical binding with optional leaderboard refresh
`goals action=run_canonical` SHALL resolve the authenticated actor's personal canonical before the Goal default and SHALL dispatch the chosen immutable version through the existing `run_branch_version` path so executor, provider, and recursion-limit behavior are shared. A personal binding SHALL bypass default leaderboard refresh. When no personal binding exists and the Goal's `auto_canonical_via_leaderboard` flag is set, the default canonical SHALL first be refreshed to the leaderboard's top entry subject to the completed-run threshold and in-flight guard. When no personal or default canonical exists and auto-refresh is off, the call SHALL be rejected with `error_kind=no_canonical_handler`. The response SHALL report `branch_version_id_used`, `scope_actor`, and a source describing the resolution.

#### Scenario: Personal canonical dispatches via run_branch_version
- **WHEN** an actor with a personal canonical invokes `run_canonical`
- **THEN** a run is dispatched through `run_branch_version` against that exact actor-scoped `branch_version_id`
- **AND** the response reports `source=actor_canonical`, the actor scope, and `branch_version_id_used`

#### Scenario: Default canonical dispatches when no personal binding exists
- **WHEN** an actor without a personal binding invokes `run_canonical` and the Goal has a default canonical
- **THEN** the existing default version is dispatched through `run_branch_version`

#### Scenario: No canonical and auto-refresh off is rejected
- **WHEN** `run_canonical` is invoked on a Goal with no personal or default canonical and auto-canonical refresh disabled
- **THEN** the call is rejected with `error_kind=no_canonical_handler`

#### Scenario: Auto-refresh changes only the default
- **WHEN** an actor without a personal binding invokes `run_canonical` with auto-canonical refresh enabled and a leaderboard candidate meeting the threshold
- **THEN** only the default canonical is refreshed and dispatched
- **AND** existing personal rows remain unchanged
