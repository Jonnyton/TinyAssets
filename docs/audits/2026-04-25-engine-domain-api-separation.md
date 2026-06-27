# Engine/Domain API Separation — Phase 1 Audit

**Date:** 2026-04-25
**Author:** navigator
**Companion task:** #28
**Builds on:** `docs/design-notes/2026-04-17-engine-domain-api-separation.md` (ROI-first proposal, approved direction)
**Cross-references:** `docs/audits/2026-04-25-universe-server-decomposition.md` (§5 move-map aligns with this classification)

---

## 1. Goal

Produce the concrete domain/engine classification that Phase 2 execution needs:

1. Which actions in `tinyassets/universe_server.py` are domain-specific (fantasy world state)?
2. Which are engine primitives (shared across any domain)?
3. What is the extraction target (`domains/fantasy_daemon/api/`) and what does it receive?
4. What sequencing constraints block or gate this work?

---

## 2. Current state

`tinyassets/universe_server.py` (13,067 LOC as of 2026-04-25) is a single file containing:

- 5 top-level MCP tools: `universe()`, `extensions()`, `goals()`, `gates()`, `wiki()`, `get_status()`
- 19 action groups, each with a `_ACTION_*` dispatch dict and associated `_action_*` handlers
- Both engine primitives (branch execution, goal graphs, gates, wiki, evaluation) and domain-specific world state (fantasy facts, characters, premises, canon uploads, editorial direction)

PLAN.md §"Module-shape commitment" (L268) names this as pending work:

> *The pending engine/domain API separation work (`docs/design-notes/2026-04-17-engine-domain-api-separation.md`) extracts domain-specific MCP actions out of the engine shell into `domains/fantasy_daemon/api/`.*

---

## 3. Classification

### 3.1 Domain actions (fantasy-specific, move to `domains/fantasy_daemon/api/`)

These actions read/write fantasy world state (`story.db`, `knowledge.db`, `udir/canon/`, `udir/premises/`). No second domain would want them in the shared engine.

| Action | Handler | Line range | What it touches |
|--------|---------|------------|----------------|
| `submit_request` | `_action_submit_request` | 1543–1674 | Editorial request queue (fantasy-specific direction mechanism) |
| `give_direction` | `_action_give_direction` | 2612–2649 | Author direction notes stored in universe |
| `query_world` | `_action_query_world` + `_query_world_db` | 2650–2838 | `story.db` (extracted_facts, character_states, promises), `knowledge.db` (entities, facts, edges) |
| `read_premise` | `_action_read_premise` | 2838–2883 | `udir/premises/` — fantasy world premise file |
| `set_premise` | `_action_set_premise` | 2884–2903 | Writes `udir/premises/` |
| `add_canon` | `_action_add_canon` | 2904–2973 | `udir/canon/` — fantasy canon uploads |
| `add_canon_from_path` | `_action_add_canon_from_path` | 2974–3123 | `udir/canon/` — large canon file ingestion |
| `list_canon` | `_action_list_canon` | 3124–3157 | Reads `udir/canon/` |
| `read_canon` | `_action_read_canon` | 3158–3199 | Reads `udir/canon/<file>` |

**Total domain LOC in universe_server.py:** ~720 lines (~5.5% of total file).

The `universe()` MCP tool's docstring would change: domain actions (`query_world`, premise, canon, submit_request, give_direction) would be removed from its action list and their usage would route through a new domain-registered tool.

### 3.2 Engine actions (keep in `tinyassets/universe_server.py`)

These are platform substrate: any second domain (research, journalism, etc.) would use them unchanged.

**In `universe()` dispatch:**

| Action group | Handler prefix | Line range | Purpose |
|-------------|---------------|------------|---------|
| Universe management | `_action_list/inspect/read_output/create/switch_universe` | 1358–1542, 3452–3662 | Universe CRUD + output reads |
| Queue management | `_action_queue_list/cancel` | 1675–1847, 2170–2276 | Request queue (generic; submit_request is fantasy-specific but the queue is engine) |
| Daemon lifecycle | `_action_control_daemon`, `_action_daemon_overview` | 1848–2097, 3200–3281 | Pause/resume/status; cross-domain |
| Market surface | `_action_submit_node_bid`, `_action_set_tier_config`, `_action_post_to_goal_pool` | 2098–2169, 2393–2611 | Bid market, tier config, goal pool |
| Goal subscriptions | `_action_subscribe/unsubscribe/list_subscriptions` | 2277–2392 | Goal pool subscriptions |
| Activity + events | `_action_get_activity`, `_action_get_recent_events`, `_action_get_ledger` | 3282–3451 | Activity log, event stream, ledger |

