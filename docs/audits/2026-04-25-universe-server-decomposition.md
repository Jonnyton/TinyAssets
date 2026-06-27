# universe_server.py Decomposition — Phase 1 Audit

**Date:** 2026-04-25
**Author:** navigator
**Companion task:** #29
**Builds on:** `docs/audits/2026-04-19-project-folder-spaghetti.md` §#1 (original hotspot audit)
**Cross-references:** `docs/audits/2026-04-25-engine-domain-api-separation.md` (domain/engine classification used here)

---

## 1. Goal

Produce the concrete move-map that Phase 2 implementation needs:

1. Exactly which action groups move to which submodule?
2. What shared helpers are extracted vs stay?
3. What is the recommended submodule structure and why?
4. What sequencing constraints apply?

---

## 2. Current state

`tinyassets/universe_server.py` — 13,067 LOC, 490 KB as of 2026-04-25.

**Top-level MCP tools:**

| Tool | Line start | Size (est.) | Nature |
|------|-----------|-------------|--------|
| `universe()` | 958 | ~2,700 LOC | Mixed (engine + 9 domain actions) |
| `extensions()` | 3674 | ~7,600 LOC | Pure engine |
| `goals()` | 10293 | ~845 LOC | Pure engine |
| `gates()` | 11149 | ~387 LOC | Pure engine |
| `wiki()` | 11536 | ~1,045 LOC | Pure engine |
| `get_status()` | 12595 | ~470 LOC | Pure engine |

**Preamble (helpers, imports, config):** L1–957, ~957 LOC — shared across all tools.

The 2026-04-19 spaghetti audit's §#1 proposed extracting sub-dispatch tables into `tinyassets/api/branches.py`, `tinyassets/api/runs.py`, etc. with a FastMCP `mount()` integration shell. This audit validates that shape and provides the exact file assignments.

---

## 3. Action group inventory

### 3.1 Group sizing (lines)

| Action group | Dispatch table | Line range | LOC (est.) | Nature |
|-------------|---------------|------------|------------|--------|
| **universe() — engine** | inline dispatch | 1358–3663 | ~1,585 | Engine universe management |
| **universe() — domain** | inline dispatch | 1543–3199 (interspersed) | ~720 | Fantasy domain (see companion audit) |
| **Branch build/edit** | `_BRANCH_ACTIONS` | 3674–6956 | ~3,282 | Engine |
| **Run execution** | `_RUN_ACTIONS` | 6958–8069 | ~1,111 | Engine |
| **Branch versioning** | `_BRANCH_VERSION_ACTIONS` | 8070–8152 | ~83 | Engine |
| **Project memory** | `_PROJECT_MEMORY_ACTIONS` | 7627–7696 | ~69 | Engine |
| **Cross-run queries** | `_action_query_runs` | 7697–7897 | ~201 | Engine |
| **Inspect / dry-run** | `_INSPECT_DRY_ACTIONS` | 7789–7897 | ~109 | Engine |
| **Escrow** | `_ESCROW_ACTIONS` | 7898–8005 | ~108 | Engine |
| **Messaging** | `_MESSAGING_ACTIONS` | 8153–8244 | ~92 | Engine |
| **Scheduler** | `_SCHEDULER_ACTIONS` | 8245–8418 | ~174 | Engine |
| **Outcomes** | `_OUTCOME_ACTIONS` | 8419–8556 | ~138 | Engine |
| **Attribution** | `_ATTRIBUTION_ACTIONS` | 8557–8738 | ~182 | Engine |
| **Judgment + evaluation** | `_JUDGMENT_ACTIONS` | 8739–9524 | ~786 | Engine |
| **Goals** | `_GOAL_ACTIONS` | 9525–10292 | ~768 | Engine |
| **Gates + gate events** | `_GATES_ACTIONS`, `_GATE_EVENT_ACTIONS` | 10413–11137 | ~725 | Engine |
| **Wiki** | inline dispatch | 11268–12580 | ~1,312 | Engine |
| **get_status** | top-level tool | 12595–13067 | ~472 | Engine |

---

## 4. Proposed submodule structure

### 4.1 Target layout

