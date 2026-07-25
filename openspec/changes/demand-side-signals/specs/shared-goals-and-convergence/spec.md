> Supersession note. The as-built requirement below specifies the Goal surface as
> "one `goals` tool that dispatches a **fixed** table of named actions" and
> enumerates that table. Standing goals add fields to the Goal record and the
> actions that register, reschedule, pause, and resume them, so the fixed table
> and the record shape both change. Rather than assert those additions in the
> `demand-side` delta and leave canonical truth describing a table that no longer
> matches, the change is carried here as a MODIFIED delta — the same drift-honest
> treatment `outbound-boundary-layer` gives its `external-effect-receipts`
> contradiction. `demand-side` SHALL NOT sync without this delta.
>
> Nothing else in this capability is touched: binding, canonical versions,
> `run_canonical`, selectors, protocols, subscriptions, common-node discovery,
> archive consultation, gate ladders, gate claims, gate bonuses, and the
> ChatGPT alias normalization are all unchanged.

## MODIFIED Requirements

### Requirement: Goals are first-class shared primitives on a single dispatch surface
Goals SHALL be first-class shared objects that capture the intent a workflow serves, reachable through one `goals` tool that dispatches a fixed table of named actions (`propose`, `update`, `bind`, `list`, `get`, `search`, `leaderboard`, `common_nodes`, `archive_consultation`, `set_canonical`, `define_protocol`, `get_protocol`, `run_canonical`, `set_selector`, `set_schedule`, `clear_schedule`, `pause`, `resume`). A proposed Goal SHALL be assigned a stable `goal_id`, recorded with its proposing author, and stored authoritatively in the SQLite `goals` table by the daemon store. The Goal record SHALL additionally carry the standing-goal coordination fields — desired outcome, owning principal, IANA-timezone cron-class schedule or event trigger, declared budget posture, success gates, and pause state — so a standing goal is fields and lifecycle on the existing Goal rather than a parallel object. The added actions SHALL extend the same fixed table and SHALL NOT introduce a second Goal surface or a new top-level tool; they remain subject to the same `require_action_scope("goals", canonical_action)` gate, the same unknown-action error path, and the same best-effort contribution attribution as every other recognized action. When a git repository backs the universe, the catalog backend SHALL additionally mirror each Goal to `goals/<slug>.yaml` and commit it in a single commit; universes without a backing repository (SQLite-only) SHALL still create the Goal but skip the YAML mirror and commit. Ownership lives in the `tinyassets/api/market.py` goal handlers and the `tinyassets/daemon_server.py` / `tinyassets/catalog` store.

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

#### Scenario: Standing-goal actions extend the same table rather than adding a surface
- **WHEN** a caller invokes `goals action=set_schedule`, `clear_schedule`, `pause`, or `resume`
- **THEN** the action dispatches through the same `goals` table under the same scope gate as every other recognized action
- **AND** no second Goal tool, top-level handle, or parallel standing-goal surface exists

#### Scenario: An unrecognized standing-goal action still returns the available-action error
- **WHEN** a caller invokes a standing-goal-shaped action name that is not in the table
- **THEN** the surface returns the available-action error before authorization or handler dispatch
