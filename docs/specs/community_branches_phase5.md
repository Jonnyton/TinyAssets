---
status: shipped
shipped_date: 2026-04-12
shipped_in: c85efa1  # Community Branches Phases 2-5 + cross-universe cluster + user-sim harness
---

# Community Branches Phase 5 — Goal as First-Class Shared Primitive

**Status:** executable — dev-2 draft + planner-approved addendum below.
Directional surface above is preserved for context. Open questions
resolved in the addendum; one escalation flagged for host.
**Depends on:** Phase 2 (build), Phase 3 + 3.5 (run + async), Phase 4
(judge + lineage + rollback). All shipped 2026-04-13.
**Unblocks:** Mission 5+ social evolution — "100 users build different
research-paper workflows, all branches public, users learn from each
other" per host direction in PLAN.md Multi-User Evolutionary Design.

---

## Thesis

Through Phase 4 the system's unit of identity is the Branch. That works
for a single user iterating on one workflow. It breaks the moment you
have many users with workflows whose *purpose* is the same but whose
*structure* differs. A user asking "show me research-paper workflows"
doesn't care about branch_def_ids; they care about intent.

**Goal is the object that carries intent.** A Goal is "produce a
research paper", "plan a wedding", "build a novel". Many Branches can
bind to one Goal. Each Branch is one community's attempt to realize the
Goal with a specific topology.

This phase introduces Goals as a first-class primitive, retrofits
existing Branches with `goal_id`, and opens discovery/leaderboard
surfaces so the "reuse vs invent" decision Mission 5 exercises becomes
tractable at 100+ users.

## Non-goals (explicitly deferred)

- **No fixed Goal taxonomy.** Users propose Goals freely. Tag-based
  grouping emerges from usage, not from a committee spec.
- **No hierarchical Goals.** Flat namespace. "Sub-goals" are tag
  conventions, not nested records. Re-evaluate post-1000-users.
- **No automatic Goal matching.** A Branch binds to a Goal by explicit
  `bind` call, not a classifier. Keep the daemon out of the
  intent-inference loop per PLAN.md generator/evaluator separation.
- **No cross-host Goal federation.** Goals live in one host's
  `.author_server.db`. Federated discovery is Phase 6+.
- **No outcome tracking.** That's #56 / Phase 6+.

## Storage

New SQLite tables in `.author_server.db` (co-located with
`branch_definitions`):

```
goals (
  goal_id       TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  description   TEXT NOT NULL DEFAULT '',
  author        TEXT NOT NULL DEFAULT 'anonymous',
  tags_json     TEXT NOT NULL DEFAULT '[]',
  visibility    TEXT NOT NULL DEFAULT 'public',
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);

CREATE INDEX idx_goals_author ON goals(author);
CREATE INDEX idx_goals_visibility ON goals(visibility);
```

Schema migration on `branch_definitions`:

```
ALTER TABLE branch_definitions ADD COLUMN goal_id TEXT;
CREATE INDEX idx_branches_goal ON branch_definitions(goal_id);
```

Nullable — existing Branches remain valid with `goal_id IS NULL` until
explicitly bound. **Migration strategy:** add the column on startup via
the same `PRAGMA table_info` / `ADD COLUMN IF NOT EXISTS` pattern #50
used for `node_edit_audit`. No data backfill in Phase 5; users bind
their own existing branches or leave them unbound.

### Why not use existing fields

- **`domain_id`** is an engine-level routing key (fantasy_author vs
  workflow). It controls which graph_compiler profile runs. Goals are
  orthogonal — a single domain hosts many Goals; a single Goal may
  stretch across domains in future.
- **`tags`** on BranchDefinition is already free-form. Tags can match
  Goals by convention (`tag: goal_id`) but that's fragile. First-class
  `goal_id` gives a hard FK for leaderboards and discovery.

## MCP actions

New coarse `goals` tool (separate from `extensions`). Rationale:
`extensions` is already 22-param branch-centric; Goals are a peer
concept deserving their own tool surface. The split keeps tool
descriptions phone-legible per `tool_return_shapes.md`.

### Proposed surface (8 actions)

