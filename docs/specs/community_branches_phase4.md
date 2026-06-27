---
status: shipped
shipped_date: 2026-04-12
shipped_in: c85efa1  # Community Branches Phases 2-5 + cross-universe cluster + user-sim harness
---

# Community Branches Phase 4 — Eval + Iteration Hooks

**Status:** executable (addendum below converges the directional surface).
**Depends on:** Phase 3 runner (#30), #44 prompt-template execution (so outputs are meaningful to judge).
**Mission:** close the loop — user builds → user runs → user judges → user edits → user reruns.

## Thesis

Phase 4 is where TinyAssets earns its product thesis. Phase 2 lets users build a graph. Phase 3 lets them run it. Neither of those matters if the user can't look at a bad output and say "that third node is wrong, let me fix it and try again." The iteration loop is the product.

Phase 4 is not mostly new MCP actions. It is mostly **data shape + loop ergonomics**. The hard design work is: what does "judgment" look like when the judge is a non-technical user on a phone, and how does a judgment land back on the specific node that produced the weak work?

## Required loop

1. User runs a branch (Phase 3).
2. User reads output — either the final state or a specific node's output.
3. User says "node X produced weak output because Y" — in plain English, not a rubric.
4. The judgment attaches to node X at the BranchDefinition level.
5. User asks Claude.ai: "what would improve node X?" Claude reads the judgment + the node definition + the output sample, proposes an edit.
6. User accepts, Claude.ai calls existing Phase 2 actions to update the node.
7. User reruns (Phase 3). New run is labeled as a follow-up to the previous one.
8. User can ask "did that help?" — Claude.ai fetches both runs' outputs and renders a comparison.

## Minimum data shape

Three new record types in `output/.runs.db`:

- **RunJudgment**: `{run_id, node_id?, text, tags?, author, timestamp}`. Node-scoped when the user blames a specific node, run-scoped otherwise. Free text — no numeric rubric in v1. Tags are optional (e.g. `quality`, `accuracy`, `tone`).
- **RunLineage**: `{run_id, parent_run_id, branch_version, edits_since_parent: [node_id]}`. Threads runs together. `branch_version` captures which version of the BranchDefinition this run executed (BranchDefinition already has a `version` field).
- **NodeEditHistory**: existing — use BranchDefinition's version bump + a new audit table linking `{branch_def_id, version_before, version_after, nodes_changed, triggered_by_judgment_id?}`.

The write-through-ledger requirement from Phase 2 (post-#11) means judgments and edits are already publicly attributable. No new auth work.

## MCP actions (extend `extensions`)

Small surface — most of Phase 4 is data and how Claude.ai orchestrates it.

- `judge_run(run_id, text, node_id?, tags?)` — attach a judgment. The phone-friendly front door for feedback.
- `list_judgments(branch_def_id?, run_id?, node_id?)` — retrieve judgments, scoped however the client needs.
- `compare_runs(run_id_a, run_id_b, field?)` — render a side-by-side diff of final outputs or one declared field. Return is rendered markdown, not raw JSON — phone legibility is the whole point.
- `suggest_node_edit(node_id, branch_def_id, context?)` — optional convenience wrapper. Bundles the node definition, recent output samples from runs against it, and any node-scoped judgments into one payload so Claude.ai has everything it needs to propose an edit. Not strictly required — Claude.ai could orchestrate this via `get_branch` + `list_judgments` + `get_run_output` — but on a phone, one tool call beats four.

## What Phase 4 intentionally does not ship

- **No numeric scoring rubric.** Natural language judgments are better signal and lower friction. Aggregation can happen later if users actually request it.
- **No AI-judge-in-the-loop.** Users judge. Claude.ai can _help_ the user judge by reading the output, but the judgment record is attributed to the human. Adding an auto-judge is a Phase 5 concern tied to evaluation architecture in PLAN.md, not a Phase 4 MVP.
- **No live re-run from checkpoint with inline node swap.** Rerunning the whole branch is fine for v1. Live surgery is a performance optimization, not a product requirement.
- **No branching run trees.** Lineage is linear (parent_run_id). Trees can come later if the use case emerges.

## UX vignette

User has built recipe-tracker in Phase 2, run it twice in Phase 3 on two sample recipes, and the `categorize` node keeps putting desserts in "mains."

1. User to Claude.ai: "categorize got dessert vs. mains wrong on both runs."
2. Claude.ai calls `judge_run(run_id=r1, node_id="categorize", text="dessert labeled as mains", tags=["accuracy"])` and same for r2.
3. User: "fix it."
4. Claude.ai calls `suggest_node_edit(node_id="categorize", branch_def_id="...")`. Receives current prompt_template + both outputs + both judgments. Proposes a new prompt template with explicit dessert/main disambiguation.
5. User accepts. Claude.ai calls Phase 2 `update_node` (new action — small Phase 2 follow-up if it doesn't exist yet — otherwise `remove_node` + `add_node`).
6. BranchDefinition version bumps to 2.
7. User: "try again." Claude.ai calls `run_branch` for both recipes, tagging lineage.
8. User: "did it work?" Claude.ai calls `compare_runs(r1, r3)` and `compare_runs(r2, r4)`, renders plain-language diff.

## Mission-5 readiness criteria

1. A non-technical user can run the loop above on a phone without seeing any JSON.
2. Judgments persist across sessions and are queryable by node.
3. Run lineage is inspectable (`compare_runs` works, `list_runs` shows parent_run_id).
4. An edit made via Phase 2 tools flows into the next run automatically — no cache problems, no stale compiled graph.
5. When the user asks "what did I change?", a single MCP call returns the answer.

## Risks to flag now

- **Node-output granularity.** For judgments to stick to the right node, the user needs to see _per-node output_, not just final state. Phase 3's RunStepEvent stream delivers this, but Phase 4 must surface it in `get_run` in a phone-legible way — probably a dedicated `get_node_output(run_id, node_id)` helper.
- **Claude.ai has to orchestrate well.** Most of the Phase 4 loop is Claude.ai calling Phase 2 + Phase 3 actions in sequence with judgment data as context. If Claude.ai gets lost between tools, the whole loop stalls. Favor fewer, richer actions (like `suggest_node_edit`) over many atomic ones.
- **Edit history vs. branch versioning.** Current BranchDefinition has a single `version` integer. Phase 4 needs enough history to answer "show me the previous prompt for this node" — either store per-node version history or rely on full-branch snapshots at each edit. Snapshots are simpler; track as a follow-up if they become bloated.
- **Judgment signal quality.** Free-text judgments from one user have sparse coverage. That is fine for mission 5 (individual iteration), but becomes the bottleneck for cross-community eval (Phase 5 discovery/ranking). Don't try to solve this here.

---

# Executable Addendum (converged from directional surface)

## MCP action signatures

All actions extend the existing `extensions` tool dispatcher. Returns follow `docs/specs/tool_return_shapes.md`.

**`judge_run(run_id, text, node_id=None, tags=None, author=None)`**
- `text`: free-form natural language. Required. No numeric rubric.
- `node_id`: optional. When set, judgment is node-scoped — blames a specific node. When absent, judgment is run-scoped.
- `tags`: **free-form list of strings**, not controlled vocab. Rationale: a controlled vocab forces taxonomy decisions before we have enough judgments to know what the vocab should be. Track most-used tags in a follow-up for Phase 5 curation.
- `author`: defaults to `UNIVERSE_SERVER_USER` env.
- Returns (success): `text` — one-line ack echoing scope + tags; `structuredContent` — `{judgment_id, run_id, node_id, text, tags, author, timestamp}`. Matches "single scalar/status" pattern.

**`list_judgments(branch_def_id=None, run_id=None, node_id=None, limit=30)`**
- All filters optional; at least one must be set or the call rejects (avoid accidental full-table scans).
- Returns: `text` — bulleted list with `author · scope · tags · first-line-of-text`; `structuredContent` — `{judgments: [...], count}`. Matches "unordered catalog" pattern.

**`compare_runs(run_a_id, run_b_id, field=None)`**
- `field`: optional state-key restriction. Defaults to full final state + per-node outputs.
- Returns (success):
  - `text`: rendered Markdown diff. Per-node sections with `### <node_id>`, then a `diff`-fenced block showing before/after for changed fields. Identical nodes collapsed to one line ("unchanged"). If branch_version differs, header line notes that explicitly. Mermaid flowchart only when topology changed, otherwise suppressed.
  - `structuredContent`: `{run_a: {run_id, branch_version, final_state}, run_b: {...}, differences: [{node_id, change_type: "added"|"removed"|"changed"|"unchanged", a_value, b_value, field?}], topology_changed: bool}`. Matches "comparison" pattern.

**`suggest_node_edit(node_id, branch_def_id, context="")`**
- Convenience wrapper — bundles everything Claude.ai needs to propose an edit, in one call.
- Returns: `text` — a framed prompt block Claude.ai can act on directly (node's current prompt_template / source_code, 2–3 recent output samples truncated to ~500 chars each, all judgments scoped to this node, optional user `context` line); `structuredContent` — `{node, recent_runs: [{run_id, output_summary}], judgments: [...], user_context}`. Matches "single composite artifact" pattern.
- This action does NOT call an LLM. It assembles context. Claude.ai (the calling client) proposes the edit. This keeps the daemon out of the eval-feedback loop per PLAN.md "generator and evaluator separate."

**`get_node_output(run_id, node_id)`** — promoted from Phase 3 risk list.
- Returns: `text` — one-line context (run / node / ts) + the node's output fence; `structuredContent` — `{run_id, node_id, step_index, output, tool_calls}`. Required so judgments can target specific node output rather than final state.

## Storage

New SQLite tables in `output/.runs.db` (the Phase 3 runs DB):

```
run_judgments (
  judgment_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  node_id TEXT,
  text TEXT NOT NULL,
  tags_json TEXT NOT NULL DEFAULT '[]',
  author TEXT NOT NULL,
  timestamp TEXT NOT NULL
)

run_lineage (
  run_id TEXT PRIMARY KEY,
  parent_run_id TEXT,
  branch_def_id TEXT NOT NULL,
  branch_version INTEGER NOT NULL,
  edits_since_parent_json TEXT NOT NULL DEFAULT '[]',
  timestamp TEXT NOT NULL
)

node_edit_audit (
  audit_id TEXT PRIMARY KEY,
  branch_def_id TEXT NOT NULL,
  version_before INTEGER NOT NULL,
  version_after INTEGER NOT NULL,
  nodes_changed_json TEXT NOT NULL,
  triggered_by_judgment_id TEXT,
  timestamp TEXT NOT NULL
)
```

Indices on `run_judgments(run_id)`, `run_judgments(node_id)`, `run_lineage(parent_run_id)`, `run_lineage(branch_def_id, branch_version)`.

Every write action writes one entry to the public action ledger (per #11).

## Phase 2 prerequisite

**`update_node` (task #45)** must land before Phase 4 merges. Without it, "edit and rerun" forces a remove+add cycle that invalidates judgments keyed on `node_id`. Phase 4 depends on stable node identity across edits.

## Mission 5 readiness checklist (phone-testable)

1. User-sim builds the recipe-tracker branch via `build_branch` (one call).
2. User-sim runs it on two sample inputs via `run_branch` (two runs).
3. User-sim calls `get_run` for each — sees per-node output rendered on mobile without scrolling past one screen per node.
4. User-sim calls `judge_run(run_a, "categorize put dessert in mains", node_id="categorize", tags=["accuracy"])` for both runs.
5. User-sim asks Claude.ai: "fix it." Claude.ai calls `suggest_node_edit("categorize", ...)`, gets bundled context, proposes a new prompt_template, calls `update_node` (task #45) to apply.
6. User-sim calls `run_branch` again for both sample inputs. New runs' lineage points to the previous runs.
7. User-sim calls `compare_runs(run_a, run_c)` and `compare_runs(run_b, run_d)` — sees rendered diff showing the corrected categorization on both.

Mission 5 passes iff all seven steps succeed on a phone chat surface with no JSON visible to the user and no more than ~12 tool calls total (stays under per-turn limit).

## Acceptance criteria

1. All five MCP actions registered, each with tool-return shape matching `tool_return_shapes.md` patterns.
2. Three new tables created with indices; schemas match the addendum exactly.
3. Ledger write-through for every write action (`judge_run`, plus any Phase 4 action that mutates state).
4. `compare_runs` suppresses mermaid when topology is unchanged — avoids visual noise for prompt-only edits (the common case).
5. `suggest_node_edit` never calls an LLM. Daemon stays out of the feedback loop.
6. Mission 5 readiness checklist passes end-to-end on a phone via user-sim.
7. Judgments survive across sessions: close chat, reopen, `list_judgments(branch_def_id=...)` returns prior judgments.