```
tinyassets/
  api/
    __init__.py           # mcp instance + mount points; the thin integration shell
    universe_helpers.py   # shared helpers: _universe_dir, _default_universe, _base_path,
                          # _read_json, _read_text, _find_all_pages, _path_size_bytes export
    universe_ops.py       # universe() engine actions (list, inspect, create, switch, queue, activity...)
    branches.py           # extensions() branch group (_BRANCH_ACTIONS, related helpers)
    runs.py               # extensions() run group (_RUN_ACTIONS, _action_query_runs)
    evaluation.py         # judgment, suggest_node_edit, rollback, versioning
    market.py             # goals, gates, gate_events, escrow, outcomes, attribution
    runtime_ops.py        # scheduler, messaging, project_memory, inspect_dry
    wiki.py               # wiki() tool + all _wiki_* helpers
    status.py             # get_status() tool + helpers
```

Domain actions (`query_world`, premise, canon, give_direction, submit_request) leave `universe_server.py` per the companion audit and land in `domains/fantasy_daemon/api/`.

**Integration shell (`tinyassets/api/__init__.py`):**

```python
from workflow.mcp_setup import mcp   # FastMCP instance (extracted from universe_server preamble)

from workflow.api import universe_ops, branches, runs, evaluation, market, runtime_ops, wiki, status

# Each submodule registers its tools/actions on mcp at import time
# OR via an explicit register(mcp) pattern — TBD per host Q in companion audit §8
```

### 4.2 Module assignment rationale

**`universe_ops.py`** (~1,585 LOC)
Owns `universe()` MCP tool (engine actions only) and its inline dispatch. Imports `universe_helpers.py` for path resolution. After domain extraction, `universe()` shrinks from 20 to 11 engine actions.

