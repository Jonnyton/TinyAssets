---
title: Step 6 prep — tinyassets/api/runtime_ops.py extraction scope
date: 2026-04-26
author: navigator
status: pre-flight scoping (no edits yet)
companion: docs/audits/2026-04-25-universe-server-decomposition.md §4.2 (`runtime_ops.py`), §8 step 6
target_task: Decomp audit Step 6 — Extract tinyassets/api/runtime_ops.py
gates_on: #8 (helpers) ✅ landed (4f98654); #9 (wiki.py) in flight; #10 (status.py) queued; Step 4 (runs.py) queued; Step 5 (evaluation.py) queued. Step 6 sequenced AFTER Step 5 per audit §8 (concurrent universe_server.py edits risk shim-block conflicts).
---

# Step 6 (`runtime_ops.py`) pre-flight scope

Read-only scope for extracting four small-to-medium runtime-coordination action groups (project memory, dry-inspect, messaging, scheduler) from `tinyassets/universe_server.py` into a new `tinyassets/api/runtime_ops.py`. Same freshness-check protocol as #9/#10/Step 4/Step 5 prep.

---

## 1. Audit-vs-reality verdict

**Audit estimate (§3.1, §4.2):** runtime_ops.py LOC ~444. Audit lists scope: `_SCHEDULER_ACTIONS`, `_MESSAGING_ACTIONS`, `_PROJECT_MEMORY_ACTIONS`, `_INSPECT_DRY_ACTIONS`. Audit framing: "Small-to-medium action groups with no strong interdependence but all serving runtime coordination — scheduling, inter-node messaging, project-scoped memory, and pre-flight dry inspection."

**Reality (current code, 2026-04-26):**

| Block | Banner / Section | Line range | LOC (est.) |
|---|---|---|---|
| Project memory | (no banner — inline) | L7983–L8050 | ~68 |
| Dry-inspect | "dry_inspect_node / dry_inspect_patch — zero-side-effect structural preview" L8223 | L8223–L8361 | ~139 |
| Messaging | "Teammate messaging" L8842 | L8842–L8934 | ~93 |
| Scheduler | "Scheduler MCP actions" L8936 | L8936–L9126 | ~191 |

**Total moveable: ~491 LOC.** Audit said ~444 — about 11% over (audit slight under-estimate; new since-audit additions: `_load_branch_for_inspect` helper at L8228, `_apply_patch_ops` helper at L8271 — both dry-inspect-internal).

**Audit framing CONFIRMED:** All 4 blocks are runtime-coordination concerns. None is a paid-market or evaluation primitive. Each serves the daemon's operational substrate.

**Lead's question — should `_PROJECT_MEMORY_ACTIONS` and `_INSPECT_DRY_ACTIONS` move with runtime_ops?** **YES, per audit §4.2.** Both are explicitly listed in the audit's runtime_ops.py scope. The Step 4 prep doc footnote noted they "stay inline in universe_server.py" because Step 4 (runs.py) extraction skipped them — but that footnote was scoped to "what doesn't move in Step 4," not "where do they ultimately land." Their ultimate home is Step 6 (runtime_ops.py). Confirmed via:
- Audit §4.2 paragraph on `runtime_ops.py`: "Owns: `_SCHEDULER_ACTIONS`, `_MESSAGING_ACTIONS`, `_PROJECT_MEMORY_ACTIONS`, `_INSPECT_DRY_ACTIONS`."
- Audit §3.1 line-range table lists all 4 dispatch tables in the runtime_ops cluster.
- No competing scope claim from any other future submodule.

---

## 2. Symbol enumeration (current line ranges)

### 2.1 Project memory block (contiguous L7983–L8050)

| Symbol | Line | LOC | Notes |
|---|---|---|---|
| `_action_project_memory_get` | 7983 | ~13 | Imports `workflow.memory.project.project_memory_get` |
| `_action_project_memory_set` | 7996 | ~31 | Imports `workflow.memory.project.project_memory_set`; uses `_current_actor` (preamble) |
| `_action_project_memory_list` | 8027 | ~17 | Imports `workflow.memory.project.project_memory_list` |
| `_PROJECT_MEMORY_ACTIONS` | 8044 | 5 | Dict literal — 3 handlers |
| `_PROJECT_MEMORY_WRITE_ACTIONS` | 8050 | 1 | Frozenset — 1 entry |

