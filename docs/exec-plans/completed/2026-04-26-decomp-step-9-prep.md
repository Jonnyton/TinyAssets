---
title: Step 9 prep — tinyassets/api/universe.py extraction scope
date: 2026-04-26
author: navigator
status: pre-flight scoping (no edits yet)
companion: docs/audits/2026-04-25-universe-server-decomposition.md (audit's "100-LOC routing shell" target — Steps 9+10 are post-original-8-step extension); docs/exec-plans/completed/2026-04-26-decomp-step-8-prep.md §10.2
target_task: Decomp post-Step-8 — Extract tinyassets/api/universe.py (the `universe()` MCP tool body + 28 `_action_*` handlers + WRITE_ACTIONS + ledger dispatcher + daemon-liveness telemetry)
gates_on: Step 8 (`branches.py`, ~2,673 LOC) MUST land first. Step 8 + Step 9 both edit `tinyassets/universe_server.py` re-export shim block. Step 9 is otherwise independent of Step 8 (no symbol overlap — branches.py owns `_BRANCH_ACTIONS` table; universe.py owns the `universe()` tool dispatch table).
---

# Step 9 (`universe.py`) pre-flight scope

Read-only scope for extracting the `universe()` MCP tool surface from `tinyassets/universe_server.py` into a new `tinyassets/api/universe.py`. **Second-largest extraction by LOC** (~2,580 moveable LOC) and the most semantically self-contained: every symbol in scope is wired through one MCP tool dispatch table. Same freshness-check protocol as Steps 1-8 prep.

This step is NOT in the original 8-step audit plan. Per Step 8 prep §10.2, the audit's "~100-LOC routing shell" target requires extracting `universe()` + `_action_*` handlers (this step) AND the preamble engine helpers (Step 10) on top of the planned 8 extractions. Lead-and-host approval required to proceed.

---

## 1. Audit-vs-reality verdict

**Audit estimate (§9 step 8 + §10 future):** Audit framed the "~100-LOC routing shell" target after Step 8. It did NOT explicitly enumerate `universe.py` as a separate step — Step 8 prep §10.2 surfaced this as the gap. Audit's universe-tool symbol list is implicit in the §9 ordering (universe()/extensions() identified as "the only two `@mcp.tool` calls left after Pattern A2 wraps `goals`/`gates`/`wiki`/`get_status`").

**Reality (current code, 2026-04-26 post-Step-7, pre-Step-8):**

| Block | Banner / Section | Line range | LOC (est.) |
|---|---|---|---|
| `WRITE_ACTIONS` extractor closures | (no banner — preamble) | L508–L713 | ~206 |
| `_ledger_target_dir`, `_scope_universe_response`, `_dispatch_with_ledger` | (no banner) | L857–L959 | ~103 |
| `@mcp.tool() universe()` definition | "MCP PROMPTS" L961 follows | L1060–L1238 | ~179 |
| Daemon telemetry helpers | "Daemon telemetry — liveness, staleness, human-readable phase" L1240 | L1240–L1490 | ~251 |
| 28 `_action_*` handlers (universe-tool scope) | "Universe action implementations" L1492 | L1497–L3832 | ~2,336 |
| **Total moveable** | | | **~3,075** |

**Total moveable: ~3,075 LOC.** Materially larger than Step 8's ~2,673 — universe.py is now the **largest single extraction** of the decomposition.

**Important narrowing:** Two universe-tool actions in `WRITE_ACTIONS` are extractor-only (the handler lives in another module per Steps 4-7):
- None — all 28 actions in the `universe()` dispatch table (L1171-L1199) have their `_action_*` handler defined in this same file (L1497-L3832 range).

**Cross-checked exclusions (handlers re-imported from Steps 4-7, NOT in scope):**
- `_action_run_branch`, `_action_run_branch_version`, `_action_query_runs` — already in `workflow.api.runs` (Step 4). Re-exported via L286 shim. NOT in `universe()` dispatch.
- `_action_attest_gate_event`, `_action_dispute_gate_event`, `_action_get_gate_event`, `_action_list_gate_events`, `_action_retract_gate_event`, `_action_verify_gate_event` — already in `workflow.api.market` (Step 7). Re-exported via L231/L239-L271 shim. NOT in `universe()` dispatch.
- `_action_dry_inspect_node`, `_action_dry_inspect_patch`, `_action_messaging_*`, `_action_project_memory_*`, `_action_schedule_*`, `_action_subscribe_branch`, `_action_unsubscribe_branch`, `_action_pause_schedule`, `_action_unpause_schedule` — already in `workflow.api.runtime_ops` (Step 6). NOT in `universe()` dispatch.
- `_action_continue_branch`, `_action_fork_tree` — moving to `branches.py` in Step 8 (L6733, L6933 in current code; not yet extracted but inside Step 8's L4435-L7110 range). NOT in `universe()` dispatch.

The `universe()` dispatch table cleanly contains **only the 28 universe-scope actions** (universe-CRUD, daemon control, canon, queue, subscriptions, goal-pool, daemon overview, tier config). Clean extraction boundary.

---

## 2. Symbol enumeration (current line ranges)

### 2.1 WRITE_ACTIONS extractors + table (L508–L713)

| Symbol | Line | LOC | Notes |
|---|---|---|---|
| Module comment block "WRITE_ACTIONS is the single source of truth..." | 508 | ~15 | Preserve verbatim |
| `_extract_submit_request` | 523 | ~12 | |
| `_extract_give_direction` | 536 | ~12 | |
| `_extract_set_premise` | 549 | ~10 | |
| `_extract_add_canon` | 560 | ~14 | |
| `_extract_add_canon_from_path` | 576 | ~17 | |
| `_extract_control_daemon` | 595 | ~9 | |
| `_extract_switch_universe` | 605 | ~6 | |
| `_extract_create_universe` | 612 | ~8 | |
| `_extract_queue_cancel` | 624 | ~9 | |
| `_extract_subscribe_goal` | 634 | ~6 | |
| `_extract_unsubscribe_goal` | 641 | ~6 | |
| `_extract_post_to_goal_pool` | 648 | ~14 | |
| `_extract_submit_node_bid` | 664 | ~17 | |
| `_extract_set_tier_config` | 682 | ~14 | |
| `WRITE_ACTIONS` dict literal | 698 | ~16 | 14 entries: action → (extractor, control_daemon_gate). |

Total: ~206 LOC.

### 2.2 Ledger dispatcher trio (L857–L959)

| Symbol | Line | LOC | Notes |
|---|---|---|---|
| `_ledger_target_dir` | 857 | ~10 | Resolves universe dir for ledger entry. Calls `_default_universe`, `_base_path`, `_universe_dir` (preamble engine helpers). |
| `_scope_universe_response` | 869 | ~36 | #15 contract: prepends `Universe: <id>` text lead-in. Pure JSON shaping. |
| `_dispatch_with_ledger` | 907 | ~52 | Funnels every WRITE action through ledger. Calls `_append_ledger` (preamble — defined L459), `WRITE_ACTIONS.get`, `_scope_universe_response`. |

Total: ~103 LOC. **All three are universe-tool-internal — not used by `extensions()` or any other MCP tool.** Verified via grep: `_dispatch_with_ledger`, `_scope_universe_response`, `_ledger_target_dir` are referenced only by `universe()` (L1237) and themselves.

### 2.3 `@mcp.tool() universe()` definition (L1060–L1238)

| Symbol | Line | LOC | Notes |
|---|---|---|---|
| `@mcp.tool(...)` decorator | 1060 | ~15 | title="Universe Operations", tags + ToolAnnotations. |
| `def universe(...)` signature | 1075 | ~25 | 23 keyword args. |
| Docstring | 1101 | ~70 | The chatbot-facing reference for every action verb. |
| `dispatch = {...}` table | 1171 | ~28 | 28 action → handler mappings. |
| `handler = dispatch.get(...)` + error path | 1201 | ~6 | |
| `kwargs = {...}` build + return | 1208 | ~30 | Funnels all 23 sig args + dispatches via `_dispatch_with_ledger`. |

Total: ~179 LOC. **First extraction with `@mcp.tool()` decorator on a function whose body lives entirely inside the moved range.** Pattern A2 decision (see §4).

### 2.4 Daemon telemetry helpers (L1240–L1490)

| Symbol | Line | LOC | Notes |
|---|---|---|---|
| Banner + module comment | 1240 | ~10 | |
| `_STALE_FRESH_SECONDS`, `_STALE_IDLE_SECONDS` | 1254 | 2 | Module-level constants. |
| `_last_activity_at` | 1258 | ~31 | |
| `_staleness_bucket` | 1291 | ~21 | |
| `_phase_human` | 1314 | ~30 | |
| `_compute_accept_rate_from_db` | 1345 | ~48 | Reads `<udir>/story.db` directly (sqlite3). |
| `_compute_word_count_from_files` | 1395 | ~50 | Walks `<udir>/output/**/*.md`. |
| `_daemon_liveness` | 1447 | ~44 | The shared liveness block consumed by `_action_list_universes`, `_action_inspect_universe`, `_action_daemon_overview`. **Test-monkeypatched** (L23 in `test_inspect_cross_surface_hint.py`). |

Total: ~251 LOC. **All used only by universe-tool actions** (verified: no callers outside L1497-L3832 range).

### 2.5 Universe action handlers (L1497–L3832)

The 28 `_action_*` handlers in `universe()` dispatch order:

| Handler | Line | LOC | Notes |
|---|---|---|---|
| `_action_list_universes` | 1497 | ~48 | |
| `_action_inspect_universe` | 1545 | ~137 | Largest READ handler. Calls `_daemon_liveness`. |
| `_action_read_output` | 1682 | ~31 | |
| `_action_submit_request` | 1713 | ~132 | |
| `_action_queue_list` | 1845 | ~173 | |
| `_action_daemon_overview` | 2018 | ~250 | Largest handler in scope. |
| `_action_set_tier_config` | 2268 | ~72 | |
| `_action_queue_cancel` | 2340 | ~107 | |
| `_action_subscribe_goal` | 2447 | ~28 | |
| `_action_unsubscribe_goal` | 2475 | ~28 | |
| `_action_list_subscriptions` | 2503 | ~60 | |
| `_action_post_to_goal_pool` | 2563 | ~110 | |
| `_action_submit_node_bid` | 2673 | ~109 | |
| `_action_give_direction` | 2782 | ~38 | |
| `_action_query_world` | 2820 | ~188 | Second-largest handler. |
| `_action_read_premise` | 3008 | ~46 | |
| `_action_set_premise` | 3054 | ~20 | |
| `_action_add_canon` | 3074 | ~70 | |
| `_action_add_canon_from_path` | 3144 | ~150 | Uses `_upload_whitelist_prefixes` (preamble). |
| `_action_list_canon` | 3294 | ~34 | |
| `_action_read_canon` | 3328 | ~42 | |
| `_action_control_daemon` | 3370 | ~82 | Daemon `pause`/`resume`/`status` text-command. |
| `_action_get_activity` | 3452 | ~50 | |
| `_action_get_recent_events` | 3521 | ~88 | Uses `_parse_activity_line` (preamble L3502). |
| `_action_get_ledger` | 3609 | ~13 | |
| `_action_switch_universe` | 3622 | ~29 | |
| `_action_create_universe` | 3651 | ~182 | Largest WRITE handler. |
| (gap) `_parse_activity_line` | 3502 | ~19 | Preamble helper used by `_action_get_recent_events`. **Inside the L1497-L3832 range** but conceptually a parse helper. Move with universe.py since it's only consumed by `_action_get_recent_events`. |

Total: ~2,336 LOC. **One contiguous range** L1497-L3832, no skip-points needed.

---

## 3. Cross-references — bidirectional dependency check

### 3.1 Does universe.py depend on Steps 1-8 (helpers/wiki/status/runs/evaluation/runtime_ops/market/branches) symbols?

**Yes — but lighter than Step 8's branches.py:**

- `_base_path`, `_universe_dir`, `_default_universe`, `_read_json`, `_read_text` from `workflow.api.helpers` (Step 8) — used heavily by every `_action_*` handler. **~50+ call sites.**
- `_storage_backend` (preamble L716) — used by `_action_post_to_goal_pool`, `_action_create_universe`. Stays in preamble per Step 10 plan.
- No reference to dispatch tables from Steps 4-7 (`_RUN_ACTIONS`, `_BRANCH_ACTIONS`, `_JUDGMENT_ACTIONS`, `_PROJECT_MEMORY_ACTIONS`, etc.) — universe-tool actions are siblings, not consumers, of the others.
- `_upload_whitelist_prefixes` (preamble L353) — used by `_action_add_canon_from_path`. Stays in preamble.
- `_format_dirty_file_conflict` (preamble L732) — used by write handlers for `DirtyFileError` shaping. Stays in preamble.

**Strategy:** lazy-import inside each consuming function (same pattern as Steps 4-8). **Expect ~10-15 functions touched** with lazy imports of preamble helpers — much less than Step 8's expected 8-15 because handlers here are mostly self-contained (canon I/O, status reads, queue ops).

### 3.2 Do Steps 1-8 submodules depend on universe.py symbols?

**No — clean leaf module.**

- No Steps-1-8 module imports `_action_list_universes`, `_action_inspect_universe`, etc.
- `_dispatch_with_ledger`, `_scope_universe_response`, `_ledger_target_dir` are universe-tool-internal — verified via grep.
- `WRITE_ACTIONS` is referenced only by `_dispatch_with_ledger` (L929) — table moves with the dispatcher.
- `_daemon_liveness` is used by 3 universe-action handlers (`_action_list_universes`, `_action_inspect_universe`, `_action_daemon_overview`) — all moving together.

**This is the cleanest extraction so far.** universe.py is a true leaf — no Step 1-8 module needs to import from it.

### 3.3 Does universe.py depend on universe_server preamble helpers?

**Yes — substantial preamble dependency, BUT all preamble helpers are slated for Step 10 extraction into `engine_helpers.py`:**

- `_current_actor` — used by ~10 write handlers for ledger attribution.
- `_append_ledger` — called by `_dispatch_with_ledger`.
- `_truncate` — called by all WRITE_ACTIONS extractors.
- `_storage_backend` — `_action_post_to_goal_pool`, `_action_create_universe`.
- `_format_dirty_file_conflict` — `_action_create_universe`, `_action_add_canon*` write paths.
- `_upload_whitelist_prefixes` — `_action_add_canon_from_path`.
- `_split_whitelist_entry` — internal to `_upload_whitelist_prefixes`.
- `_warn_if_no_upload_whitelist` — module-import-time call only (not handler-time).
- `logger` — universe_server-scoped; universe.py defines its own `logger = logging.getLogger("universe_server.universe")`.

**Strategy:** lazy-import inside each consuming function (same pattern as Steps 4-8). After Step 10 ships, the import path becomes `from workflow.api.engine_helpers import _current_actor, _append_ledger, ...`. Until Step 10, lazy-import from `workflow.universe_server`.

**Expect 10-15 functions touched** with lazy imports of preamble helpers.

### 3.4 Does universe.py share dispatch surface with `extensions()`?

**No — verified via L3833-L4495 scan.** The `extensions()` body does NOT reference `universe()`'s dispatch table or any `_action_*` handler from the universe scope. The two MCP tools are siblings with no cross-tool dispatch. This makes universe.py extraction **structurally independent of `extensions()`** — Step 9 lands without touching the `extensions()` body.

### 3.5 `_parse_activity_line` placement (L3502)

This helper sits inside the L1497-L3832 universe-action range but is preamble-style (parses activity log lines). It's consumed only by `_action_get_recent_events` (L3521). **Move with universe.py** since (a) it's inside the contiguous range and (b) it has exactly one caller, also in the range.

---

## 4. FastMCP `mcp` instance — Pattern A2 decision required

`universe()` IS an `@mcp.tool()` registration. Same Pattern A2 question as Step 8's `@mcp.prompt`:

- **Option A** (recommended, consistent with Step 8 §3.6 + #6/#7 Pattern A2): Move the `universe()` body to `tinyassets/api/universe.py` as a plain function `_universe_impl(action, **kwargs) -> str`. Preserve `@mcp.tool() def universe(...)` decorator + 23-arg signature in `tinyassets/universe_server.py` wrapping a delegation to `_universe_impl`. ~25-line wrapper.
- **Option B**: Move `@mcp.tool()` decoration WITH the `universe()` body to `tinyassets/api/universe.py`. Requires `mcp` instance import in `universe.py` (back-edge `from workflow.universe_server import mcp` — same leaf-module concern from audit §6).

**Recommendation: Option A** — consistent with how `goals`, `gates`, `wiki`, `get_status`, and Step 8's `@mcp.prompt` Branch Design Guide are handled. Avoids the leaf-module question entirely. Wrapper preservation is small (~25 LOC for the decorator + signature + delegation).

**Decision asked of lead in §9.**

---

## 5. Test files importing universe-tool symbols (and how)

**Surveyed all 28 `_action_*` handlers + dispatcher trio + daemon-liveness helpers:**

| Symbol | Test files importing | Approx. import count |
|---|---|---|
| `_action_inspect_universe` | `test_inspect_cross_surface_hint.py` (×3) | 3 |
| `_action_submit_request` | `test_phase_e_dispatcher.py` (×1) | 1 |
| `_action_queue_list` | `test_phase_e_dispatcher.py` (×1) | 1 |
| `_action_queue_cancel` | `test_phase_e_dispatcher.py` (×1) + others | ~5 |
| `_action_post_to_goal_pool` | (×6 across various) | 6 |
| `_action_submit_node_bid` | (×5 across various) | 5 |
| `_action_list_subscriptions` | (×2) | 2 |
| `_action_list_universes` | (×1) | 1 |
| `_action_create_universe` | (×1) | 1 |
| `WRITE_ACTIONS` | (×5) | 5 |
| `_daemon_liveness` (monkeypatch target) | `test_inspect_cross_surface_hint.py:23` | 1 |
| `_action_inspect_universe`, `_action_set_premise`, `_action_add_canon`, etc. (other 19 handlers) | Sparse — possibly 0-2 each | ~5-10 |

**Total estimated: ~35-45 test imports across ~10-15 test files.** Materially smaller surface than Step 8 (75+ imports across 25+ files) because the universe-tool surface is older and more stable than branch-CRUD.

**Strategy: back-compat re-export shim** (audit §7 Strategy 1) preserves all imports. Re-export block in `tinyassets/universe_server.py` after Step 9:

```python
from workflow.api.universe import (  # noqa: E402, F401
    WRITE_ACTIONS,
    _action_add_canon,
    _action_add_canon_from_path,
    _action_control_daemon,
    _action_create_universe,
    _action_daemon_overview,
    _action_get_activity,
    _action_get_ledger,
    _action_get_recent_events,
    _action_give_direction,
    _action_inspect_universe,
    _action_list_canon,
    _action_list_subscriptions,
    _action_list_universes,
    _action_post_to_goal_pool,
    _action_query_world,
    _action_queue_cancel,
    _action_queue_list,
    _action_read_canon,
    _action_read_output,
    _action_read_premise,
    _action_set_premise,
    _action_set_tier_config,
    _action_submit_node_bid,
    _action_submit_request,
    _action_subscribe_goal,
    _action_switch_universe,
    _action_unsubscribe_goal,
    _compute_accept_rate_from_db,
    _compute_word_count_from_files,
    _daemon_liveness,
    _dispatch_with_ledger,
    _last_activity_at,
    _ledger_target_dir,
    _parse_activity_line,
    _phase_human,
    _scope_universe_response,
    _staleness_bucket,
)
```

**Monkeypatch-target risk: LOW.** Only **one** confirmed `mock.patch("workflow.universe_server._daemon_liveness", ...)` in `test_inspect_cross_surface_hint.py:23`. After Step 9, that patch needs a mirror on `workflow.api.universe._daemon_liveness` per the #9/#11/Step-8 pattern. **Expected: 1 test edit only** — the lowest patch-target friction of any extraction so far.

**No `monkeypatch.setattr(us, "_action_*", ...)` patterns found** in tests — handlers are imported by name and called directly, not patched.

---

## 6. Risks the audit didn't anticipate

1. **Largest single extraction by LOC.** ~3,075 moveable LOC vs Step 8's ~2,673 and Step 7's ~1,940. universe.py becomes the new largest API submodule. Mitigation: it's also the most semantically coherent — every symbol in scope serves the `universe()` MCP tool.

2. **`@mcp.tool()` Pattern A2 wrapper preservation cost.** Same as Step 8 (~25 LOC wrapper). Acceptable cost for keeping `mcp` instance ownership in universe_server.py.

3. **`_daemon_liveness` is the only test-monkeypatched symbol.** One edit in `test_inspect_cross_surface_hint.py:23`. Trivial.

4. **`WRITE_ACTIONS` extractor closures are tightly coupled to handler return shapes** — refactoring a handler's return JSON would require updating the extractor in the same file. After extraction, both stay co-located in universe.py — better cohesion than today (where extractors and handlers are separated by ~1,000 LOC of preamble).

5. **`_daemon_liveness` reads `<udir>/story.db` directly via sqlite3.** This is a domain-specific path (fantasy_author writes scene_history). After universe.py extraction, this coupling is preserved verbatim — it's a known engine/domain seam (see `docs/exec-plans/active/2026-04-26-engine-domain-coupling-inventory.md`). **Not a blocker for Step 9** — extraction preserves behavior; the domain-coupling cleanup is separate work.

6. **`_compute_word_count_from_files` walks `<udir>/output/**/*.md`** — also fantasy-domain-specific (scene-* files). Same caveat as #5. Preserve verbatim; domain-coupling cleanup is separate.

7. **`_parse_activity_line` is inside the moved range but conceptually preamble.** Single caller; no test imports. Move with universe.py to keep range contiguous.

8. **Single deletion range.** L508-L713 (WRITE_ACTIONS) + L857-L959 (dispatcher trio) + L1060-L1238 (`universe()`) + L1240-L1490 (telemetry) + L1497-L3832 (handlers) — **5 separate deletion sub-ranges** (multi-range, not single). Mirror Steps 4/6 multi-range pattern. Recommend reverse-order deletion to preserve line numbers during edit.

9. **Preamble helpers used by universe.py** (`_current_actor`, `_append_ledger`, `_truncate`, `_storage_backend`, `_format_dirty_file_conflict`, `_upload_whitelist_prefixes`) are all slated for Step 10 extraction into `engine_helpers.py`. **Coordination decision needed** (see §9):
   - Plan A: Step 9 ships first using `from workflow.universe_server import _current_actor, ...` lazy imports; Step 10 then changes those to `from workflow.api.engine_helpers import _current_actor, ...`.
   - Plan B: Land Step 10 BEFORE Step 9 so universe.py imports are already pointed at the right module.
   **Recommend Plan A** — Step 9's universe.py is structurally the cleanest extraction (clear leaf, low test risk); land it first to validate the Pattern A2 wrapper for `@mcp.tool()`. Step 10's preamble extraction is more delicate and benefits from Step 9's validation.

10. **Pre-commit canonical-vs-plugin parity check** — same as previous steps. Run `python packaging/claude-plugin/build_plugin.py`.

11. **Sequencing constraint.** Step 9 strictly after Step 8 (both edit universe_server.py shim block). Confirmed.

12. **Module docstring carries the audit + decomposition history.** Same pattern as Steps 1-8.

---

## 7. Total LOC moved estimate

| Block | LOC |
|---|---|
| WRITE_ACTIONS extractors + table (L508–L713) | ~206 |
| Ledger dispatcher trio (L857–L959) | ~103 |
| `universe()` body (L1075–L1238) — moves to `_universe_impl` (Option A) | ~163 (loses the @mcp.tool decorator + signature, kept in shim) |
| Daemon telemetry helpers (L1240–L1490) | ~251 |
| `_parse_activity_line` (L3502) | ~19 |
| 28 `_action_*` handlers (L1497–L3832 minus L3502) | ~2,317 |
| **Total moved out of universe_server.py** | **~3,059** |
| Back-compat re-export block added to universe_server.py | ~50 |
| `@mcp.tool() def universe(...)` decorator + 23-arg signature wrapper preserved (Option A) | ~50 (decorator + sig + delegation; body is in universe.py) |
| **Net reduction in universe_server.py** | **~2,959** |
| New `tinyassets/api/universe.py` size | **~3,150** (with imports + module docstring + Pattern A2 docstring) |

**Materially larger than Step 8 (~2,593 net reduction).** universe.py becomes the largest single API submodule.

---

## 8. Concrete Step 9 implementation plan

Estimated wall time: **150-210 min** (largest extraction by LOC; multi-range deletion; first `@mcp.tool()` Pattern A2 wrapper for a function with 23-arg signature; ~10-15 lazy-import touch-points; 1 test edit expected).

1. **Confirm Step 8 landed.** Step 8 SHIP must precede Step 9 start.
2. **AST scan for external symbol set.** Identify exact set of universe_server-internal preamble symbols that the moved code references. Lazy-import each in the consuming function. **Expect 10-15 affected functions** with `from workflow.universe_server import _current_actor, _append_ledger, _truncate, _storage_backend, _format_dirty_file_conflict, _upload_whitelist_prefixes`.
3. **Verify `_parse_activity_line` is consumed only by `_action_get_recent_events`** (grep all callers). If single caller, move with universe.py.
4. **Verify `_daemon_liveness` callers are exactly 3 universe-action handlers** (`_action_list_universes`, `_action_inspect_universe`, `_action_daemon_overview`). If any other module imports it, add to re-export shim.
5. **Create `tinyassets/api/universe.py`:**
   - Module docstring referencing audit + extraction date + the source ranges (5 sub-ranges) + Pattern A2 explanation for `@mcp.tool() universe()`.
   - Imports: `from workflow.api.helpers import _base_path, _default_universe, _universe_dir, _read_json, _read_text` + std-lib + typing + `logging.getLogger("universe_server.universe")`.
   - Move L508-L713 verbatim (WRITE_ACTIONS extractors + table).
   - Move L857-L959 verbatim (`_ledger_target_dir`, `_scope_universe_response`, `_dispatch_with_ledger`).
   - Move L1240-L1490 verbatim (daemon telemetry).
   - Move L3502 `_parse_activity_line` (alongside its caller).
   - Move L1497-L3832 verbatim (28 `_action_*` handlers).
   - For Option A: extract `universe()` body as `def _universe_impl(action: str, **kwargs: Any) -> str` exposing the dispatch logic; the `@mcp.tool()` decorator stays in universe_server.py.
6. **Update `tinyassets/universe_server.py`:**
   - Delete L508-L713 (WRITE_ACTIONS).
   - Delete L857-L959 (dispatcher trio).
   - Delete L1060-L1238 (`universe()` body — replaced by Pattern A2 wrapper).
   - Delete L1240-L1490 (telemetry).
   - Delete L1497-L3832 (handlers).
   - **Reverse-order deletion recommended** (highest line ranges first) to preserve line numbers during edits.
   - Add to back-compat shim block (re-export ~37 symbols — see §5).
   - Add `@mcp.tool(...) def universe(action, ..., tag) -> str: return _universe_impl(action, ..., tag)` Pattern A2 wrapper. Preserve full 23-arg signature + decorator + `title="Universe Operations"` + tags + ToolAnnotations + docstring.
7. **Test edits expected.** 1 edit in `test_inspect_cross_surface_hint.py:23` to add mirror `mock.patch("workflow.api.universe._daemon_liveness", ...)`. Verify no other monkeypatch targets fall in scope.
8. **Run `python packaging/claude-plugin/build_plugin.py`** to sync plugin runtime mirror.
9. **Verification:**
   - `pytest tests/test_inspect_cross_surface_hint.py tests/test_phase_e_dispatcher.py tests/test_canonical_branch_mcp.py -q` → green.
   - `pytest -k "universe or action or daemon" -q` → cross-cutting smoke.
   - `pytest -q` → full suite green (essential — universe.py is the largest single extraction; touches ledger surface).
   - `ruff check tinyassets/api/universe.py tinyassets/universe_server.py` → clean.
   - **Visual check:** `git diff tinyassets/universe_server.py | grep -c "^-def _action_"` should equal **28**.
   - **Visual check:** `git diff tinyassets/universe_server.py | grep -c "^-def _extract_"` should equal **13** (14 entries, but `_extract_set_tier_config` is the last — count shows 13 deleted plus the dict literal).
   - **MCP probe:** `python scripts/mcp_probe.py --tool universe --args '{"action":"list"}'` → returns valid universe list. Validates Pattern A2 wrapper.

**Files in eventual Step 9 SHIP handoff:**
- `tinyassets/api/universe.py` (NEW, ~3,150 LOC — largest single-file extraction)
- `tinyassets/universe_server.py` (~3,059 LOC removed + ~50 re-export added + ~50 universe-wrapper preservation = net ~−2,959)
- `tests/test_api_universe.py` (NEW, 70-100 tests recommended)
- 1 existing test file with monkeypatch-target update (`test_inspect_cross_surface_hint.py`)
- `packaging/claude-plugin/.../tinyassets/api/universe.py` (NEW mirror)
- `packaging/claude-plugin/.../tinyassets/universe_server.py` (mirror)

5-7 files, +3,200 / −2,950 LOC net.

---

## 9. Decision asks for the lead

1. **Option A (recommended) vs Option B for `@mcp.tool() universe()`** — see §4. Recommend Option A (preserve `@mcp.tool()` decorator + 23-arg signature + docstring in universe_server.py with delegation to `_universe_impl` in universe.py). Avoids leaf-module question. Wrapper cost ~50 LOC.

2. **Step 9 vs Step 10 ordering** — see §6.9. Recommend **Plan A** (Step 9 first, Step 10 after). Step 9 is the cleaner leaf extraction; lazy-imports of preamble helpers continue to point at `workflow.universe_server` until Step 10 reroutes them to `workflow.api.engine_helpers`. This sequences validation work — Pattern A2 wrapper for `universe()` is proven before tackling the more delicate preamble split.

3. **Multi-range deletion (5 sub-ranges) — reverse-order edit.** Mirror Steps 4/6 pattern. Recommend reverse-order deletion (highest line numbers first: L3832 → L1497 → L1490 → L1240 → L1238 → L1060 → L959 → L857 → L713 → L508) to preserve line numbers during edit.

4. **Audit-target reaffirmation.** Step 9 + Step 10 are post-original-8-step extensions explicitly to chase the audit's "~100-LOC routing shell" goal. After Step 9, residual is projected at **~2,150 LOC** (preamble engine helpers L451-L905 + extensions tool body + 6 @mcp.tool/@mcp.prompt wrappers + back-compat shims). Step 10 then targets the remaining ~1,500 LOC of preamble helpers. Final residual after Step 10: **~650 LOC** (extensions() body + 6 wrapper preservations + shim block) — still ~6× the audit's ~100-LOC target but materially closer than today's 7,778. Lead should explicitly approve this two-step extension to the original 8-step plan, OR accept ~5,100 LOC residual after Step 8 as the new steady state.

5. **Domain-coupling preserved verbatim.** `_daemon_liveness` reads `story.db`; `_compute_word_count_from_files` walks scene-*.md files. These are known engine/domain seams in the coupling inventory. Step 9 preserves them — the cleanup is separate work (engine/domain API separation; see Concern 2026-04-26 in STATUS.md).

---

## 10. Cross-prep summary (Steps 1-9 combined, projected)

After Step 9 lands:

| Step | New file | Net LOC removed from universe_server.py | Cumulative universe_server.py size |
|---|---|---|---|
| baseline (2026-04-26) | — | — | 14,012 |
| #8 ✅ | extends `helpers.py` | ~16 | ~13,996 |
| #9 ✅ | `wiki.py` | ~1,360 | ~12,636 |
| #10 ✅ | `status.py` | ~422 | ~12,214 |
| Step 4 ✅ | `runs.py` | ~1,379 | ~10,835 |
| Step 5 ✅ | `evaluation.py` | ~822 | ~10,013 |
| Step 6 ✅ | `runtime_ops.py` | ~458 | ~9,555 |
| Step 7 ✅ | `market.py` | ~1,940 | ~7,615 |
| Step 8 (in-flight) | `branches.py` | ~2,513 | ~5,100 |
| Step 9 (this prep) | `universe.py` | ~2,959 | **~2,150** |
| **Subtotal after Step 9** | 7 new + 1 extended | ~11,869 | **~2,150** |

**universe_server.py crosses below ~2,150 LOC after Step 9** (from baseline 14,012 = ~85% reduction). Remaining content: preamble engine helpers (~1,500 LOC, slated for Step 10), `extensions()` body (~600 LOC, stays as routing-shell), 6 @mcp.tool/@mcp.prompt wrapper preservations (~150 LOC), back-compat shim block (~150 LOC).

Step 10 then drives toward the audit's "~100-LOC routing shell" target by extracting the preamble engine helpers — see Step 10 prep.

All 9 steps remain pure refactor — no behavior change. The decomposition's stated goal of "make universe_server.py readable + composable" is met (no single submodule >3,150 LOC, vs baseline 14,012-LOC monolith).
