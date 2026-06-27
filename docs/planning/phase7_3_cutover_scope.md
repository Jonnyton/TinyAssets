# Phase 7.3 — Write-Handler Cutover Scope

**Author:** planner
**Date:** 2026-04-13

## 1. Enumerated write handlers

Two registries on the MCP surface carry write actions; 7.3 targets
the **shared-catalog** (goals, branches, nodes) subset. Universe-scoped
actions (add_canon, give_direction, submit_request, create_universe,
etc.) also mutate files but are scoped to a single user's clone, not
to the git-tracked catalog — lower priority, different migration.

**Catalog writes (branches + nodes + goals) — the 7.3 cutover set:**

| # | Handler | Writes to | Contract |
|---|---------|-----------|----------|
| 1 | `_ext_branch_build` (build_branch) | `branch_definitions` row + inline `node_defs` | Composite: create branch, add nodes, connect edges, validate. Single ledger entry. |
| 2 | `_ext_branch_patch` (patch_branch) | Same row | Transactional field patches on existing branch. |
| 3 | `_ext_branch_create` (create_branch) | `branch_definitions` row | Atomic: one empty branch. |
| 4 | `_ext_branch_delete` (delete_branch) | Row soft-delete | Soft-delete via `visibility=deleted`. |
| 5 | `_ext_branch_add_node` (add_node) | `node_defs` JSON field | Append single node. |
| 6 | `_ext_branch_connect_nodes` (connect_nodes) | `edges` JSON field | Append single edge. |
| 7 | `_ext_branch_set_entry_point` (set_entry_point) | `entry_point` field | Set once. |
| 8 | `_ext_branch_add_state_field` (add_state_field) | `state_schema` JSON field | Append one field. |
| 9 | `_ext_branch_update_node` (update_node) | Single node in `node_defs` | Stable node_id across edits; bumps `version`. |
| 10 | `_ext_branch_patch_nodes` (patch_nodes) | Multiple nodes transactionally | All-or-nothing. |
| 11 | `_action_goal_propose` (goals.propose) | `goals` row | Create. |
| 12 | `_action_goal_update` (goals.update) | `goals` row | Owner-gated. |
| 13 | `_action_goal_bind` (goals.bind) | `branch_definitions.goal_id` column | Cross-table: touches branch YAML. |

Thirteen, not twelve — the original spec estimate was one short. The
cutover set cleaves naturally into three clusters.

**Run-state writes NOT in 7.3 scope** (stay local per spec §Dual-write
+ §What-stays-local): `_action_judge_run`, `_action_rollback_node`
(writes to `run_lineage`), `_action_suggest_node_edit`,
`_action_cancel_run`. These touch `runs.db` or `node_edit_audit`,
both of which spec §What-stays explicitly keeps local.

**Universe-scoped writes** (deferred to a follow-up cutover, likely
Phase 7.5+): `_action_set_premise`, `_action_add_canon`,
`_action_give_direction`, `_action_submit_request`,
`_action_create_universe`, `_action_switch_universe`,
`_action_control_daemon`. Spec §7.7 draft workflow and §7.3 note
about `universe write_note/give_direction/submit_request` cover these
as a separate future slice.

## 2. Cutover strategy and order

Per-handler, not big-bang — matches spec §Architecture. Order by
**coupling footprint, then traffic**:

- **First: Goals cluster** (handlers 11-13). Three handlers, one row
  per write, no transactional-across-nodes shape. `goals.bind` is
  the only cross-table write — touches `branches.goal_id`. Smallest
  blast radius; best feedback loop for the pattern. G3's
  `save_goal_and_commit` is already queued.
- **Second: Single-entity branch writes** (handlers 3, 5, 6, 7, 8).
  Append-style: one field per handler. Easier than composites.
- **Third: Composite branch writes** (handlers 1, 2, 9, 10, 4).
  `build_branch` / `patch_branch` / `patch_nodes` are the
  transactional ones. Do these last because the commit-granularity
  question (§3a in 7.2 scope doc) matters most here — a composite
  that produces N nodes + 1 branch = N+1 YAML files should land as
  **one commit**, not N+1 commits. Implementation requires
  `git_bridge.commit` to take a staged-path list, not fire once per
  `stage()`.

Each cluster merges as one PR. Three PRs total, sequential on the
composite-commit shape question but otherwise parallel-safe.

## 3. Backend construction — lifecycle + thread safety

**Recommendation: one module-global `SqliteCachedBackend` instance
per process, lazily initialized on first use.**

- Lives in a new `tinyassets/storage/__init__.py` function
  `get_backend() -> StorageBackend` that memoizes.
