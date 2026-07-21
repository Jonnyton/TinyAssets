## ADDED Requirements

### Requirement: Goals are first-class shared primitives on a single dispatch surface
Goals SHALL be first-class shared objects that capture the intent a workflow serves, reachable through one `goals` tool that dispatches a fixed table of named actions (`propose`, `update`, `bind`, `list`, `get`, `search`, `leaderboard`, `common_nodes`, `archive_consultation`, `set_canonical`, `define_protocol`, `get_protocol`, `run_canonical`, `set_selector`). A proposed Goal SHALL be assigned a stable `goal_id`, recorded with its proposing author, and stored authoritatively in the SQLite `goals` table by the daemon store. When a git repository backs the universe, the catalog backend SHALL additionally mirror each Goal to `goals/<slug>.yaml` and commit it in a single commit; universes without a backing repository (SQLite-only) SHALL still create the Goal but skip the YAML mirror and commit. Ownership lives in the `tinyassets/api/market.py` goal handlers and the `tinyassets/daemon_server.py` / `tinyassets/catalog` store.

#### Scenario: Proposing a Goal assigns an id and author
- **WHEN** a caller invokes `goals action=propose` with a `name`
- **THEN** a new Goal is created with a stable `goal_id` and the proposing actor recorded as author
- **AND** the response reports status `proposed` with the stored Goal

#### Scenario: Propose requires a name
- **WHEN** a caller invokes `goals action=propose` with an empty `name`
- **THEN** the call is rejected with an error stating `name` is required
- **AND** no Goal is created

#### Scenario: Repo-backed propose writes YAML and one commit; SQLite-only skips it
- **WHEN** `goals action=propose` runs against a universe with a git repository
- **THEN** the Goal is persisted to the SQLite `goals` table and mirrored to `goals/<slug>.yaml` in exactly one commit
- **AND** when the same action runs in a SQLite-only universe, the Goal is still created but no YAML mirror or commit is produced

### Requirement: Branches converge on a Goal by binding
Convergence SHALL be expressed by binding a Branch definition to a Goal: `goals action=bind` with a `branch_def_id` and a `goal_id` attaches the Branch to that Goal, and an empty `goal_id` unbinds the Branch from its current Goal. Bind SHALL reject a missing Branch, a missing Goal, and a soft-deleted (`visibility=deleted`) Goal. The binding SHALL be recorded on the Branch definition so that many Branches can converge on one shared Goal.

#### Scenario: Binding attaches a Branch to a Goal
- **WHEN** a caller invokes `goals action=bind` with a valid `branch_def_id` and `goal_id`
- **THEN** the Branch is attached to the Goal and the response reports status `bound`

#### Scenario: Empty goal_id unbinds
- **WHEN** a caller invokes `goals action=bind` with a valid `branch_def_id` and an empty `goal_id`
- **THEN** the Branch is detached from its previous Goal and the response reports status `unbound`

#### Scenario: Bind rejects a soft-deleted Goal
- **WHEN** a caller invokes `goals action=bind` targeting a Goal whose visibility is `deleted`
- **THEN** the call is rejected and the Branch binding is unchanged

### Requirement: A canonical branch version records the Goal's best-known version, author/host-only
A Goal SHALL hold at most one `canonical_branch_version_id` designating the best-known Branch version for that Goal. `goals action=set_canonical` SHALL be permitted only for the Goal's author or an actor holding the canonical-branch capability, and SHALL reject any other actor. A supplied version SHALL be validated as a published branch version whose status is `active`; a non-published or non-active (rolled-back / superseded) version SHALL be rejected. An empty `branch_version_id` SHALL unset the canonical, and the previous canonical SHALL be recorded in the Goal's canonical history.

#### Scenario: Author sets the canonical version
- **WHEN** the Goal author invokes `goals action=set_canonical` with a published active `branch_version_id`
- **THEN** the Goal's `canonical_branch_version_id` is updated to that version

#### Scenario: Non-author without capability is rejected
- **WHEN** an actor who is neither the Goal author nor holder of the canonical-branch capability invokes `set_canonical`
- **THEN** the call is rejected and the canonical is unchanged

#### Scenario: Non-active or unpublished version is rejected
- **WHEN** `set_canonical` is called with a `branch_version_id` that is not a published version, or whose status is not `active`
- **THEN** the call is rejected with an error explaining only active published versions may be canonical

### Requirement: run_canonical executes against the canonical binding with optional leaderboard refresh
`goals action=run_canonical` SHALL dispatch a run against the Goal's canonical binding, delegating actual execution to the existing `run_branch_version` path so executor, provider, and recursion-limit behavior are shared. When the Goal has no canonical handler and auto-refresh is off, the call SHALL be rejected with `error_kind=no_canonical_handler`. When the Goal's `auto_canonical_via_leaderboard` flag is set, the canonical SHALL first be refreshed to the leaderboard's top entry, subject to the `min_completed_runs_for_canonical` threshold and an in-flight-run guard that defers refresh while a canonical run is already in progress. The response SHALL report `branch_version_id_used` and a `source` describing which version was chosen and why.