**Write actions (ledgered):**
- `propose(name, description, tags?)` → `goal_id`. Create a new Goal.
- `bind(branch_def_id, goal_id)` → `{ok, branch_name, goal_name}`.
  Attach an existing Branch to a Goal. Unbind by calling with
  `goal_id=""`.
- `update_goal(goal_id, name?, description?, tags?)` → same shape.
  Owner-only; other authors forking a Goal is Phase 5.5 or later.

**Read actions (no ledger):**
- `list(filter_tags?, author?, limit?)` — Catalog pattern. Markdown
  bullet list in text channel.
- `get(goal_id)` — Single-artifact pattern. Returns Goal + bound
  Branches + summary stats.
- `leaderboard(goal_id, metric="run_count"|"judgments"|"forks",
  limit?)` — Ordered list per metric.
- `common_nodes(goal_id, min_branches=2)` — Nodes appearing in ≥N
  Branches under this Goal. Mission-5 reuse-vs-invent signal.
- `search(query, limit?)` — Keyword search over Goal name +
  description + tags. Simple FTS or LIKE-based for v1.

**Cross-cutting: `list_branches` on the existing `extensions` tool
gains a `goal_id` filter.** Users saying "show me research-paper
workflows" route to `extensions action=list_branches goal_id=...`
without touching the new tool.

### Tool-return shapes (per `tool_return_shapes.md`)

- `propose` / `bind` / `update_goal` — write-ack pattern. One-line
  markdown + structured `goal` dict.
- `list` — catalog. Bullets per Goal: author, # bound branches,
  top-3 tags, description preview.
- `get` — single-composite. Markdown sections: description, bound
  Branches with mermaid thumbnail, recent runs aggregate, leaderboard
  preview. Structured content has the raw Goal + branches + stats.
- `leaderboard` — state-over-time pattern? No — "ordered catalog with
  rank hints" is closer. Numbered markdown list. Each row:
  `branch_name`, `author`, metric value, short description.
- `common_nodes` — catalog of NodeDefinition previews. Each row shows
  node_id, display_name, occurrence count across the Goal's branches,
  and first-encountered branch_def_id.
- `search` — catalog.

## Leaderboard metrics

v1 ships three metrics, all derivable from existing Phase 2-4 storage:

1. **`run_count`** — raw `runs` table count grouped by `branch_def_id`.
   Cheapest signal. Bias: popularity not quality.
2. **`judgments`** — positive/negative judgment tally from
   `run_judgments`. Phase 4 judgments are free-text — we need a coarse
   polarity classifier OR a thumbs-up/down tag convention. **Open
   question — see below.**
3. **`forks`** — count of Branches whose `parent_def_id` descends from
   a Branch. Requires walking lineage. Proxy for "this workflow is
   worth building on".

Metrics are computed on demand (no materialization). Cache later if
slow. Callers pick the metric; no aggregate score in v1.

## Integration seams (Phase 2-4 surfaces I built)

### BranchDefinition (`tinyassets/branches.py`)
- Add `goal_id: str = ""` field.
- `to_dict()` / `from_dict()` pick it up automatically via existing
  dataclass plumbing.
- `validate()` gains no new rule — an empty `goal_id` is valid (Phase
  5 legacy), a populated one doesn't constrain topology.

### Composite actions (`build_branch` / `patch_branch`)
- `build_branch` spec accepts an optional `goal_id` top-level key.
- `patch_branch` gains a `set_goal` / `unset_goal` op.
- Composite actions already ledger — no new ledger wiring needed.

### `list_branches` filter
- Existing signature accepts `domain_id`, `author`. Add `goal_id`.
- Text-channel summary adds a "Goal: ..." line per branch when filter
  is applied.

### Phase 4 lineage
- `run_lineage` already tracks parent_run_id. No changes needed for
  Goals — runs inherit Goal via their branch, not directly.
- `node_edit_audit` unchanged — edits are scoped to Branches.

### `suggest_node_edit`
- Optional future enhancement: when a user judges a node, bundle
  same-Goal neighbor Branches' same-role nodes as additional context.
  Out of scope for Phase 5.

## Mission 5 relationship

Mission 5 spawns BEFORE Phase 5 lands. The test is:

- User-sim builds research-paper workflow A in Mission 4 (persistent).
- Mission 5 prompts: "build a DIFFERENT research-paper workflow —
  reuse vs invent."

