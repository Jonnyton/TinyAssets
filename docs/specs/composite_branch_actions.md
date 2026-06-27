---
status: shipped
shipped_date: 2026-04-12
shipped_in: c85efa1  # Phase 2-5 bundle that introduced tinyassets/branches.py + composite actions
---

# Composite Branch Actions — `build_branch` and `patch_branch`

**Status:** proposed (fast-track — blocking Mission 4).
**Depends on:** Phase 2 landed (atomic actions exist).
**Unblocks:** Mission 4 phone-surface quality; reduces workflow build from 15–20 round trips to 1–2.

## Goal

Claude.ai's tool-use-per-turn limit maxed out on a single workflow build. Fine-grained actions (`add_node`, `connect_nodes`, `add_state_field`, `set_entry_point`) force one round trip each. Compose them.

Add two MCP actions to the existing `extensions` tool:

- `build_branch(spec)` — full BranchDefinition spec → validated branch, one call.
- `patch_branch(branch_def_id, changes)` — batch edits, one call.

Fine-grained actions stay for surgical edits. The `control_station` prompt teaches: default to composite; use atomic only when changing one thing.

## `build_branch(spec)`

Input is a dict in BranchDefinition shape: `{name, description?, domain_id?, tags?, node_defs: [...], edges: [...], conditional_edges?: [...], state_schema?: [...], entry_point?}`. Node defs carry `node_id`, `display_name`, `description`, `phase`, `prompt_template` or `source_code`, `input_keys`, `output_keys`. Each edge is `{from, to}`.

Internally: begin transaction → `create_branch` → loop `add_node`/`connect_nodes`/`add_state_field` → `set_entry_point` → `validate` → commit. On validation failure, roll back. No partial branch is ever visible.

## `patch_branch(branch_def_id, changes)`

`changes` is an ordered list of ops. Each op: `{op: "add_node"|"remove_node"|"add_edge"|"remove_edge"|"add_state_field"|"remove_state_field"|"set_entry_point"|"update_node", ...op-specific fields}`. Applied in order against a staging copy of the branch; validate at end; commit atomically.

## Key decisions

**Strict-with-suggestions, not lenient.** `build_branch` rejects ambiguous specs (missing entry_point when the graph requires one, disconnected nodes, unknown state field types, unknown phase). But every error response carries a `suggestions` field with concrete fixes: `[{issue, proposed_fix}]`. Example: missing entry_point → suggest the first node with no incoming edge. Unknown state type → suggest closest valid type. This keeps the guardrail while minimizing additional round trips: Claude.ai can often apply the suggestion on the same turn's reasoning.

Rationale: autocompleting silently corrupts user intent on phone builds where Claude.ai can't re-confirm. Rejecting outright burns a round trip. Suggestions land in the middle — one error response often carries enough to fix the spec without a second call.

**Transactional, not best-effort.** `patch_branch` reverts the whole batch on any op failure. Per-op errors returned in `errors: [{op_index, op, error, suggestion?}]`. Rationale: a half-applied patch leaves the graph in a state the user didn't ask for and can't easily describe. Transactional is easier to explain, easier to retry, and the common case (an MCP client batching coherent edits) doesn't benefit from best-effort.

**Tool-return shape on success** (per `tool_return_shapes.md`, "ordered steps with directed connections" pattern):
- `text`: one-line ack (`Built branch <name> (id: <id>): N nodes, M edges, entry=<node>`), then the mermaid flowchart from `describe_branch`, then a 1–2 line state-schema summary.
- `structuredContent`: the full BranchDefinition + `{status: "built", node_count, edge_count}`.

**Tool-return shape on failure**:
- `text`: one-line failure summary + bulleted list of errors with suggestions.
- `structuredContent`: `{status: "rejected", errors: [...], suggestions: [...], attempted_spec: <input>}`.

No branch row is written on failure. No partial state. No orphan rows.

## Risk & dependencies

- **Ledger write-through.** `build_branch` creates one community-visible artifact per call; `patch_branch` creates one per batch. Per #11's resolution, both actions must write through the public action ledger. One ledger entry per composite call is correct — the batch is the authored unit — not one per internal atomic op.
- **Tool-return size.** `build_branch` success returns the full described branch. For branches with >12 nodes, truncate the mermaid to a summary per `tool_return_shapes.md` phone-legibility rule (≤12 nodes); full topology stays in `structuredContent`.
- **Naming collisions with Phase 2 atomic actions.** Action verbs are distinct (`build_branch` ≠ `create_branch`, `patch_branch` ≠ any existing). No surface conflict.
- **Prompt drift.** The `control_station` prompt must be updated in the same PR: "prefer `build_branch` for new workflows; use `patch_branch` for batch edits; atomic actions only for single-item surgery." Otherwise dev lands the tools and Claude.ai keeps calling atomic actions from muscle memory.

## Acceptance criteria

1. Recipe-tracker branch from Phase 2 vignette builds in exactly one `build_branch` call.
2. Validation failure returns `suggestions`; a second call applying the suggestions succeeds.
3. `patch_branch` with a 5-op batch where op 3 is invalid: zero rows mutated, all 5 errors returned with per-op indices.
4. One ledger entry per composite call, not per internal op.
5. `control_station` prompt updated to prefer composite actions.
6. Fine-grained actions still work unchanged.
