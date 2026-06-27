---
title: Step 8 prep — tinyassets/api/branches.py extraction scope
date: 2026-04-26
author: dev
status: pre-flight scoping (no edits yet)
companion: docs/audits/2026-04-25-universe-server-decomposition.md §4.6 (`branches.py`), §8 step 8
target_task: Decomp audit Step 8 — Extract tinyassets/api/branches.py (LAST step)
gates_on: Steps 1-6 ✅ landed. Step 7 (market.py) MUST land before Step 8 — both edit `tinyassets/universe_server.py`. After Step 8 SHIP, residual universe_server.py is the projected ~4,400-LOC routing shim — close to (but not identical to) the audit's "~100-LOC routing shell" target (residual still owns `extensions()` body, `universe()` body, preamble engine helpers, and the 6 @mcp.tool wrappers preserved by Pattern A2).
---

# Step 8 (`branches.py`) pre-flight scope

Read-only scope for extracting the branch authoring + node CRUD subsystem from `tinyassets/universe_server.py` into a new `tinyassets/api/branches.py`. **Largest single extraction by LOC** (~2,675 in current code, audit said ~3,282) and the most cross-referenced. Same freshness-check protocol as Steps 1-7 prep.

---

## 1. Audit-vs-reality verdict

**Audit estimate (§4.6):** branches.py LOC ~3,282. Audit lists scope: `_BRANCH_ACTIONS`, `_BRANCH_WRITE_ACTIONS`, `_BRANCH_VERSION_ACTIONS`, all `_action_*` and `_ext_branch_*` handlers for branch CRUD + composite build/patch + node manipulation, plus `_resolve_branch_id`, `_ext_branch_describe`, `_ext_branch_get`, `_related_wiki_pages`. Audit framing: "Largest submodule; highest dependency density; last because it shares helpers with runs and evaluation."

**Reality (current code, 2026-04-26 post-Step-6):**

| Block | Banner / Section | Line range | LOC (est.) |
|---|---|---|---|
| Phase 2 banner + helpers | "Phase 2: Community Branches" L4435 | L4435–L4658 | ~224 |
| `_ext_branch_*` core handlers | (no banner) | L4660–L5099 | ~440 |
| `_related_wiki_pages` group | (no banner) | L5100–L5184 | ~85 |
| `_ext_branch_describe` + helpers | (no banner) | L5185–L5719 | ~535 |
| `_ext_branch_build` (composite) | "── Composite: build_branch / patch_branch ──" L5302 + L5747 | L5720–L6026 | ~307 |
| `_ext_branch_patch` + downstream | (no banner) | L6027–L6657 | ~631 |
| `_resolve_udir` + `_action_*` | (no banner) | L6658–L6939 | ~282 |
| `_BRANCH_ACTIONS` + `_BRANCH_WRITE_ACTIONS` | (no banner) | L6940–L6964 | ~25 |
| `@mcp.prompt("Branch Design Guide")` | (no banner) | L6967–L7110 | ~144 |