#### Scenario: Stored canonical dispatches via run_branch_version
- **WHEN** a Goal has a stored canonical version and `run_canonical` is invoked
- **THEN** a run is dispatched through the existing `run_branch_version` path against that version
- **AND** the response reports the `branch_version_id_used` and `source`

#### Scenario: No canonical and auto-refresh off is rejected
- **WHEN** `run_canonical` is invoked on a Goal with no canonical version and `auto_canonical_via_leaderboard` disabled
- **THEN** the call is rejected with `error_kind=no_canonical_handler`

#### Scenario: Auto-refresh promotes the leaderboard top then dispatches
- **WHEN** `run_canonical` runs on a Goal with `auto_canonical_via_leaderboard` enabled and a leaderboard candidate meeting the completed-runs threshold
- **THEN** the canonical is refreshed to that candidate and the run dispatches against it
- **AND** when the candidate has insufficient completed runs the stored canonical is kept, and when a canonical run is already in flight the refresh is deferred

### Requirement: The Goal leaderboard is synthesized by a user-bound selector branch
Ranking of a Goal's bound Branches SHALL be performed by a user-buildable selector Branch, not a fixed platform weighting formula (DESIGN-008). `goals action=set_selector` SHALL bind a published branch version as the Goal's selector and SHALL be permitted only for the Goal author or an actor holding the selector-bind capability. An empty `branch_version_id` SHALL unbind and fall back to the platform default selector. The bound selector Branch SHALL be pure: a Branch that carries node effects or invokes child Branches SHALL be rejected so a selector cannot cause side effects while ranking.

#### Scenario: Author binds a selector branch
- **WHEN** the Goal author invokes `goals action=set_selector` with a valid selector `branch_version_id`
- **THEN** the Goal records that selector and future leaderboard synthesis dispatches it to rank candidates

#### Scenario: Non-author without capability is rejected
- **WHEN** an actor who is neither the Goal author nor holder of the selector-bind capability invokes `set_selector`
- **THEN** the call is rejected and the selector binding is unchanged

#### Scenario: A selector branch with effects is rejected
- **WHEN** `set_selector` is called with a Branch that carries node effects or invokes a child Branch
- **THEN** the call is rejected with a structured effects error and no selector is bound

#### Scenario: Empty branch_version_id unbinds to the default selector
- **WHEN** `set_selector` is called with an empty `branch_version_id`
- **THEN** the Goal's selector is unbound and leaderboard calls fall back to the platform default selector

### Requirement: Goal writes are authorization-scoped and appended to the global contribution ledger
Every `goals` invocation SHALL pass through the `require_action_scope("goals", action)` gate before dispatch. Write actions (`propose`, `update`, `bind`, `set_canonical`, `define_protocol`, `set_selector`) SHALL require an authenticated goals scope, while read actions SHALL remain available to anonymous callers; a rejected write SHALL return a structured error flagged `auth_scope_required`. On a successful write action, the surface SHALL append a `goals.<action>` entry to the global contribution ledger for public attribution.

#### Scenario: Anonymous write is rejected with an auth flag
- **WHEN** an unauthenticated caller invokes a goals write action such as `propose`
- **THEN** the call is rejected with a structured error carrying `auth_scope_required: true`

#### Scenario: Successful write records a contribution-ledger entry
- **WHEN** an authorized caller completes a goals write action (for example `propose` or `bind`)
- **THEN** a `goals.<action>` entry is appended to the global contribution ledger identifying the target

### Requirement: Per-universe participation in shared Goals is opt-in via subscriptions
A universe SHALL participate in a Goal's cross-universe work pool only by explicitly subscribing to that Goal slug; participation SHALL NOT be implicit. A fresh-install universe with no subscriptions file SHALL behave as subscribed to exactly `["maintenance"]`. The goal-pool producer SHALL be flag-gated (`TINYASSETS_GOAL_POOL`); when enabled it SHALL read `goal_pool/<goal_slug>/*.yaml` only for the universe's subscribed goals, turning each pool YAML into a Branch task whose `inputs` are constrained to a flat dictionary of primitive values so per-universe state cannot cross the isolation boundary.

#### Scenario: Fresh install defaults to the maintenance subscription
- **WHEN** the daemon reads subscriptions for a universe that has no subscriptions file
- **THEN** the universe is treated as subscribed to `["maintenance"]` only

#### Scenario: The pool producer only reads subscribed goals when enabled
- **WHEN** `TINYASSETS_GOAL_POOL` is enabled and the goal-pool producer runs
- **THEN** it scans `goal_pool/<goal_slug>/*.yaml` only for the universe's subscribed goals and emits Branch tasks with flat-primitive inputs
- **AND** when the flag is off no goal-pool producer is registered and pool reads are a no-op