### 2.2 Dry-inspect block (contiguous L8223–L8361)

| Symbol | Line | LOC | Notes |
|---|---|---|---|
| Section banner | 8223 | 4 | "dry_inspect_node / dry_inspect_patch — zero-side-effect structural preview" |
| `_load_branch_for_inspect` | 8228 | ~28 | Helper; both dry-inspect handlers consume it. Single-block local. |
| `_action_dry_inspect_node` | 8256 | ~14 | Imports `workflow.graph_compiler.inspect_node_dry` |
| `_apply_patch_ops` | 8271 | ~64 | Helper for `_action_dry_inspect_patch`. Single consumer at L8349. **Audit §5.2 says this should move to `branches.py`** — see §3.3 below. |
| `_action_dry_inspect_patch` | 8334 | ~22 | Imports `workflow.graph_compiler.inspect_node_dry`; calls `_load_branch_for_inspect` + `_apply_patch_ops` |
| `_INSPECT_DRY_ACTIONS` | 8357 | 4 | Dict literal — 2 handlers |

### 2.3 Messaging block (contiguous L8842–L8934)

| Symbol | Line | LOC | Notes |
|---|---|---|---|
| Section banner | 8842 | 4 | "Teammate messaging" |
| `_action_messaging_send` | 8847 | ~32 | Imports `workflow.runs.post_teammate_message` |
| `_action_messaging_receive` | 8879 | ~29 | |
| `_action_messaging_ack` | 8908 | ~21 | |
| `_MESSAGING_ACTIONS` | 8929 | 5 | Dict literal — 3 handlers |

### 2.4 Scheduler block (contiguous L8936–L9126)

| Symbol | Line | LOC | Notes |
|---|---|---|---|
| Section banner | 8936 | 1 | "── Scheduler MCP actions ──" |
| `_action_schedule_branch` | 8939 | ~47 | |
| `_action_unschedule_branch` | 8986 | ~17 | |
| `_action_list_schedules` | 9003 | ~12 | |
| `_action_subscribe_branch` | 9015 | ~35 | |
| `_action_unsubscribe_branch` | 9050 | ~17 | |
| `_action_pause_schedule` | 9067 | ~17 | |
| `_action_unpause_schedule` | 9084 | ~17 | |
| `_action_list_scheduler_subscriptions` | 9101 | ~15 | |
| `_SCHEDULER_ACTIONS` | 9116 | 11 | Dict literal — 8 handlers |

---

## 3. Cross-references — bidirectional dependency check

### 3.1 Does runtime_ops.py depend on #9/#10/Step 4/Step 5 (wiki/status/runs/evaluation) symbols?

**No.** Verified by grep:
- No `_wiki_*` symbol used by any runtime_ops handler.
- No `get_status` or `_policy_hash` reference.
- No `_RUN_ACTIONS` / `_action_run_*` reference (runtime_ops operates parallel to runs).
- No `_JUDGMENT_ACTIONS` / `_BRANCH_VERSION_ACTIONS` reference.

### 3.2 Does runtime_ops.py depend on shared #8 helpers?

**Yes:** Most handlers use `_base_path` (helpers.py) and `_current_actor` (preamble L295). After #8 lands (already done — 4f98654), runtime_ops.py imports `_base_path` from `tinyassets/api/helpers.py`.

`_current_actor` is **NOT in helpers.py** — it lives in universe_server.py preamble. Same back-edge concern as Step 5's `_append_global_ledger`. **Verification at extraction time:** check `tinyassets/api/helpers.py` for `_current_actor`. If absent, runtime_ops.py needs `from workflow.universe_server import _current_actor` (back-edge tolerated as long as re-export shim is at module END).

### 3.3 `_apply_patch_ops` placement — audit conflict

**Audit §5.2 says `_apply_patch_ops` → `branches.py`** (audit step 8 future scope; "Move with primary consumer: `_apply_patch_ops` → branches.py").