Without Goals:
- User-sim / bot has no way to ask "what workflows already exist for
  this intent?" except by reading every `list_branches` entry and
  inferring intent from name/description.
- Reuse discovery works through raw `list_branches` + name scanning.

**Mission 5 findings will SHAPE Phase 5.** Specifically:

- If the bot naturally asks "what workflows exist?" and tries to fork,
  then Goals are the pattern we need — execute Phase 5.
- If the bot doesn't ask and just rebuilds, Phase 5 needs a stronger
  discovery nudge in `control_station` prompt + tool descriptions.
- If `list_branches` shows ≥3 branches and user still rebuilds, the
  problem is Claude.ai UX not tool shape — different fix entirely.

**Don't execute Phase 5 until Mission 5 data lands.** The spec is ready
to sharpen.

## Tool description hints (update after Phase 5 lands)

Current `control_station` prompt has no Goal routing. When Phase 5 lands
the prompt routing table gains:

- "Build a workflow for [intent]" → first call `goals search` to see if
  the intent already exists. If yes, offer the user the existing
  Branches bound to that Goal. If no, propose a new Goal.
- "Show me [domain] workflows" → `extensions list_branches goal_id=...`
  after resolving the Goal via `goals search`.
- "What's the best [intent] workflow?" → `goals leaderboard`.

## Open questions for planner

1. **Judgment polarity.** Phase 4 judgments are free-text, deliberately
   no numeric rubric. Leaderboards need polarity. Options:
   - Reserve `tags=["positive", "negative"]` convention.
   - Add optional `polarity` field to judge_run (breaks Phase 4 spec §
     "no numeric rubric" — probably too far).
   - Derive polarity by LLM classifier at leaderboard-compute time
     (slow, expensive, adds AI-in-eval-loop which PLAN.md rejects).
   - Skip the `judgments` leaderboard metric entirely in v1; ship
     `run_count` + `forks` only. Revisit when judgment signal is
     richer. **My lean: this option.**

2. **Goal ownership / permissions.** Phase 5 proposes Goals are
   author-owned for `update_goal` but public for `bind`. That means
   anyone can attach any Branch to my Goal. Is that the social model
   we want? Alternative: Goal owner approves binds. That adds
   moderation overhead and a new "pending bind" state.

3. **Goal forking.** What happens when Alice proposes "research paper"
   and Bob disagrees about scope — wants "fast position papers" as a
   sibling, not a child? Phase 5 spec says flat namespace, users
   propose new Goals freely. But that means user-sim's Mission 5
   "DIFFERENT research paper" workflow probably spawns a new Goal
   rather than binding to the existing one. Is that the right answer,
   or do we want sub-Goals eventually?