**In `extensions()` dispatch (all engine, no domain contamination):**

| Action group | Dispatch table | Line range | Purpose |
|-------------|---------------|------------|---------|
| Branch build/edit | `_BRANCH_ACTIONS` | 3674–6714 | build, list, describe, get, patch, fork, continue, set_canonical, set_fork_from |
| Run execution | `_RUN_ACTIONS` | 6958–8019 | run_branch, get_run, list_runs, stream_run, cancel_run, resume_run, wait_for_run, get_run_output, estimate_cost |
| Cross-run queries | `_action_query_runs` | 7697–7788 | Cross-run state query (recently shipped) |
| Project memory | `_PROJECT_MEMORY_ACTIONS` | 7627–7694 | get/set/list project-scoped memory |
| Inspection / dry-run | `_INSPECT_DRY_ACTIONS` | 7789–7897 | dry_inspect_node, dry_inspect_patch |
| Escrow | `_ESCROW_ACTIONS` | 7898–8005 | lock/release/refund/inspect |
| Branch versioning | `_BRANCH_VERSION_ACTIONS` | 8070–8152 | publish/get/list branch versions |
| Messaging | `_MESSAGING_ACTIONS` | 8153–8244 | send/receive/ack inter-node messages |
| Scheduler | `_SCHEDULER_ACTIONS` | 8245–8418 | schedule/unschedule/list/subscribe branch schedules |
| Outcomes | `_OUTCOME_ACTIONS` | 8419–8556 | record/list/get outcomes |
| Attribution | `_ATTRIBUTION_ACTIONS` | 8557–8738 | record_remix, get_provenance |
| Judgment | `_JUDGMENT_ACTIONS` | 8739–9524 | judge_run, list_judgments, compare_runs, suggest_node_edit, rollback, versioning |

**Separate top-level MCP tools (all engine):**

- `goals()` (L10293–11137): propose/update/bind/list/get/search/leaderboard/common_nodes/set_canonical
- `gates()` (L11149–11524): define/get/claim/retract/list/leaderboard/stake_bonus/unstake/release + gate_event attest/verify/dispute/retract/get/list
- `wiki()` (L11536–12580): read/search/list/lint/write/consolidate/promote/ingest/supersede/sync_projects/file_bug
- `get_status()` (L12595–end): daemon + storage observability

**Verdict:** `extensions()`, `goals()`, `gates()`, `wiki()`, and `get_status()` are 100% engine. Only `universe()` contains domain contamination — and only 9 of its 20 actions are domain.

---

## 4. Extraction target

Per PLAN.md §"Module-shape commitment": `domains/fantasy_daemon/api/`.

`domains/fantasy_daemon/` already exists as the canonical domain directory. Today it contains `__init__.py` (compat shim re-binding to the pre-rename shim layer). After rename Phases 2–4 land, it will hold the actual domain implementation.

**Target shape:**

```
domains/fantasy_daemon/
  api/
    __init__.py          # registers domain actions on startup
    world_state.py       # query_world, read/set_premise, add/list/read_canon
    editorial.py         # submit_request, give_direction
```

Each module defines action handlers (`_action_*`) with the same signature contract as today. On startup, the domain calls a `register_domain_actions(mcp_server)` hook that mounts domain actions alongside engine actions on the shared `mcp` object, or the engine calls it via `domains/<name>/api/__init__.py:register()` discovered at startup.

**Registration pattern (FastMCP `mount()`):**

```python
# domains/fantasy_daemon/api/__init__.py
def register(mcp):
    """Called by engine startup; registers domain actions on the shared mcp."""
    mcp.mount("fantasy", domain_mcp)  # or inline tool decorators
```

The engine `universe()` tool's dispatch dict would then delegate `query_world` etc. to the domain module rather than handling them inline — or the universe tool's doc drops those actions and they surface as separate domain-registered tools. The cleaner long-term shape is separate tools; the safer migration is delegation-within-universe-tool first.