**`branches.py`** (~3,282 LOC — the largest submodule)
Owns `_BRANCH_ACTIONS`, `_BRANCH_WRITE_ACTIONS`, `_BRANCH_VERSION_ACTIONS`, and all `_action_*` handlers for: build_branch, list_branches, describe_branch, get_branch, patch_branch, continue_branch, set_canonical, set_fork_from, fork_tree, publish_version, get_branch_version, list_branch_versions. Also owns `_ext_branch_describe`, `_ext_branch_get`, and `_related_wiki_pages` helper (recently added Task #19).

**`runs.py`** (~1,312 LOC combined with cross-run queries)
Owns `_RUN_ACTIONS`, `_RUN_WRITE_ACTIONS`, `_action_query_runs`, and all run execution handlers: run_branch, get_run, list_runs, stream_run, cancel_run, resume_run, wait_for_run, get_run_output, estimate_run_cost. Imports from `workflow.runs` and `workflow.graph_compiler`.

**`evaluation.py`** (~895 LOC)
Owns `_JUDGMENT_ACTIONS`, `_JUDGMENT_WRITE_ACTIONS`, and handlers: judge_run, list_judgments, compare_runs, suggest_node_edit, get_node_output, list_node_versions, rollback_node. This is the multi-criteria evaluation surface from PLAN.md §"Evaluation Hooks".

**`market.py`** (~1,813 LOC)
Owns: `goals()` MCP tool + `_GOAL_ACTIONS`, `gates()` MCP tool + `_GATES_ACTIONS` + `_GATE_EVENT_ACTIONS`, `_OUTCOME_ACTIONS`, `_ATTRIBUTION_ACTIONS`, `_ESCROW_ACTIONS`. Groups the paid-market economy primitives together: goal graphs, gate ladders, real-world outcomes, remix attribution, escrow. These are logically one concern even if they have separate MCP tools.

Rationale: goals and gates are interdependent (gates evaluate outcomes against goal ladders; outcomes reference gate events). Keeping them together avoids circular imports between `goals.py` and `gates.py`. If the market surface grows large enough to warrant further splitting, goals.py + gates.py can split at that point.

**`runtime_ops.py`** (~444 LOC)
Owns: `_SCHEDULER_ACTIONS`, `_MESSAGING_ACTIONS`, `_PROJECT_MEMORY_ACTIONS`, `_INSPECT_DRY_ACTIONS`. Small-to-medium action groups with no strong interdependence but all serving "runtime coordination" — scheduling, inter-node messaging, project-scoped memory, and pre-flight dry inspection.

**`wiki.py`** (~1,312 LOC)
Owns `wiki()` MCP tool, all `_wiki_*` handlers, `_WIKI_CATEGORIES`, `_wiki_root/pages_dir/drafts_dir/...` path helpers, `_ensure_wiki_scaffold`, `_wiki_similarity_score`, `_wiki_file_bug`, `_wiki_cosign_bug` (Task #21 in-flight). This is already a cohesive subsystem — isolated path helpers, a single dispatch dict, an internal taxonomy. It extracts cleanly.

**`status.py`** (~472 LOC)
Owns `get_status()` MCP tool and its helpers. Minor dependency on `workflow.storage.inspect_storage_utilization` — already cleanly separated. Includes the activity log evidence gathering + storage utilization computation.

**`universe_helpers.py`** (~200–400 LOC extracted from preamble)
The preamble (L1–957) mixes: imports, global constants, path helper functions (`_universe_dir`, `_default_universe`, `_base_path`), JSON helpers (`_read_json`, `_read_text`), wiki path helpers (`_find_all_pages`), and the FastMCP instance setup.

Extraction target: move all `def _*` helpers out of the preamble and into `universe_helpers.py`. The FastMCP instance (`mcp = FastMCP(...)`) and its prompt registrations move to `tinyassets/api/__init__.py`. What remains in preamble is just imports + constants + the `universe_server.py` shim that delegates to the new submodules.

**`tinyassets/universe_server.py` (residual shim):**
After extraction, `universe_server.py` becomes a ~100-LOC routing shell that:
- Imports submodules (triggering their tool/action registrations)
- Exports `mcp` for the MCP entry point
- Maintains backward-compat imports for the 23 files that currently import from it

---

## 5. Shared helpers — what moves and what stays

### 5.1 Must extract to `universe_helpers.py`

Used by 3+ submodules — must be in a shared location:

| Helper | Current location | Used by |
|--------|----------------|---------|
| `_universe_dir(uid)` | L~120 | universe_ops, branches, runs, evaluation, market, wiki, status |
| `_default_universe()` | L~145 | universe_ops, branches, runs, evaluation, market |
| `_base_path()` | L~155 | universe_ops, branches, runs |
| `_read_json(path)` | L~200 | universe_ops, branches, runs, evaluation |
| `_read_text(path)` | L~215 | universe_ops, branches, wiki |
| `_find_all_pages(dir)` | L~4947 | branches (related_wiki_pages), wiki |
| `_wiki_pages_dir()`, `_wiki_drafts_dir()` | L~11308–11312 | branches, wiki |

### 5.2 Move with their primary consumer

Used by 1–2 submodules — can move with the primary consumer and be imported by the secondary:

| Helper | Move to | Secondary importer |
|--------|---------|-------------------|
| `_related_wiki_pages()` | `branches.py` | wiki.py (potentially) |
| `_wiki_root()`, `_ensure_wiki_scaffold()`, `_wiki_similarity_score()` | `wiki.py` | None |
| `_ext_branch_describe()`, `_ext_branch_get()` | `branches.py` | runs.py (get_run may reference) |
| `_apply_patch_op()` | `branches.py` | None |
| `_query_world_db()` | `domains/fantasy_daemon/api/world_state.py` | None |
| `_add_canon_entry()`, `_ingest_canon()` | `domains/fantasy_daemon/api/world_state.py` | None |
| storage utilization helpers | stay in `tinyassets/storage/__init__.py` | status.py imports from there |

---

## 6. FastMCP integration shell — two viable patterns

### Pattern A: Single `mcp` instance, action handlers imported at module level

`tinyassets/api/__init__.py` creates `mcp = FastMCP(...)`. Submodules import `mcp` and use `@mcp.tool()` decorators. This is the current pattern — extraction just splits the single file into submodules that all decorate the same `mcp` object.

**Pro:** Zero behavior change; existing tool names/docs preserved.
**Con:** All submodules must import `mcp` from `workflow.api`; creates a `workflow.api -> workflow.api.branches -> workflow.api` circular import risk. Solved by: `mcp` lives in `workflow.mcp_setup` (a leaf module with no project dependencies), imported by both `workflow.api` and each submodule.

### Pattern B: FastMCP `mount()`

Each submodule creates its own local `FastMCP` instance and the integration shell mounts them:

```python
from fastmcp import FastMCP
from workflow.api.branches import branches_mcp
from workflow.api.runs import runs_mcp

mcp = FastMCP("Workflow")
mcp.mount("branches", branches_mcp)   # tools become "branches_build_branch" etc.
```

**Pro:** True isolation; no shared-mutable-object risk.
**Con:** Tool names change (prefixed by mount path) — breaks all existing chatbot integrations. Only viable with a versioned breaking release, or with alias registrations on the root mcp.

**Recommendation:** Pattern A for Phase 1. Each submodule imports `mcp` from a new `workflow.mcp_setup` leaf module. Pattern B is the long-term target but requires a breaking-change window.

---

## 7. Import fan-in analysis

23 files currently import `from workflow.universe_server import ...` (per grep 2026-04-25). After extraction, they route to the new submodules. Two migration strategies:

**Strategy 1 (recommended): Keep `workflow.universe_server` as an aggregator shim**

`tinyassets/universe_server.py` becomes:
```python
from workflow.api.branches import *   # noqa: F401,F403
from workflow.api.runs import *
# ... etc.
```
All 23 importers continue to work unchanged. Shim is removed in a future cleanup once importers are migrated.

**Strategy 2: Migrate all 23 importers immediately**

Higher blast radius, more review surface. Better long-term but riskier as a single commit. Appropriate for Phase 2 of the decomposition, not Phase 1.

---

## 8. Sequencing constraints

| Gate | Status | Blocks |
|------|--------|--------|
| Domain action extraction (#28 / companion audit) | Pending; sequenced after rename Phases 2–4 | Domain helpers (`_query_world_db`, `_add_canon_entry`) need to leave before extraction locks the helper location |
| universe_server.py rename to workflow_server.py | Blocked on host §5 answers (design-note 2026-04-19) | If the file is renamed, the extraction should happen to the new filename; doing extraction first is fine and slightly simplifies the rename |
| Rename Phases 2–4 | Not started | Handler identifiers should be cleaned before moving handlers — avoids renaming in two places |
| NodeScope dedup (memory note `project_node_scope_dedup_post_2c.md`) | Gated on Stage 2c flag flip | Does not block universe_server extraction |
| In-flight tasks #21/#22 | In-progress (touching `universe_server.py`) | Wait for these to land before starting extraction — avoids merge conflicts on the file |

**Recommended execution order for Phase 2 (implementation):**

1. Extract `universe_helpers.py` (no behavior change, just moves helpers).
2. Extract `wiki.py` (most isolated; good test case for the pattern).
3. Extract `status.py` (isolated; few helpers).
4. Extract `runs.py` (well-defined boundary; imports from `workflow.runs` already).
5. Extract `evaluation.py` (judgment handlers; no cross-dependencies to market).
6. Extract `runtime_ops.py` (scheduler, messaging, memory, dry-run).
7. Extract `market.py` (goals + gates + attribution + outcomes + escrow; largest API surface but self-contained).
8. Extract `branches.py` (largest submodule; highest dependency density; last because it shares helpers with runs and evaluation).
9. Leave `universe_ops.py` inline in `universe_server.py` until domain extraction lands — it's the residual after domain actions leave.

Each step is a separate commit. Between steps: `pytest` + `ruff` green.

---

## 9. Estimated effort

| Phase | Work | Estimate |
|-------|------|---------|
| `universe_helpers.py` extraction | Move ~15 helper functions, fix imports in universe_server.py | 0.5 dev-day |
| `wiki.py` extraction | Move ~1,312 LOC, one new file | 0.5 dev-day |
| `status.py` extraction | Move ~472 LOC | 0.25 dev-day |
| `runs.py` extraction | Move ~1,311 LOC, update references | 0.5 dev-day |
| `evaluation.py` extraction | Move ~895 LOC | 0.5 dev-day |
| `runtime_ops.py` extraction | Move ~444 LOC | 0.25 dev-day |
| `market.py` extraction | Move ~1,813 LOC, largest API surface | 1 dev-day |
| `branches.py` extraction | Move ~3,282 LOC, highest density | 1 dev-day |
| Integration + full suite green | Shim + circular-import fixes + pytest pass | 0.5 dev-day |
| **Total** | | **~5 dev-days** |

The spaghetti audit's original estimate was "~3–4 dev-days for phase 1 (extraction without behavior change)." The 5-day revised estimate accounts for the larger-than-expected file (13K vs the 9.9K at audit time) and the `universe_helpers.py` extraction step.

---

## 10. What this does NOT do

- No behavior changes — pure refactor.
- Does not rename `universe_server.py` (that's the layer-3 design note's decision).
- Does not extract domain actions (that's the companion audit's scope, sequenced after rename Phases 2–4).
- Does not introduce FastMCP `mount()` (Pattern B) — reserved for a future breaking-change window.
- Does not collapse `daemon_server.py`'s 5+ bounded contexts (spaghetti audit §#2) — separate task, lower priority.