- Construction reads `repo_root` from the git detection in
  `git_bridge.is_enabled()`. When `is_enabled()` returns False,
  returns a `SqliteOnlyBackend` — dev/test environments without a
  repo keep working.
- Env var `TINYASSETS_STORAGE_BACKEND` overrides (per §6 below).
- Thread safety: `SqliteCachedBackend` methods are stateless modulo
  the `self._stage_hook` call; `git_bridge.commit` serializes via
  the process-local lock (7.2 §5e risk). Concurrent `save_branch`
  calls are already serialized by the SQLite busy_timeout + the
  git commit lock.

**Construction points:**
- `_ensure_author_server_db()` is already called at the top of every
  Goals handler and every branch write; piggyback on this by making
  it also call `get_backend()` once. No new injection surface.
- Do **not** construct backend per-request — each construction does
  a git detection and defeats the `is_enabled()` cache.

## 4. Dirty-file refusal UX

When `has_uncommitted_changes(path)` returns True for the target
YAML path, we have a local-edit conflict (user edited the YAML in
their checkout; dispatcher tries to auto-commit over them).

**Recommendation: surface as a structured MCP-layer response, not
a backend raise.**

Shape (added to `_dispatch_with_ledger` + `_dispatch_goal_action`):

```json
{
  "status": "local_edit_conflict",
  "error": "Your clone has uncommitted edits to <path>. The server won't overwrite them.",
  "conflicting_path": "branches/research-paper.yaml",
  "options": [
    "git commit your edits, then retry the action",
    "git stash, retry the action, reapply",
    "pass force=true to this action to overwrite"
  ]
}
```

`force: bool = False` lands on every catalog write action as an
optional kwarg. When True, skips the dirty-check and proceeds.
Destructive ops (patch_branch, delete_branch, update_node,
rollback_node) MUST take the `force=true` via an explicit ask — do
not auto-force on retry.

Backend returns a typed result (not raise) so the dispatcher can
format the response consistently. The commit-granularity question
feeds this: composite operations check all target paths up-front
and fail the whole operation if any is dirty, not mid-write.

## 5. Test strategy

**Per-handler tests** for the three clusters — each cluster gets
its own test file:

- `test_phase7_3_goals_cutover.py` — 3 handlers × (happy path,
  dirty-file refusal, force-override, git-disabled no-op,
  round-trip rehydration) ≈ 15 tests.
- `test_phase7_3_branch_single_cutover.py` — 5 handlers × same
  matrix ≈ 25 tests.
- `test_phase7_3_branch_composite_cutover.py` — 5 handlers × same
  matrix + explicit N-files-one-commit assertion for composites
  ≈ 30 tests.

Plus one thin **integration test** in `test_phase7_3_integration.py`:
spin up real `git init` in tmp_path, build a branch, patch it, bind
a goal, `git log --oneline` should show three commits with the
expected ledger-parity messages. Asserts the end-to-end shape once;
the unit tests cover correctness.

Total new tests: ~70-80. In line with Phase 4's 44-test ship.

## 6. Rollback mechanism

**Recommendation: env-var backend selection — same knob that chooses
`sqlite_only` vs `sqlite_cached` in spec §Architecture.**

```
TINYASSETS_STORAGE_BACKEND=sqlite_only    # safe fallback
TINYASSETS_STORAGE_BACKEND=sqlite_cached  # 7.3 default after cutover
```

Default behavior:
- If env unset AND `git_bridge.is_enabled()` True → `sqlite_cached`.
- If env unset AND `git_bridge.is_enabled()` False → `sqlite_only`.
- Env var always wins when set.

**Why env, not feature flag per handler:** per-handler feature flags
accumulate cruft and make the cutover order legible in config rather
than in git history. One knob, two values, cutover order is the
merge order — simpler and easier to audit. If a specific handler
breaks in production, revert the cluster's PR; don't live with a
half-cutover indefinitely.

**Tray / host operator control:** surface the env var in
`tinyassets/desktop/tray.py` menu once G2/G3 land — a "Storage mode"
submenu with `sqlite_only` / `sqlite_cached` radio options. Lets the
user fall back without touching env vars. Out of 7.3 scope; file as
a 7.5 polish item.

## 7. Risks

1. **Commit granularity for composites.** `build_branch` producing
   1 branch + N nodes = N+1 YAML files must land as one commit. If
   G1's `commit()` only accepts a single message and composites call
   `stage()` N+1 times then `commit()` once, that's fine — but the
   backend has to NOT call `commit()` after each stage. Nail this
   contract in the G3 `save_branch_and_commit` helper before the
   composite cluster cuts over. Ship the composite cluster LAST for
   this reason.