**Reality (2026-04-26):** `_apply_patch_ops` has **only ONE consumer** in current code — `_action_dry_inspect_patch` at L8349. It does NOT have a `branches.py` consumer (`extensions()` body's `patch_branch` action handler uses different machinery via `workflow.branches.patch_branch_definition`).

**Two options for Step 6:**
- **Option A (literal audit):** Leave `_apply_patch_ops` inline in universe_server.py for now; dry_inspect_patch in runtime_ops.py imports it via `from workflow.universe_server import _apply_patch_ops`. When Step 8 (branches.py) extracts, `_apply_patch_ops` moves to branches.py and runtime_ops.py's import path updates.
- **Option B (move with consumer):** `_apply_patch_ops` moves with `_action_dry_inspect_patch` to runtime_ops.py. Audit's §5.2 prescription is stale — there's no `branches.py` consumer to "move with." When Step 8 extracts, branches.py imports `_apply_patch_ops` from runtime_ops.py if needed (or doesn't — current code shows no need).

**Recommendation:** **Option B.** Single consumer is in dry_inspect, no branches.py consumer exists. The audit's §5.2 prescription was written before the dry-inspect block grew its current shape. Moving `_apply_patch_ops` with its only consumer eliminates a back-edge import. This is a freshness-check finding per memory `feedback_audit_freshness_check.md` rule #6.

**Decision needed for lead:** Option A or Option B. Recommend B.

### 3.4 `_load_branch_for_inspect` placement

`_load_branch_for_inspect` (L8228) has 2 consumers — both `_action_dry_inspect_node` (L8263) and `_action_dry_inspect_patch` (L8345). Both move to runtime_ops.py. Helper moves with them. **Trivial; no decision needed.**

### 3.5 Does runtime_ops.py share dispatch surface with `extensions()`?

**Yes — 4 dispatch reads in `extensions()` body:**
- L4026: `pm_handler = _PROJECT_MEMORY_ACTIONS.get(action)` — project memory dispatch
- L4056: `messaging_handler = _MESSAGING_ACTIONS.get(action)` — messaging dispatch
- L4108: `inspect_dry_handler = _INSPECT_DRY_ACTIONS.get(action)` — dry-inspect dispatch
- L4119: `scheduler_handler = _SCHEDULER_ACTIONS.get(action)` — scheduler dispatch

After Step 6 lands, `extensions()` body needs **one new import line** at top of universe_server.py:
```python
from workflow.api.runtime_ops import (
    _PROJECT_MEMORY_ACTIONS, _PROJECT_MEMORY_WRITE_ACTIONS,
    _MESSAGING_ACTIONS,
    _INSPECT_DRY_ACTIONS,
    _SCHEDULER_ACTIONS,
)
```

Also note: `extensions()` at L4029-4030 references `_PROJECT_MEMORY_WRITE_ACTIONS` for ledger-write tracking (per the dispatch loop snippet — `if action in _PROJECT_MEMORY_WRITE_ACTIONS: _append_global_ledger(...)`). This is the only WRITE_ACTIONS frozenset in scope; the other 3 dispatch tables don't have separate write-action sets in current code. **Verify at extraction time** by `grep -n "_PROJECT_MEMORY_WRITE_ACTIONS\|_MESSAGING_WRITE_ACTIONS\|_INSPECT_DRY_WRITE_ACTIONS\|_SCHEDULER_WRITE_ACTIONS" tinyassets/universe_server.py` — only `_PROJECT_MEMORY_WRITE_ACTIONS` should appear.

**Structurally identical** to Step 4 (`_RUN_ACTIONS`) and Step 5 (`_JUDGMENT_ACTIONS` + `_BRANCH_VERSION_ACTIONS`) patterns. **Trivial; not a refactor of `extensions()` body.**

---

## 4. FastMCP `mcp` instance — inherits #9 decision

Same Pattern A question as previous steps. **Inherited.**

runtime_ops.py does NOT register any `@mcp.tool()` decorator directly (just like runs.py + evaluation.py). Public `extensions()` MCP tool is the surface; runtime_ops.py owns dispatch handlers exposed via the 4 ACTIONS dicts. `mcp` import is technically not required for runtime_ops.py.

**Recommendation:** omit `mcp` import in runtime_ops.py, consistent with Step 4/5 recommendations.

---

## 5. Test files importing runtime_ops symbols (and how)

| Test file | Symbol(s) imported | Count |
|---|---|---|
| `tests/test_dry_inspect_node.py` | `_action_dry_inspect_node` (×7), `_action_dry_inspect_patch` (×5), `extensions` (×3) | 12 direct + 3 via tool |
| `tests/test_project_memory.py` | `_action_project_memory_get` (×4), `_action_project_memory_set` (×6), `_action_project_memory_list` (×4), `extensions` (×2) | 14 direct + 2 via tool |
| `tests/test_scheduler.py` | (none direct from universe_server — uses storage layer directly) | 0 |
| `tests/test_scheduler_edge_cases.py` | (none direct) | 0 |
| `tests/test_scheduler_mcp.py:14` | `extensions` | 1 (via tool surface) |
| `tests/test_teammate_message.py:365,380,395,412,420` | `extensions` | 5 (via tool surface) |
| `tests/test_mcp_dispatch_docstring_parity.py` | (uses `_SCHEDULER_ACTIONS` etc. via introspection — back-compat shim covers) | (introspection) |

**Strategy:** Audit §7 Strategy 1 (back-compat re-export shim) preserves all imports. After Step 6 lands, `tinyassets/universe_server.py` adds:
```python
# Phase-1 runtime_ops extraction — back-compat re-exports.
from workflow.api.runtime_ops import (  # noqa: F401
    _PROJECT_MEMORY_ACTIONS, _PROJECT_MEMORY_WRITE_ACTIONS,
    _MESSAGING_ACTIONS,
    _INSPECT_DRY_ACTIONS,
    _SCHEDULER_ACTIONS,
    _action_project_memory_get, _action_project_memory_set, _action_project_memory_list,
    _action_dry_inspect_node, _action_dry_inspect_patch,
    _action_messaging_send, _action_messaging_receive, _action_messaging_ack,
    _action_schedule_branch, _action_unschedule_branch, _action_list_schedules,
    _action_subscribe_branch, _action_unsubscribe_branch,
    _action_pause_schedule, _action_unpause_schedule,
    _action_list_scheduler_subscriptions,
    _load_branch_for_inspect,
)
# If Option B (recommended), also re-export `_apply_patch_ops`:
from workflow.api.runtime_ops import _apply_patch_ops  # noqa: F401
```

**~26 direct test imports across 2 files** (`test_dry_inspect_node`, `test_project_memory`) continue to work via shim. **No test edits required for Step 6.**

Cleaner than Step 4 (32 imports across 4 files) but messier than Step 5 (0 direct imports). Middle of the difficulty spectrum.

---

## 6. What partially-moved (the helpers-already-extracted lesson)

Searched for evidence that any runtime_ops-scope symbols already shipped to a submodule (e.g. `workflow.api.runtime_ops`, `workflow.scheduler`, `workflow.messaging`). **None found.**

Adjacent cross-module dependencies:
- `workflow.memory.project.*` — storage layer for project memory. Stays put. Imports unchanged.
- `workflow.runs.post_teammate_message` — storage layer for messaging. Stays put.
- `workflow.graph_compiler.inspect_node_dry` — engine-side dry-inspect implementation. Stays put.
- `workflow.scheduler.*` (presumed; verify at extraction time) — storage layer for scheduler. Stays put.

The only adjacent partial moves are the helpers in #8 (already landed) — `_base_path` is now in `helpers.py`.

---

## 7. Total LOC moved estimate

| Block | LOC |
|---|---|
| Project memory (L7983–8050) | ~68 |
| Dry-inspect (L8223–8361) | ~139 (incl. `_load_branch_for_inspect` + `_apply_patch_ops` per Option B) |
| Messaging (L8842–8934) | ~93 |
| Scheduler (L8936–9126) | ~191 |
| **Total moved out of universe_server.py** | **~491** |
| Back-compat re-export block added to universe_server.py | ~22 |
| **Net reduction in universe_server.py** | **~469** |
| New `tinyassets/api/runtime_ops.py` size | **~525** (with imports + module docstring) |

**Audit said ~444.** Reality ~491 (~11% over). Drift driven by Option-B inclusion of `_apply_patch_ops` (~64 LOC) + `_load_branch_for_inspect` (~28 LOC) — neither was in audit's audit-time enumeration. If Option A is chosen instead, total drops to ~427 LOC (closer to audit estimate but with a back-edge import).

---

## 8. Risks the audit didn't anticipate

1. **Four non-contiguous source ranges.** Even more interleaved than Step 4/5. Extraction must surgically pick:
   - L7983–L8050 (project memory) — sandwiched between runs (Step 4) and `_action_query_runs`
   - L8223–L8361 (dry-inspect) — sandwiched between query_runs and escrow (market.py future)
   - L8842–L8934 (messaging) — sandwiched between branch_versioning (Step 5) and scheduler
   - L8936–L9126 (scheduler) — sandwiched between messaging and outcomes (market.py)

   **Highest accidental-pull risk of any step so far.** Recommend dev does line-by-line `git diff` review against the §2 enumeration before commit, especially around the L8842-9126 block where messaging and scheduler are physically adjacent but scheduler immediately precedes outcomes (which goes to market.py in Step 7).

2. **`_current_actor` back-edge import** (§3.2). Same pattern as Step 5's `_append_global_ledger`. Tolerated; back-edge is fine as long as re-export shim at module END.

3. **`_apply_patch_ops` placement decision** (§3.3). Recommend Option B (move with consumer). Lead must decide before extraction.

4. **`_PROJECT_MEMORY_WRITE_ACTIONS` is the ONLY write-actions frozenset in runtime_ops scope.** Other 3 dispatch tables don't have separate write-action sets. Verify at extraction time and don't accidentally invent write-action sets for the others.

5. **`extensions()` body has 4 dispatch reads** that need a single new import line. Trivial.

6. **No dispatch glue to extract.** Unlike Step 4 (`_dispatch_run_action`) and Step 5 (`_dispatch_judgment_action`), Step 6 has NO dispatch helper functions — `extensions()` body inlines the dispatch loop directly. Each `*_handler = _XXX_ACTIONS.get(action); if *_handler is not None: return *_handler(*_kwargs)` block is inline. Confirmed via grep — no `_dispatch_messaging`, `_dispatch_scheduler`, `_dispatch_project_memory`, `_dispatch_inspect_dry` defined anywhere. Slightly simpler shim than Step 4/5.

7. **Pre-commit canonical-vs-plugin parity check** — same as previous steps. Run `python packaging/claude-plugin/build_plugin.py`.

8. **Sequencing relative to Step 5** — both Step 5 and Step 6 edit the universe_server.py back-compat shim block. **Concurrent landing risks merge conflicts on the shim block.** Recommend strict serialization Step 5 → Step 6. Otherwise (per the lead's note), they don't directly interact — Step 6 doesn't touch Phase 4 evaluation territory.

9. **`tests/test_scheduler.py` and `test_scheduler_edge_cases.py` use storage layer directly** — they don't import from `workflow.universe_server`. So they survive Step 6 with zero changes. Sanity check: run them after extraction to confirm.

10. **`_apply_patch_ops` shape** — it depends on `workflow.branches.BranchDefinition` + `workflow.branches.NodeDefinition`. These are storage-layer imports. Stays put; extraction just moves the consumer + helper.

---

## 9. Concrete Step 6 implementation plan

Estimated wall time: 60-90 min (4 non-contiguous source ranges + 26 direct test imports to preserve via shim, but no dispatch glue to migrate, no test edits needed).

1. **Confirm #8, #9, #10, Step 4, Step 5 have all landed.**
2. **Confirm `_current_actor` location** — if in helpers.py, import from there; if still in universe_server.py preamble, accept back-edge import.
3. **Lead decision: Option A or Option B for `_apply_patch_ops`** (§3.3). Recommend Option B (move with consumer to runtime_ops.py).
4. **Confirm `mcp` instance pattern from #9** — inherited; not strictly needed for runtime_ops.py.
5. **Create `tinyassets/api/runtime_ops.py`:**
   - Module docstring referencing audit + extraction date + the four non-contiguous source ranges.
   - Imports: `from workflow.api.helpers import _base_path` + storage layer imports (`workflow.memory.project`, `workflow.runs`, `workflow.graph_compiler`, `workflow.branches`, `workflow.scheduler` per verification) + back-edge `_current_actor` per §3.2 + std-lib + typing.
   - Move symbols **in this order** (logical grouping by sub-domain — project memory, dry-inspect, messaging, scheduler):
     1. **Project memory section** — banner + 3 handlers + `_PROJECT_MEMORY_ACTIONS` + `_PROJECT_MEMORY_WRITE_ACTIONS`
     2. **Dry-inspect section** — banner + `_load_branch_for_inspect` + `_action_dry_inspect_node` + (Option B) `_apply_patch_ops` + `_action_dry_inspect_patch` + `_INSPECT_DRY_ACTIONS`
     3. **Messaging section** — banner + 3 handlers + `_MESSAGING_ACTIONS`
     4. **Scheduler section** — banner + 8 handlers + `_SCHEDULER_ACTIONS`
6. **Update `tinyassets/universe_server.py`:**
   - Delete the 4 source ranges in reverse order to avoid line-shift confusion:
     - L8936–L9126 (scheduler block)
     - L8842–L8934 (messaging block)
     - L8223–L8361 (dry-inspect block)
     - L7983–L8050 (project memory block)
   - Add to back-compat shim block at end of file (per §5).
   - The `extensions()` body's 4 dispatch reads continue to work via the re-export.
7. **No test edits required** — re-export shim preserves the existing 26 direct imports.
8. **Run `python packaging/claude-plugin/build_plugin.py`** to sync plugin runtime mirror.
9. **Verification:**
   - `pytest tests/test_dry_inspect_node.py tests/test_project_memory.py tests/test_scheduler_mcp.py tests/test_teammate_message.py -q` → green (covers direct imports + extensions surface).
   - `pytest tests/test_scheduler.py tests/test_scheduler_edge_cases.py -q` → green (storage-layer-only tests, sanity check).
   - `pytest tests/test_mcp_dispatch_docstring_parity.py -q` → green (introspection-based parity test).
   - `pytest -q` → full suite green.
   - `ruff check tinyassets/api/runtime_ops.py tinyassets/universe_server.py` → clean.
   - **Visual check:** `git diff tinyassets/universe_server.py | grep -c "^-def _action_"` should equal 16 (3 project memory + 2 dry-inspect + 3 messaging + 8 scheduler). Anything else means an accidental pull.

**Files in eventual Step 6 SHIP handoff:**
- `tinyassets/api/runtime_ops.py` (NEW, ~525 LOC)
- `tinyassets/universe_server.py` (~469 LOC removed + ~22 re-export added)
- `packaging/claude-plugin/.../tinyassets/api/runtime_ops.py` (NEW mirror)
- `packaging/claude-plugin/.../tinyassets/universe_server.py` (mirror)

4 files, +547 / -469 LOC net.

---

## 10. Decision asks for the lead

1. **`_apply_patch_ops` placement (Option A vs Option B)** — recommend Option B (move with `_action_dry_inspect_patch`, only consumer; audit's §5.2 prescription is stale — no `branches.py` consumer exists in current code).
2. **Sequencing: Step 5 → Step 6 strict serialization** — recommend yes (avoid back-compat shim block merge conflicts in universe_server.py).
3. **`mcp` instance import** in runtime_ops.py — recommend omit, consistent with Step 4/5.
4. **`_current_actor` back-edge import** — accept for Step 6, same as Step 5 accepted `_append_global_ledger` back-edge. Promote `_current_actor` to helpers.py during eventual full universe_server shim cleanup post-Step-8.

---

## 11. Cross-prep summary (Steps 1–6 combined)

After all 6 land:

| Step | New file | Net LOC removed from universe_server.py | Cumulative universe_server.py size |
|---|---|---|---|
| baseline (2026-04-26) | — | — | 14,012 |
| #8 ✅ landed (4f98654) | extends `helpers.py` | ~16 | ~13,996 |
| #9 (in flight) | `wiki.py` | ~1,360 | ~12,636 |
| #10 (queued) | `status.py` | ~422 | ~12,214 |
| Step 4 (queued) | `runs.py` | ~1,385 | ~10,829 |
| Step 5 (queued) | `evaluation.py` | ~836 | ~9,993 |
| Step 6 (this prep) | `runtime_ops.py` | ~469 | **~9,524** |
| **Total** | 4 new + 1 extended | ~4,488 | **~9,524** |

universe_server.py shrinks by **~32%** after the 6 steps (from baseline 14,012). Crosses the symbolic 10,000-LOC threshold during Step 5; lands at ~9,524 after Step 6. Larger reductions still ahead in steps 7–8 (`market.py` ~1,813, `branches.py` ~3,282 — together another ~5,095 LOC).

After Step 8 (final): universe_server.py projects to **~4,429 LOC** (~68% reduction from baseline). The remaining ~4,400 LOC is `universe()` MCP tool + `extensions()` MCP tool dispatch shell + preamble (imports, constants, mcp setup) + back-compat re-export block.

All 6 steps are pure refactor — no behavior change, no test edits required (back-compat shim preserves existing test imports across the suite).