**Total moveable: ~2,675 LOC.** Audit said ~3,282 — about 18% under (pre-decomp audit, but several large helpers like `_ext_branch_describe` (~535 LOC) didn't grow as much as audit assumed).

**Audit framing CONFIRMED:** All 23 handlers + helpers are branch-CRUD or node-manipulation concerns. The `@mcp.prompt` "Branch Design Guide" is a chatbot-facing prompt registration — moves with branches.py since it's branch-specific guidance.

**`_BRANCH_VERSION_ACTIONS` already extracted in Step 5 (`evaluation.py`)** — audit's listing of it under branches.py was stale. Confirmed: `_BRANCH_VERSION_ACTIONS` lives in `tinyassets/api/evaluation.py` since commit 555712e.

---

## 2. Symbol enumeration (current line ranges)

### 2.1 Branches Phase 2 preamble + dispatcher (L4435–L4658)

| Symbol | Line | LOC | Notes |
|---|---|---|---|
| Phase 2 banner | 4435 | ~5 | "Phase 2: Community Branches — author/edit BranchDefinition over MCP" |
| `_dispatch_branch_action` | 4533 | ~103 | Ledger glue; calls `_append_global_ledger` + `_truncate` |
| `_resolve_branch_id` | 4636 | ~24 | Branch-name → branch_id resolver. **Currently lazy-imported by `workflow.api.runs._action_run_branch` per #11.** |
| `_ext_branch_create` | 4602 | ~34 | First _ext_branch_* handler |

### 2.2 Branch CRUD handlers (L4660–L5099)

| Handler | Line | LOC | Notes |
|---|---|---|---|
| `_ext_branch_get` | 4660 | ~40 | |
| `_ext_branch_list` | 4700 | ~47 | |
| `_ext_branch_delete` | 4747 | ~12 | |
| `_ext_branch_add_node` | 4759 | ~68 | |
| `_ext_branch_connect_nodes` | 4827 | ~42 | |
| `_ext_branch_set_entry_point` | 4869 | ~40 | |
| `_ext_branch_add_state_field` | 4909 | ~57 | |
| `_ext_branch_validate` | 4966 | ~134 | Largest CRUD handler |

### 2.3 `_related_wiki_pages` group (L5100–L5184)

| Symbol | Line | LOC | Notes |
|---|---|---|---|
| `_RELATED_WIKI_CAP` | 5100 | 1 | Constant |
| `_related_summary` | 5104 | ~28 | |
| `_related_wiki_pages` | 5132 | ~53 | **Cross-cuts wiki:** uses `_parse_frontmatter`, `_page_rel_path`, `_wiki_pages_dir`, `_find_all_pages` — currently re-exported via `workflow.universe_server` shim from `workflow.api.wiki` (post-#9). After Step 8, branches.py imports them directly from `workflow.api.wiki` and `workflow.api.helpers`. |

### 2.4 `_ext_branch_describe` + helpers (L5185–L5719)

| Symbol | Line | LOC | Notes |
|---|---|---|---|
| `_ext_branch_describe` | 5185 | ~217 | **Largest single handler in branches.py** |
| `_resolve_node_spec` | 5402 | ~318 | Node-spec resolver helper used by build/patch composites |

### 2.5 Composite build/patch handlers (L5720–L6657)

| Symbol | Line | LOC | Notes |
|---|---|---|---|
| `_build_branch_text` | 5720 | ~27 | Markdown rendering helper |
| `_ext_branch_build` | 5747 | ~280 | Composite create_branch + add_nodes + connect_nodes — largest single MCP handler in repo |
| `_ext_branch_patch` | 6027 | ~150 | Composite patch handler |
| `_ext_branch_update_node` | 6177 | ~225 | |
| `_ext_branch_search_nodes` | 6402 | ~121 | |
| `_ext_branch_patch_nodes` | 6523 | ~135 | Bulk-patch handler |

### 2.6 `_action_*` handlers + `_resolve_udir` (L6658–L6939)

| Symbol | Line | LOC | Notes |
|---|---|---|---|
| `_resolve_udir` | 6658 | ~17 | Universe-dir resolver helper for action handlers |
| `_action_continue_branch` | 6675 | ~200 | |
| `_action_fork_tree` | 6875 | ~65 | |

### 2.7 Dispatch table (L6940–L6964)

| Symbol | Line | LOC | Notes |
|---|---|---|---|
| `_BRANCH_ACTIONS` | 6940 | 19 | Dict literal — 17 handlers |
| `_BRANCH_WRITE_ACTIONS` | 6960 | 5 | Frozenset |

### 2.8 `@mcp.prompt` Branch Design Guide (L6967–L7110)

| Symbol | Line | LOC | Notes |
|---|---|---|---|
| `@mcp.prompt(title="Branch Design Guide", ...)` | 6967 | ~144 | Chatbot-facing prompt body. **First @mcp.prompt extraction.** Pattern decision needed — see §3.6. |

---

## 3. Cross-references — bidirectional dependency check

### 3.1 Does branches.py depend on Steps 1-7 (helpers/wiki/status/runs/evaluation/runtime_ops/market) symbols?

**Yes — multiple back-edges, all cleanly importable:**
- `_parse_frontmatter`, `_page_rel_path` from `workflow.api.wiki` (used by `_related_wiki_pages`).
- `_wiki_pages_dir`, `_find_all_pages`, `_base_path`, `_universe_dir`, `_default_universe`, `_read_json`, `_read_text` from `workflow.api.helpers`.
- No reference to Steps 4/5/6/7 dispatch tables (`_RUN_ACTIONS`, `_JUDGMENT_ACTIONS`, `_PROJECT_MEMORY_ACTIONS`, etc.) — branches.py is upstream of those in the dataflow.

### 3.2 Do Steps 1-7 submodules depend on branches.py symbols?

**Yes — `_resolve_branch_id` is referenced by Step 4 (runs.py) per #11's lazy-import block:**
- `tinyassets/api/runs.py` `_action_run_branch` lazy-imports `from workflow.universe_server import _current_actor, _resolve_branch_id`.
- After Step 8 lands, that import path needs to update to `from workflow.api.branches import _resolve_branch_id` (or stay via re-export shim if branches.py is re-exported from universe_server).

**Strategy:** Keep `_resolve_branch_id` re-exported from `workflow.universe_server` via the back-compat shim block. **No edit needed** to runs.py — the existing `from workflow.universe_server import _current_actor, _resolve_branch_id` continues to work. Same pattern applies to any other Step 4-7 module that imports branches symbols.

### 3.3 Does branches.py depend on universe_server preamble helpers?

**Yes — the most heavily preamble-coupled extraction so far.** Expected dependencies (verify via AST scan at extraction time):
- `_current_actor` — actor-credit on every write handler. Very high frequency (~15+ call sites).
- `_append_global_ledger` + `_truncate` — used by `_dispatch_branch_action` (L4533).
- `_ensure_author_server_db` — likely used by `_ext_branch_create` and other write handlers.
- `_format_dirty_file_conflict` — used by branch-write handlers per the Phase 6.3 dirty-file guard pattern (similar to `gates`).
- `_storage_backend` — used by build/patch handlers (test mocks this in `tests/test_build_branch_summary_response.py`).
- `_apply_node_spec` — referenced by `tests/test_build_branch_summary_response.py:271` as `workflow.universe_server._apply_node_spec` — **need to grep for current location and either move with branches or document as preamble-resident.**
- `_gates_enabled` — referenced by `tests/test_describe_branch_approval.py` and `tests/test_describe_branch_wiki_pages.py` — preamble helper.
- `logger` — universe_server-scoped; branches.py defines its own `logger = logging.getLogger("universe_server.branches")`.

**Strategy:** lazy-import inside each consuming function (same pattern as #11/#12/#13). **Expect the largest lazy-import set yet** — likely 8-15 functions touched.

### 3.4 Does branches.py share dispatch surface with `extensions()`?

**Yes — 1 dispatch read in `extensions()` body (L4065-L4067):**
```python
branch_handler = _BRANCH_ACTIONS.get(action)
if branch_handler is not None:
    return _dispatch_branch_action(action, branch_handler, branch_kwargs)
```

After Step 8 lands, `extensions()` body needs **one new import line** at top of universe_server.py:
```python
from workflow.api.branches import _BRANCH_ACTIONS, _BRANCH_WRITE_ACTIONS, _dispatch_branch_action
```

Structurally identical to Step 4 (`_RUN_ACTIONS`) pattern. **Trivial; not a refactor of `extensions()` body.**

### 3.5 `_BRANCH_VERSION_ACTIONS` — already extracted in Step 5

The audit listed `_BRANCH_VERSION_ACTIONS` under branches.py scope, but **Step 5 (evaluation.py) extracted it** per the audit's own §4.4 listing. Current location: `tinyassets/api/evaluation.py`. **Do NOT re-extract.** Confirmed via grep: `_BRANCH_VERSION_ACTIONS` defined in evaluation.py only.

### 3.6 `@mcp.prompt` "Branch Design Guide" — Pattern A2 with prompt decoration

This is the first extraction with an `@mcp.prompt` decoration to preserve. Same Pattern A2 logic as `@mcp.tool` for `goals`/`gates`/`wiki`/`get_status`:

- **Option A**: Move the prompt body to branches.py as a plain function/string; preserve `@mcp.prompt` decorator + signature in universe_server.py wrapping a delegation. Same as how Pattern A2 handles `@mcp.tool`.
- **Option B**: Move `@mcp.prompt` decoration WITH the prompt body to branches.py. Requires `mcp` instance import in branches.py (back-edge `from workflow.universe_server import mcp` — same back-edge concern as audit §6 leaf-module discussion).

**Recommendation:** **Option A** — consistent with Steps 9/10's Pattern A2 for `@mcp.tool`. Avoids the leaf-module question entirely. The wrapper preservation is ~144 LOC of decorator + docstring + delegation — non-trivial but acceptable cost. branches.py exposes the prompt body as a plain string constant or function.

**Decision needed for lead:** Option A or Option B. Recommend A.

---

## 4. FastMCP `mcp` instance — inherits #9 decision (with prompt nuance)

Same Pattern A2 inheritance as Steps 1-7. **Inherited.**

`branches.py` does NOT register any `@mcp.tool()` decorator directly. The `@mcp.prompt` decoration question is handled per §3.6 (recommend Option A — preserve in universe_server.py with delegation).

---

## 5. Test files importing branches symbols (and how)

This is the **highest test-import surface of any extraction**. Counted at least 75+ direct test imports across ~25 test files. Comprehensive list (sampled — verify exhaustively at extraction time):

| Test file | Symbol(s) imported (sampled) | Rough count |
|---|---|---|
| `tests/test_branch_name_resolution.py:30,99` | `_current_actor`, `_base_path`, `_related_wiki_pages` (patch targets) | ~3 |
| `tests/test_build_branch_summary_response.py:82-420` | `_base_path`, `_storage_backend`, `_apply_node_spec`, `_current_actor` | ~10 |
| `tests/test_describe_branch_approval.py:51-90` | `_base_path`, `_current_actor`, `_gates_enabled` | ~6 |
| `tests/test_describe_branch_wiki_pages.py:50-296` | `_related_wiki_pages` (×11), `_ext_branch_describe`, `_ext_branch_get` | ~14 |
| `tests/test_patch_branch_readback.py:43` | `_base_path` | ~1 |
| `tests/test_canonical_branch_mcp.py:115,126` | `_BRANCH_ACTIONS` | 2 |
| Plus untold others | `_ext_branch_*`, `_action_continue_branch`, `_action_fork_tree`, `_dispatch_branch_action`, `_BRANCH_ACTIONS`, `_BRANCH_WRITE_ACTIONS`, `_resolve_branch_id` | ~50+ |

**Strategy:** Audit §7 Strategy 1 (back-compat re-export shim) preserves all imports. After Step 8 lands, `tinyassets/universe_server.py` adds re-export block for ~30 symbols (17 handlers in `_BRANCH_ACTIONS` + 2 dispatch dict + dispatcher + helpers + `_resolve_branch_id` + `_related_wiki_pages` + the prompt body).

**Direct test-import surface estimated 75+ imports** across ~25 test files. **Largest re-export block of any extraction.** Re-export shim handles all without test edits — same pattern as Steps 4-7.

**Monkeypatch-target risk: HIGH.** Several tests do `mock.patch("workflow.universe_server._base_path", ...)` or `monkeypatch.setattr(us, "_current_actor", ...)`. After branches.py extracts handlers that call `_base_path` / `_current_actor`, those patches won't reach (same class as #9 mock.patch fix and #11 monkeypatch fix). **Expect 3-6 monkeypatch-target test edits** per the patterns documented in #9 + #11.

---

## 6. What partially-moved (the helpers-already-extracted lesson)

Searched for evidence that any branches-scope symbols already shipped to a submodule (e.g. `workflow.api.branches`). **None found in the API layer.**

Note: there IS a `tinyassets/branches.py` (storage layer for `BranchDefinition` + `patch_branch_definition`, etc.) — that's the **persistence backend** that the API handlers wrap. Different namespace. Inside branches.py (API), imports stay as `from workflow.branches import BranchDefinition, NodeDefinition, ...` (storage). **Verify no name collision** at extraction time — the new file is `tinyassets/api/branches.py`, not `tinyassets/branches.py`.

Adjacent partial moves:
- 5 helpers in #8 — most branch handlers already use `_base_path` from helpers.py.
- `_parse_frontmatter`, `_page_rel_path` from #9 (wiki.py) — `_related_wiki_pages` will import them.
- `_BRANCH_VERSION_ACTIONS` from #5 (evaluation.py) — already extracted, not re-extracted here.

---

## 7. Total LOC moved estimate

| Block | LOC |
|---|---|
| Phase 2 preamble + dispatcher + resolver (L4435–L4658) | ~224 |
| Branch CRUD handlers (L4660–L5099) | ~440 |
| `_related_wiki_pages` group (L5100–L5184) | ~85 |
| `_ext_branch_describe` + node-spec resolver (L5185–L5719) | ~535 |
| Composite build/patch handlers (L5720–L6657) | ~938 |
| `_resolve_udir` + `_action_*` (L6658–L6939) | ~282 |
| `_BRANCH_ACTIONS` + `_BRANCH_WRITE_ACTIONS` (L6940–L6964) | ~25 |
| `@mcp.prompt` Branch Design Guide BODY moved to branches.py (Option A) | ~144 |
| **Total moved out of universe_server.py** | **~2,673** |
| Back-compat re-export block added to universe_server.py | ~50 |
| `@mcp.prompt` decorator + signature wrapper preserved (Option A) | ~30 (decorator + signature + delegation; body is in branches.py) |
| **Net reduction in universe_server.py** | **~2,593** |
| New `tinyassets/api/branches.py` size | **~2,750** (with imports + module docstring) |

**Audit said ~3,282.** Reality ~2,673 — about 18% under. The wrapper preservation is much smaller than market.py (only 1 prompt vs 2 MCP tools).

---

## 8. Risks the audit didn't anticipate

1. **Highest test-import surface.** ~75+ direct imports across ~25 test files. Re-export shim covers all blanket imports cleanly, but **monkeypatch-target risk is HIGH** — `mock.patch("workflow.universe_server.X", ...)` and `monkeypatch.setattr(us, "X", ...)` patterns abound. Expect 3-6 test edits per the #9 + #11 extraction-aware patch-target pattern.

2. **Largest contiguous block** (L4435–L7110 = ~2,675 LOC, single super-range). No skip-points needed for non-runtime_ops/non-evaluation siblings — all 2,675 LOC are pure branches scope. Single deletion range, no reverse-order needed.

3. **`_apply_node_spec` location uncertainty.** `tests/test_build_branch_summary_response.py:271` patches `workflow.universe_server._apply_node_spec`. Need to grep current code to confirm whether `_apply_node_spec` is inside the L4435–L7110 branches range (moves with branches.py) or in preamble (stays). **Verify at extraction time.** If inside the range, it moves; if preamble, the patch target stays correct.

4. **`_storage_backend` placement.** `tests/test_build_branch_summary_response.py:272,329,373,420` patches `workflow.universe_server._storage_backend`. **Need to grep current location** — likely preamble (storage helper used by many subsystems, not just branches). If preamble, patches stay correct after Step 8.

5. **`_gates_enabled` placement.** `tests/test_describe_branch_approval.py:71` patches `workflow.universe_server._gates_enabled`. **Need to grep current location** — likely preamble (gates feature flag, used by branches but not branches-owned). Patches stay correct.

6. **`@mcp.prompt` decoration is FIRST extraction with this pattern.** Recommend Option A (preserve decoration in universe_server.py wrapping a delegation to branches.py prompt body). This avoids leaf-module question. Decision needed from lead.

7. **`_resolve_branch_id` is consumed by Step 4 (runs.py)** — already documented in §3.2. Re-export shim handles this; no runs.py edit needed.

8. **`_dispatch_branch_action` ledger writes** call `_append_global_ledger` + `_truncate`. Same lazy-import pattern as Steps 4/5/6.

9. **`@mcp.prompt` "Branch Design Guide" body is 144 LOC of chatbot-facing markdown** — moving it preserves the prompt registration; chatbots still see the same prompt content.

10. **Pre-commit canonical-vs-plugin parity check** — same as previous steps. Run `python packaging/claude-plugin/build_plugin.py`.

11. **Sequencing constraint.** Step 8 strictly after Step 7 (both edit universe_server.py shim block). Confirmed.

12. **Residual universe_server.py post-Step-8.** The audit projected "~100-LOC routing shell." Reality after all 8 extractions: residual is projected at **~4,400 LOC**, containing:
    - Module preamble (imports + constants + `mcp` instance) ~200 LOC
    - Engine helpers (`_current_actor`, `_truncate`, `_append_global_ledger`, `_resolve_branch_id`, `_ensure_author_server_db`, `_apply_node_spec`, `_storage_backend`, `_gates_enabled`, `_format_dirty_file_conflict`, `_dispatch_with_ledger`, `_daemon_liveness`, `_parse_activity_line`, etc.) ~1,500 LOC
    - `universe()` MCP tool body + 30+ `_action_*` handlers ~2,000 LOC
    - `extensions()` MCP tool body ~400 LOC
    - 6 @mcp.tool / @mcp.prompt wrapper preservations from Pattern A2 ~300 LOC
    - Back-compat re-export blocks (Steps 1-8) ~150 LOC

The audit's "100-LOC routing shell" target requires further extraction beyond Step 8: `universe.py` for the `universe()` tool + actions, `engine_helpers.py` for the preamble engine functions. Those are **out of scope for the original 8-step plan** — discuss with lead whether to add Steps 9+10 after Step 8 ships.

---

## 9. Concrete Step 8 implementation plan

Estimated wall time: **120-180 min** (largest extraction; most cross-references; 3-6 test edits expected).

1. **Confirm Steps 1-7 landed.** Step 7 must SHIP before Step 8 starts.
2. **AST scan for external symbol set.** Identify exact set of universe_server-internal symbols that the moved code references. Lazy-import each in the consuming function. Expect 8-15 affected functions.
3. **Verify `_apply_node_spec`, `_storage_backend`, `_gates_enabled` locations** — confirm whether they're inside L4435–L7110 (move with branches) or in preamble (stay).
4. **Create `tinyassets/api/branches.py`:**
   - Module docstring referencing audit + extraction date + the source range + cross-module dependencies (wiki re-imports + Pattern A2 explanation for `@mcp.prompt` Branch Design Guide).
   - Imports: `from workflow.api.helpers import _base_path, _default_universe, _universe_dir, _read_json, _read_text, _wiki_pages_dir, _find_all_pages` + `from workflow.api.wiki import _parse_frontmatter, _page_rel_path` + std-lib + typing + `logging.getLogger("universe_server.branches")`.
   - Move L4435–L7110 verbatim (preserving all section banners + helpers + handlers + `_BRANCH_ACTIONS` + `_BRANCH_WRITE_ACTIONS`). For Option A: extract `@mcp.prompt` body as a plain function `_branch_design_guide_prompt() -> str` exposing the markdown body; the decorator stays in universe_server.py.
5. **Update `tinyassets/universe_server.py`:**
   - Delete L4435–L7110 (single deletion, no reverse order needed since it's contiguous and there's no skip).
   - Add to back-compat shim block:
     ```python
     from workflow.api.branches import (  # noqa: E402, F401
         _BRANCH_ACTIONS,
         _BRANCH_WRITE_ACTIONS,
         _RELATED_WIKI_CAP,
         _action_continue_branch,
         _action_fork_tree,
         _build_branch_text,
         _dispatch_branch_action,
         _ext_branch_add_node,
         _ext_branch_add_state_field,
         _ext_branch_build,
         _ext_branch_connect_nodes,
         _ext_branch_create,
         _ext_branch_delete,
         _ext_branch_describe,
         _ext_branch_get,
         _ext_branch_list,
         _ext_branch_patch,
         _ext_branch_patch_nodes,
         _ext_branch_search_nodes,
         _ext_branch_set_entry_point,
         _ext_branch_update_node,
         _ext_branch_validate,
         _related_summary,
         _related_wiki_pages,
         _resolve_branch_id,
         _resolve_node_spec,
         _resolve_udir,
     )
     ```
   - Add `@mcp.prompt(title="Branch Design Guide", ...)` decorator + thin wrapper that returns `_branch_design_guide_prompt()` from branches.py.
6. **Test edits expected.** Re-grep tests for `mock.patch("workflow.universe_server.X", ...)` and `monkeypatch.setattr(us, "X", ...)` patterns where X is now in branches.py. Add mirror patches on `workflow.api.branches.X` per the #9 + #11 pattern. **Expected:** 3-6 test files touched, 5-15 lines edited total.
7. **Run `python packaging/claude-plugin/build_plugin.py`** to sync plugin runtime mirror.
8. **Verification:**
   - `pytest tests/test_branch_*.py tests/test_build_branch*.py tests/test_describe_branch*.py tests/test_patch_branch*.py tests/test_canonical_branch_mcp.py tests/test_run_branch_*.py -q` → green.
   - `pytest -k "branch or extensions" -q` → cross-cutting smoke.
   - `pytest -q` → full suite green (essential — branches.py touches 25+ test files).
   - `ruff check tinyassets/api/branches.py tinyassets/universe_server.py` → clean.
   - **Visual check:** `git diff tinyassets/universe_server.py | grep -c "^-def _"` should equal **23** (17 `_ext_branch_*` + `_action_continue_branch` + `_action_fork_tree` + `_dispatch_branch_action` + `_resolve_branch_id` + `_resolve_node_spec` + `_resolve_udir` + `_build_branch_text` + `_related_summary` + `_related_wiki_pages`). Note: actual count depends on whether `_apply_node_spec` is inside the range. Recompute after extraction.

**Files in eventual Step 8 SHIP handoff:**
- `tinyassets/api/branches.py` (NEW, ~2,750 LOC — largest single-file extraction)
- `tinyassets/universe_server.py` (~2,593 LOC removed + ~50 re-export added + ~30 prompt-wrapper preservation = net ~−2,513)
- `tests/test_api_branches.py` (NEW, 70-100 tests recommended)
- 3-6 existing test files with monkeypatch-target updates
- `packaging/claude-plugin/.../tinyassets/api/branches.py` (NEW mirror)
- `packaging/claude-plugin/.../tinyassets/universe_server.py` (mirror)

7-10 files, +2,800 / −2,510 LOC net.

---

## 10. Decision asks for the lead

1. **Option A (recommended) vs Option B for `@mcp.prompt`** — see §3.6. Recommend Option A (preserve decoration in universe_server.py with delegation to branches.py prompt-body function). Avoids leaf-module question.
2. **Audit "100-LOC routing shell" target unattainable in 8 steps.** Residual universe_server.py post-Step-8 is projected at ~4,400 LOC, not ~100. Discuss whether to plan Steps 9+10 (`universe.py` + `engine_helpers.py`) post-Step-8 ship, or accept ~4,400 LOC residual as the new steady state.
3. **Test-edit budget.** Expect 3-6 monkeypatch-target test edits. Acceptable given they're additive (mirror patches alongside the existing `us.X` patches per the #9/#11 pattern), and the alternative (changing branches.py to look up names via universe_server) would defeat the extraction purpose.
4. **Single-deletion vs sub-range deletion.** L4435–L7110 is contiguous; no skip-points. Recommend single deletion to minimize diff complexity. Mirror Steps 1/2/3/5 pattern (single-range), not Steps 4/6 pattern (multi-range).

---

## 11. Cross-prep summary (Steps 1-8 combined)

After Step 8 lands:

| Step | New file | Net LOC removed from universe_server.py | Cumulative universe_server.py size |
|---|---|---|---|
| baseline (2026-04-26) | — | — | 14,012 |
| #8 ✅ | extends `helpers.py` | ~16 | ~13,996 |
| #9 ✅ | `wiki.py` | ~1,360 | ~12,636 |
| #10 ✅ | `status.py` | ~422 | ~12,214 |
| Step 4 ✅ | `runs.py` | ~1,379 | ~10,835 |
| Step 5 ✅ | `evaluation.py` | ~822 | ~10,013 |
| Step 6 ✅ | `runtime_ops.py` | ~458 | ~9,555 |
| Step 7 (prep ready) | `market.py` | ~1,940 | ~7,615 |
| Step 8 (this prep) | `branches.py` | ~2,513 | **~5,100** |
| **Total** | 6 new + 1 extended | ~8,910 | **~5,100** |

**universe_server.py crosses below ~5,100 LOC after Step 8** (from baseline 14,012 = ~64% reduction). This is materially larger than the audit's "~100-LOC routing shell" target — see §10.2. Path to the audit target requires Steps 9+10 (`universe.py` + `engine_helpers.py`) which are NOT in the original 8-step plan.

All 8 steps remain pure refactor — no behavior change. The decomposition's stated goal of "make universe_server.py readable + composable" is met (no single submodule >2,750 LOC, vs baseline 14,012-LOC monolith).