2. **Dirty-file check cost.** `git diff --quiet HEAD -- <path>` is
   cheap but non-zero, and it runs on every write. On a slow disk
   or a repo with a huge working tree, that adds up. Mitigation:
   cache the dirty status per path for a short window (5s) within a
   single MCP session. Invalidate on successful write. Document as
   "acceptable latency tax" if caching gets complicated.

3. **Goal.bind cross-file coupling.** `goals.bind(branch_def_id,
   goal_id)` mutates `branches/<slug>.yaml` (goal_id field), not
   `goals/<slug>.yaml`. The handler naming suggests it's a goals
   write, but the storage effect is on a branch file. Two
   consequences: (a) the dirty-check must target the branch path,
   not the goal path; (b) the commit message should make the
   cross-table nature clear (`goals.bind: my-branch → my-goal`).
   Document this in the G3 helper shape so it doesn't surprise
   dev.

## 8. Dev task slicing

Four tasks; H1 is blocking, H2-H4 parallel after H1.

### H1 — Backend factory + env-var selection + dirty-file response shape

Wire `get_backend()` module-level singleton. Add
`force: bool = False` kwarg threading. Define the
`local_edit_conflict` response shape in the dispatcher layer. Wire
`TINYASSETS_STORAGE_BACKEND` env var. No handler cutover yet.

**Files:** `tinyassets/storage/__init__.py`, `tinyassets/universe_server.py`
(dispatcher helpers only), `tests/test_phase7_3_backend_factory.py`.
**Depends on:** G1, G2, G3.
**Risk:** low. Pure plumbing.

### H2 — Goals cluster cutover (handlers 11-13)

Three handlers: `_action_goal_propose`, `_action_goal_update`,
`_action_goal_bind`. Replace direct `save_goal` calls with
`get_backend().save_goal_and_commit(goal, author, message)`. Handle
the cross-file `goals.bind` case with a branch-path dirty-check.

**Files:** `tinyassets/universe_server.py` (3 handlers),
`tests/test_phase7_3_goals_cutover.py`.
**Depends on:** H1.
**Parallel-safe with:** H3.

### H3 — Single-entity branch cluster (handlers 3, 5, 6, 7, 8)

Five append-style handlers: `create_branch`, `add_node`,
`connect_nodes`, `set_entry_point`, `add_state_field`. Each writes
one branch YAML + potentially one node YAML. Simple `save_branch_and_commit`
wrap.

**Files:** `tinyassets/universe_server.py` (5 handlers),
`tests/test_phase7_3_branch_single_cutover.py`.
**Depends on:** H1.
**Parallel-safe with:** H2.

### H4 — Composite branch cluster (handlers 1, 2, 4, 9, 10)

Five transactional handlers: `build_branch`, `patch_branch`,
`delete_branch`, `update_node`, `patch_nodes`. Requires composite
commit semantics — N YAMLs staged, one commit. G3's
`save_branch_and_commit` must accept `extra_paths: list[Path]` for
multi-file writes. Coordinate with G3 on the signature.

**Files:** `tinyassets/universe_server.py` (5 handlers),
`tinyassets/storage/backend.py` (signature extension),
`tests/test_phase7_3_branch_composite_cutover.py`,
`tests/test_phase7_3_integration.py`.
**Depends on:** H1, H2 merged, H3 merged.
**Parallel-safe with:** nothing in 7.3 (ships last).

## 9. §7.3 spec amendments I'd flag

Two small sharpenings — both add clarity, neither breaks the spec's
direction:

1. **Handler count.** Spec says "~12 MCP write handlers"; the actual
   count per this audit is 13 (goals.bind is the missing one). Update
   to "~13" or drop the number and list them by handler name. Low
   priority.

2. **Cross-file writes.** Spec §7.3 treats each mutation as one
   file. `goals.bind` breaks that — it's a goals-action that writes
   a branch file. The "one commit per public action" semantics still
   hold, but the file-to-action mapping isn't 1:1. Add a sentence
   acknowledging cross-table writes exist and are committed as a
   single commit with a `<namespace>.<action>` message prefix.

3. **Composite commit semantics (not an amendment, a clarification
   the spec leaves implicit).** Spec says "writes its YAML, stages
   it, and commits immediately." Read literally for `build_branch`
   that's N+1 commits, which breaks the "one commit per public
   action" rule. Clarify: **one commit per MCP action, regardless of
   how many YAML files it touches.** Composites stage all, commit
   once. This is the safer read of the spec's intent; worth saying
   out loud.

None of these block the cutover. Hand dev a patch to the spec
alongside H1 so the reading order is clear.
