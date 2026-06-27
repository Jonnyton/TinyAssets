---
status: shipped
shipped_date: 2026-04-12
shipped_in: c85efa1  # Community Branches Phases 2-5 + cross-universe cluster + user-sim harness
---

# Community Branches Phase 2 — Graph & State Design MCP Tools

**Status:** proposed (awaiting lead approval)
**Depends on:** Phase 1 (done — schema + storage landed 2026-04-11)
**Unblocks:** Phase 3 (generic graph runner), Phase 4 (social layer)

## Goal

Give any MCP client (especially Claude.ai on mobile) the ability to build, edit, and validate a `BranchDefinition` through natural conversation. One working end-to-end path for a non-fantasy domain ships Phase 2. Coverage beats polish — do not re-implement fork/publish here, that is Phase 4.

## Surface decision

**Extend the existing `extensions` tool, do not add a new coarse tool.** Rationale: `extensions` already owns node registration. `BranchDefinition` is just the aggregate form — nodes grouped into a graph with a state schema. Splitting into a second tool fragments the mental model, multiplies docstring bloat, and forces the user to learn where the seam is. Phase 2 adds actions to the same dispatcher.

## Actions to add to `extensions`

All actions use existing optional params where possible; new params listed inline. Return shape is JSON with `{branch_def_id, status, errors?}` unless noted.

**Branch lifecycle**
- `create_branch(name, description, domain_id?)` — create empty BranchDefinition, return `branch_def_id`.
- `get_branch(branch_def_id)` — return full BranchDefinition JSON.
- `list_branches(domain_id?, author?)` — summaries only (id, name, author, domain, node_count).
- `delete_branch(branch_def_id)` — soft delete; Phase 4 adds archive/restore.

**Topology authoring**
- `add_node(branch_def_id, node_id, display_name, description, phase?, prompt_template?, source_code?)` — adds a NodeDefinition *and* a GraphNodeRef in one step. Either prompt_template or source_code, not both.
- `connect_nodes(branch_def_id, from_node, to_node)` — add simple edge.
- `add_conditional_edge(branch_def_id, from_node, conditions_json)` — `conditions_json` is a stringified `{outcome: target}` map.
- `set_entry_point(branch_def_id, node_id)` — mark the graph entry.
- `remove_node(branch_def_id, node_id)` — also removes incident edges.

**State schema**
- `add_state_field(branch_def_id, field_name, field_type, reducer?, default?, description?)` — append to state_schema blob.
- `remove_state_field(branch_def_id, field_name)`.

**Validation & readiness**
- `validate_branch(branch_def_id)` — call `BranchDefinition.validate()`, return error list. Non-destructive. Client should call before handing off for a run.
- `describe_branch(branch_def_id)` — human-readable summary (nodes, edges, entry, state fields, open problems). Purpose: phone-legibility — the user asks "what does my branch look like?" and gets a paragraph, not a JSON dump.

## UX vignettes

**Non-technical phone user — "I want to track my recipes":**

1. Claude.ai calls `extensions action=create_branch name="Recipe tracker"`.
2. Claude proposes three nodes in chat; user says yes.
3. Claude calls `add_node` three times: `capture` (prompt_template), `categorize` (prompt_template), `archive` (prompt_template).
4. Claude calls `connect_nodes` twice + `set_entry_point capture`.
5. Claude calls `add_state_field` for `raw_recipe`, `category`, `archived`.
6. Claude calls `validate_branch` — passes.
7. Claude calls `describe_branch` and renders the summary to the user.

The user never types JSON. Claude.ai does all the argument shaping. Success criterion: a non-technical user can build this branch in under 20 messages on a phone.

**Nerdy-user path — same tool, different depth.** Power users pass `source_code` instead of `prompt_template`, write their own reducers via `add_state_field reducer=append`, and inspect errors from `validate_branch` directly. Do **not** build a second tool surface. The same 12 actions serve both audiences — the difference is how much Claude.ai abstracts on the user's behalf.

## Minimum-to-ship cut

Ship these 10 actions. Defer the rest to Phase 3/4:

**Ship Phase 2:** create_branch, add_node, connect_nodes, set_entry_point, add_state_field, validate_branch, describe_branch, get_branch, list_branches, delete_branch.

**Defer:** add_conditional_edge (Phase 3 — only matters once a runner exists), remove_node/remove_state_field (Phase 3 — ergonomics, not blocking a first run), fork/publish/rate (Phase 4 social layer).

Rationale: conditional edges are dead weight without a runner to execute them. Removal is a nice-to-have for iteration but a user building their first branch can re-create it faster than debugging a half-broken one.

## Risk & bug dependencies

**Hard gate — #11 (ledger bypass).** Every Phase 2 write action creates a community-visible artifact. If writes still skip the public action ledger, branch authorship is unattributed and the social layer in Phase 4 collapses. **#11 must land before Phase 2 merges**, or Phase 2 must explicitly write-through the ledger in each handler (add a ledger write to each action that mutates a BranchDefinition).

**Soft concerns, not blockers:**
- #12 (word_count inconsistency), #17 (accept_rate always 0): telemetry-layer bugs — unrelated to branch authoring.
- #13 (backslash-n premise), #15 (cross-universe leak), #16 (dormant daemon misreported): output-rendering / state-read bugs in the `universe` tool — do not touch `extensions` surface.
- #4/#5 (docstring trim): run Phase 2 docstrings through the trim pattern from the start. Each new action gets a one-line entry in the `extensions` action list, no per-action prose — move rich reference into a new `branch_design_guide` prompt.

**Architectural risk:** Phase 2 ships tools the user can call, but there is no runner yet (Phase 3). A validated branch just sits in SQLite. Be explicit about this in the `describe_branch` output: "This branch is validated but cannot yet be executed — a runner is coming." Otherwise users will build branches, hit END, and report it as broken.

## Acceptance criteria

1. All 10 ship-list actions registered in `tinyassets/universe_server.py` under `extensions`.
2. Each action writes through the public action ledger (or #11 lands first).
3. A `branch_design_guide` MCP prompt walks users through the recipe-tracker vignette.
4. End-to-end test: build the recipe-tracker BranchDefinition via MCP calls only, `validate_branch` returns no errors, `describe_branch` produces a coherent paragraph.
5. Docstring for each new action is ≤ 2 lines; rich reference lives in the prompt.