4. **Deletion semantics.** What happens to bound Branches when a Goal
   is deleted? Cascade (drop goal_id from Branches) vs. soft-delete
   (mark goal as `visibility="deleted"`, keep binds for history) vs.
   refuse (can't delete a Goal that has binds). **My lean:
   soft-delete**, matches the "nothing is lost, nothing is deleted"
   convention in AGENTS.md.

5. **Search implementation.** SQLite FTS5 vs. LIKE-based vs. existing
   retrieval backends. FTS5 is best but adds a virtual table. LIKE is
   fine for <10K Goals. **My lean: LIKE for v1**, FTS5 if we hit
   scale.

6. **Visibility.** `public` / `private` / `host_only`? Or simpler
   `public` / `draft`? Host may want private Goals for testing before
   sharing. **My lean: `public` / `private`**, with private meaning
   only the author + host can see.

7. **Interaction with domain_id.** A Branch has both `domain_id` and
   `goal_id`. domain_id determines which engine profile runs it;
   goal_id says what intent it serves. Should a Goal declare an
   allowed `domain_id` list? Or is that over-constraint?
   **My lean: leave unconstrained**. Users can bind a `fantasy_author`
   Branch to a "produce a research paper" Goal if they want. They
   won't, but the freedom is cheap and the rigidity isn't.

## Acceptance criteria (when executed)

1. `goals` table + `branches.goal_id` column exist. Migration is
   additive; existing installs see no data loss.
2. All 8 proposed MCP actions registered with tool-return shapes
   matching `tool_return_shapes.md`.
3. `propose` → `bind` → `list` → `get` round-trip works for a single
   Goal with 3 Branches.
4. Leaderboard with `metric="run_count"` returns Branches ordered by
   their run count from the Phase 3 `runs` table.
5. `common_nodes(goal_id, min_branches=2)` returns nodes appearing in
   ≥2 Branches under the Goal. At minimum, compares on `node_id` (same
   id in multiple Branches). Future: semantic match on prompt similarity.
6. `list_branches goal_id=...` filter works end-to-end.
7. Ledger write-through on all write actions.
8. Mission-6 or later probe: naive user builds a 2nd workflow for the
   same intent; the bot discovers the existing Goal and Branches via
   `goals search`, surfaces them, and either rebinds or forks
   explicitly. No silent rebuilding.

## Scope cuts for v1

- **Propose-time tag normalization.** Just store what the user gives.
  Curation is a future pass.
- **Leaderboard recency weighting.** v1 is raw counts. Time-weighting
  is a future pass.
- **Goal-level judgments.** Judgments stay scoped to Runs (and optionally
  to Nodes within Runs). No Goal-wide judgment in v1.
- **Multi-author Goal editing.** Author-owned only. Co-ownership / pull
  requests later.

## Implementation estimate

Roughly the scale of Phase 2 (build_branch surfaces):

- Storage + CRUD helpers: 1 PR (~300 lines in `tinyassets/author_server.py`
  or a new `tinyassets/goals.py`). Includes the ADD COLUMN migration.
- `goals` MCP tool + 8 action handlers: 1 PR (~500 lines in
  `tinyassets/universe_server.py`, following the `_BRANCH_ACTIONS`
  dispatch pattern).
- `list_branches goal_id` filter: small (~30 lines, same PR as above).
- Prompts (`goal_discovery_guide`, `control_station` routing): 1 PR
  (~100 lines prompts + tests).
- Tests: `tests/test_goals_surface.py`, ~30 tests mirroring
  Phase 2 coverage style.

Total: ~900 lines of code + tests. About 2 sessions of work if the open
questions have sharp answers before execution starts.

---

## What this draft is NOT

- Not a planner-approved spec. Treat as a starting point for planner
  review. The 7 open questions need concrete resolutions before any
  code lands.
- Not an execution commitment. Host sequences after Mission 5 data.
- Not a complete picture of outcome tracking (#56 / Phase 6+). That
  layer consumes Goal data but is separately scoped.

Feedback from planner, host, and user-sim observations welcome on all
open-question bullets.

---

# Executable Addendum (planner-approved)

dev-2's draft is sound. Below resolves the 7 open questions, tightens
leaderboard v1 → v2 migration, and calls out what parts defer on Mission 5.

## Resolutions

**1. Judgment polarity — CONFIRMED dev-2 lean: skip `judgments` metric in v1.**
Ship `run_count` + `forks` only. Rationale: polarity classifier or new
`polarity` field both break Phase 4's "no rubric, no AI-in-eval-loop" stance.
The richer path is gate-based ranking in Phase 6 (#56). Leaderboard v2
becomes outcome-gate progression, not sentiment. Migration: v1 `metric` arg
accepts `run_count | forks`; v2 adds `gate_passed | outcome` without
breaking signatures — callers who pass unknown metrics get a
`{error, available_metrics}` response, not a crash.

**2. Goal ownership — ESCALATE TO HOST.** This is a product/social
model decision, not an architecture one. dev-2's lean (author-owned
update, public bind, no approval) favors frictionless discovery. The
alternative (owner-approved bind) favors curation but adds moderation
load and a pending-bind state. Ship dev-2's lean as default, but flag
for host that "public bind with no approval" is the Phase 5 V1 stance
and can be tightened later by adding an `approval_required` bool on the
Goal record without a schema migration. Host may want to change the
default; I don't have enough signal on the target community.

**3. Goal forking / sub-goals — CONFIRMED flat namespace.**
Alice and Bob both propose variants; the community sorts it out via
usage metrics. Hierarchical Goals encode assumptions we don't have.
Tag conventions (`parent:research_paper`) remain available if users
self-organize. Re-evaluate at 1000+ Goals.

**4. Deletion — CONFIRMED soft-delete via visibility field.**
Matches AGENTS.md "nothing is lost, nothing is deleted." Add
`"deleted"` as a third visibility value. `list` and `search` filter
it out by default; `get` still returns deleted Goals with a flag so
references remain resolvable. No cascade to branch goal_id — a
deleted Goal's bound Branches stay bound; the reference simply
resolves to a hidden Goal.

**5. Search — CONFIRMED LIKE for v1, FTS5 when scale demands.**
Threshold for migration: when `list(filter_tags)` takes >200ms on a
representative host, or when Goal count exceeds ~5K. Add the FTS5
virtual table as a Phase 5.5 task with the exact trigger, not now.

**6. Visibility — CONFIRMED `public` / `private`** (plus `deleted`
from question 4). Simpler than a three-tier model. Private means
author-plus-host visibility. Add `host_only` later if an admin
workflow surface needs it; no schema change required (it's just a
new enum value).

**7. domain_id vs goal_id — CONFIRMED unconstrained.**
Orthogonal fields. A `fantasy_author` Branch can bind to a research-
paper Goal if someone wants; they probably won't, and the freedom
costs us nothing.

## Leaderboard v1 → v2 migration path

v1 ships `run_count`, `forks`, and a reserved `outcome` stub that
returns `{status: "not_available_until_phase_6"}` rather than an
error. Claude.ai learns to ask for `outcome`; when Phase 6 gates
land, the stub starts returning real data without a surface change.
No caller migration required.

## Mission-5-informed vs. Mission-5-independent parts

**Ship independent of Mission 5 results:**
- Storage (`goals` table, `branch_definitions.goal_id` column, migration).
- All 8 MCP action handlers for `goals` tool.
- `list_branches goal_id=...` filter.
- `propose` / `bind` / `get` / `list` / `search` round-trip tests.

**Defer until Mission 5 signal lands:**
- `control_station` prompt routing changes. If Mission 5 shows the
  bot naturally asks "what exists?", the routing table's "search-
  before-build" rule is load-bearing and should be terse. If the bot
  doesn't ask, the prompt needs stronger language — we don't know
  which until we see the test. Dev-2 builds the infrastructure; the
  prompt update waits on data.
- `common_nodes` min_branches threshold tuning. Default to 2 for
  shipping; adjust after Mission 5 shows what feels useful.

## Tightening on dev-2's surface

One change to the proposed surface:

- **Rename `update_goal` to `update`** inside the `goals` tool
  dispatcher (so actions read `goals propose`, `goals update`, `goals
  bind`, not `goals update_goal`). Matches the `universe` tool's
  naming convention and keeps action names short on phone.
- Keep all other action names as proposed.

Otherwise dev-2's 8-action surface is accepted as-is.

## Acceptance criteria (supersedes dev-2's list)

1. `goals` table created; `branch_definitions.goal_id` column added
   via idempotent `ADD COLUMN` migration. Zero data loss on existing
   installs.
2. All 8 actions registered on a new `goals` MCP tool. Tool-return
   shapes match `tool_return_shapes.md` patterns (catalog, single-
   composite, ordered-rank, write-ack).
3. `leaderboard` v1 accepts `metric="run_count"` or `metric="forks"`;
   `metric="outcome"` returns the Phase 6 stub payload; any other
   value returns `{error, available_metrics}`.
4. `common_nodes(goal_id, min_branches=2)` compares on `node_id`
   equality across bound Branches. Semantic match is future work.
5. Soft-delete works: deleted Goals disappear from `list`/`search`
   but remain resolvable by `get` with a `is_deleted: true` flag.
6. Ledger write-through on `propose`, `bind`, `update`, and any state
   change to visibility. One ledger entry per call.
7. `build_branch` and `patch_branch` accept `goal_id` top-level +
   `set_goal`/`unset_goal` ops respectively, already-ledgered.
8. Independent-ship parts above pass before Mission 5 data lands;
   prompt routing + `common_nodes` threshold land in a Phase 5.5
   follow-up keyed to Mission 5 findings.

## Escalation

**One open question needs host input before ship:** Goal ownership
social model (#2 above). Default is author-owned update + public bind;
host may want owner-approved bind for curation. Calling out because
the choice reflects community culture, not architecture. Flagging to
team-lead for pass-through.