---

## 5. Domain action dependencies on engine helpers

Before extraction, confirm each domain handler's imports. Key shared helpers used inside domain handlers:

| Helper | Used by domain handlers | Engine or shared? |
|--------|------------------------|-------------------|
| `_universe_dir(uid)` | All domain handlers | Engine (keep in universe_server.py, import from domain) |
| `_default_universe()` | All domain handlers | Engine |
| `_read_json(path)` | `query_world`, `list_canon` | Engine |
| `_add_canon_entry(...)` | `add_canon`, `add_canon_from_path` | Could move with canon handlers |
| `_ingest_canon(...)` | `add_canon_from_path` | Domain-specific |
| `_query_world_db(udir, ...)` | `query_world` | Domain-specific (reads story.db, knowledge.db) |

**Implication:** Domain handlers need to `from workflow.universe_server import _universe_dir, _default_universe, _read_json` or these helpers need to be promoted to a stable `workflow.universe` module. The decomposition audit (companion doc) recommends promoting them to `tinyassets/api/universe_helpers.py`.

---

## 6. Sequencing gates

| Gate | Status | Impact |
|------|--------|--------|
| Rename Phase 1 Part 2 commit | See STATUS.md | `domains/fantasy_daemon/` must be the real domain package, not just a shim, before adding `api/` inside it |
| Rename Phases 2–4 | Not started | Identifier renames inside domain handlers should not happen twice — wait for Phase 2 to clean identifiers before moving the handlers |
| universe_server.py decomposition (#29 / companion audit) | Audit pending | The universe_server decomposition must align seam boundaries with this classification — shared helpers extracted to `tinyassets/api/universe_helpers.py` before domain handlers can safely import them |
| Universe-to-Workflow-Server rename (`docs/design-notes/2026-04-19-universe-to-tinyassets-server-rename.md`) | Blocked on host §5 answers | If the file moves to `tinyassets/workflow_server.py`, do the extraction against the new path. No-op if extracted first, but two renames on the same handlers in quick succession adds noise. |

**Recommended order:**
1. Land decomposition audit (#29) and agree on extraction boundaries → this shapes which helpers move vs stay.
2. Rename Phases 2–4 land → identifiers cleaned.
3. Extract domain actions to `domains/fantasy_daemon/api/` as a standalone commit.
4. Domain registration hook → engine calls `domains/<name>/api.register(mcp)` on startup.

---

## 7. ROI assessment

**Why this is worth doing:**

The pressure test is PLAN.md's stated criterion: *can a second domain adopt the engine without engine changes?* Today the answer is "no" for a domain that wants `universe()` because `universe().query_world` bakes in `story.db` schema. Extracting the 9 domain actions makes `universe()` a clean engine tool — a second domain installs without touching it.

**Why now is not the right time:**

- 720 LOC out of 13,067 is ~5.5% of the file. The blast radius of extraction is small.
- The rename work (Phases 2–4) is the larger adjacent effort, and it touches the same handlers. Sequencing extraction after rename avoids renaming handlers twice.
- The more urgent clarity uplift is decomposing `extensions()` into action-group submodules (#29) — that reduces the 7,500-LOC extensions block that every dev touches. Domain extraction is a clean second step.

**Estimate:** ~2 dev-days once rename Phases 2–4 land. One commit per module (`world_state.py`, `editorial.py`) + one commit for the registration hook.

---

## 8. Open questions for host

1. **Tool shape after extraction:** Should domain actions remain accessible via `universe(action="query_world")` (engine delegates to domain) or surface as a separate domain-registered MCP tool (e.g. `fantasy(action="query_world")`)? The latter is cleaner long-term; the former is safer for existing chatbot flows that use `universe action=query_world` today.

2. **Other domain candidates:** `add_canon_from_path` has a server-filesystem-access security surface (`TINYASSETS_UPLOAD_WHITELIST`). Should it stay in the engine with policy enforcement, or move to the domain with the whitelist check delegated? Current code has the whitelist check inline in `_action_add_canon_from_path`.

3. **Registration hook:** Should domain registration happen at import time (declarative, simple) or via an explicit `register(mcp)` call in the engine's startup sequence (more controlled)?
