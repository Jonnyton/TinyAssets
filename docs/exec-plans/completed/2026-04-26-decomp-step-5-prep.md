---
title: Step 5 prep — tinyassets/api/evaluation.py extraction scope
date: 2026-04-26
author: navigator
status: pre-flight scoping (no edits yet)
companion: docs/audits/2026-04-25-universe-server-decomposition.md §4.2 (`evaluation.py`), §8 step 5
target_task: Decomp audit Step 5 — Extract tinyassets/api/evaluation.py
gates_on: #8 (helpers) ✅ landed (4f98654); #9 (wiki.py) in flight; #10 (status.py) queued; Step 4 (runs.py) queued. Step 5 is sequenced AFTER Step 4 per audit §8.
---

# Step 5 (`evaluation.py`) pre-flight scope

Read-only scope for extracting the multi-criteria evaluation surface (Phase 4 judgment + iteration hooks) and branch-versioning handlers from `tinyassets/universe_server.py` into a new `tinyassets/api/evaluation.py`. Same freshness-check protocol as #9/#10/Step 4 prep.

---

## 1. Audit-vs-reality verdict

**Audit estimate (§3.1, §4.2):** evaluation LOC ~895 (= ~786 judgment block + ~83 branch_version + ~26 dispatch glue). Audit lists handlers: judge_run, list_judgments, compare_runs, suggest_node_edit, get_node_output, list_node_versions, rollback_node. Branch-versioning called out separately at §3.1: `_BRANCH_VERSION_ACTIONS` line range 8070–8152, ~83 LOC.

**Reality (current code, 2026-04-26):**
- `_BRANCH_VERSION_ACTIONS` is at L8835 (audit said L8070–8152 — drift +765 lines from intervening growth).
- Branch-versioning section L8758–8839 (banner + 3 handlers + dispatch dict) = ~82 LOC. Audit estimate solid.
- Phase 4 banner at L9472 ("Phase 4: Eval + iteration hooks").
- `_split_tag_csv` helper L9481.
- 7 action handlers L9485–10182:
  - `_action_judge_run` L9485
  - `_action_list_judgments` L9528
  - `_action_compare_runs` L9578
  - `_action_suggest_node_edit` L9690
  - `_action_get_node_output` L9816
  - `_action_list_node_versions` L9902 (with explanatory comment block at L9876-9881 about rollback semantics)
  - `_action_rollback_node` L10012
- `_JUDGMENT_ACTIONS` dispatch dict L10185 (7 entries).
- `_JUDGMENT_WRITE_ACTIONS` frozenset L10195 (2 entries: judge_run, rollback_node).
- `_dispatch_judgment_action` L10200 (~40 LOC).
- Phase 4 section ends L10241 (immediately before TOOL 3 — Goals banner at L10242).

**Total LOC contiguous Phase 4 block (L9472 → L10241): ~770 LOC.**
**Total LOC branch-versioning block (L8758 → L8839): ~82 LOC.**
**Combined moveable: ~852 LOC** (audit said ~895 — within 5%, slight under).

**Audit was NOT stale on size or content.** Drift only in line numbers (universe_server.py grew between audit-write 2026-04-25 and now). The 7-handler list is current. `_split_tag_csv` (L9481) is a new local helper not in the audit's enumeration but eval-only (single consumer at L9502).

---

## 2. Symbol enumeration (current line ranges)

### 2.1 Branch-versioning block (contiguous L8758–8839)

| Symbol | Line | LOC | Notes |
|---|---|---|---|
| Branch versioning section banner | 8758 | 4 | Comment block |
| `_action_publish_version` | 8764 | ~40 | Imports `workflow.branch_versions.publish_branch_version` and `workflow.daemon_server.get_branch_definition` |
| `_action_get_branch_version` | 8804 | ~14 | |
| `_action_list_branch_versions` | 8818 | ~17 | |
| `_BRANCH_VERSION_ACTIONS` | 8835 | 5 | Dict literal — 3 handlers |

### 2.2 Phase 4 evaluation block (contiguous L9472–10241)

| Symbol | Line | LOC | Notes |
|---|---|---|---|
| Phase 4 banner + design comment | 9472 | 9 | Comment block establishing build → run → judge → edit → rerun loop |
| `_split_tag_csv` | 9481 | 2 | Single internal consumer (`_action_judge_run` L9502) |
| `_action_judge_run` | 9485 | ~43 | Phase 4 write action; calls `_dispatch_judgment_action` ledger glue |
| `_action_list_judgments` | 9528 | ~50 | Read-only |
| `_action_compare_runs` | 9578 | ~112 | Read-only; multi-run JSON diff |
| `_action_suggest_node_edit` | 9690 | ~126 | Read-only; bundles context for chatbot edit |
| `_action_get_node_output` | 9816 | ~86 | Read-only; node-level run output extraction |
| `_action_list_node_versions` | 9902 | ~110 | Includes inline comment block at L9876-9881 about rollback semantics; rollback semantics rationale |
| `_action_rollback_node` | 10012 | ~173 | Phase 4 write action; bumps branch version + emits audit row with `edit_kind="rollback"` |
| `_JUDGMENT_ACTIONS` | 10185 | 9 | Dict literal — 7 handlers |
| `_JUDGMENT_WRITE_ACTIONS` | 10195 | 3 | Frozenset — 2 entries |
| `_dispatch_judgment_action` | 10200 | ~40 | Ledger glue mirroring `_dispatch_run_action` shape |

---

## 3. Cross-references — bidirectional dependency check

### 3.1 Does evaluation.py depend on #9/#10/Step 4 (wiki/status/runs) symbols?

**No.**
- No `_wiki_*` symbol used by any evaluation handler.
- No `get_status` or `_policy_hash` reference.
- No `_RUN_ACTIONS` / `_action_run_*` reference (evaluation operates on runs as data, not by dispatching them).

### 3.2 Does evaluation.py depend on shared #8 helpers?

**Yes:** `_action_compare_runs`, `_action_get_node_output`, `_action_list_node_versions`, `_action_rollback_node` use `_universe_dir`, `_default_universe`, `_base_path` (per import patterns observed in surrounding code).

After #8 lands (already done — 4f98654), evaluation.py imports these from `tinyassets/api/helpers.py`.

### 3.3 Does evaluation.py call into other future submodules?

**`_action_publish_version` imports `workflow.branch_versions.publish_branch_version` and `workflow.daemon_server.get_branch_definition`** (L8765-8766). These are **storage/engine modules**, not API submodules. They stay where they are; evaluation.py imports them. **No circular risk.**

`_action_rollback_node` imports `workflow.daemon_server.get_branch_definition` similarly. Same pattern.

`_dispatch_judgment_action` calls `_append_global_ledger` + `_truncate` (L10229, L10232). These are preamble helpers. **Risk:** if `_append_global_ledger` is in universe_server.py preamble (not yet extracted to helpers.py), evaluation.py needs `from workflow.universe_server import _append_global_ledger, _truncate` — which works but creates a soft back-edge. **Need to verify:** whether `_append_global_ledger` will move to `helpers.py` in a future #8-style extraction OR stays in preamble until full universe_server shim cleanup.

**Recommended verification at extraction time:** `grep -n "_append_global_ledger\|_truncate" tinyassets/api/helpers.py` — if absent, import from `workflow.universe_server` is the back-compat path.

### 3.4 Does evaluation.py share dispatch surface with `extensions()`?

**Yes.** Two dispatch reads in `extensions()` body:
- L4011: `judgment_handler = _JUDGMENT_ACTIONS.get(action)` — Phase 4 dispatch
- L4043: `bv_handler = _BRANCH_VERSION_ACTIONS.get(action)` — branch-versioning dispatch

After Step 5 lands, `extensions()` body needs **two new imports** at top of universe_server.py:
```python
from workflow.api.evaluation import (
    _JUDGMENT_ACTIONS, _JUDGMENT_WRITE_ACTIONS, _dispatch_judgment_action,
    _BRANCH_VERSION_ACTIONS,
)
```

This is **structurally identical** to the Step 4 (`_RUN_ACTIONS`) pattern. **Trivial; not a refactor of `extensions()` body.**

### 3.5 `_action_run_branch_version` placement vs `_BRANCH_VERSION_ACTIONS`

Important distinction:
- `_action_run_branch_version` (L8473) — **Step 4 (runs.py) scope.** Registered in `_RUN_ACTIONS` (L8694). Executes a run against a published version.
- `_BRANCH_VERSION_ACTIONS` (L8835) — **Step 5 (evaluation.py) scope.** Owns publish/get/list version metadata.

The two share semantic territory ("branch versioning") but are functionally distinct: Step 4 owns the runner, Step 5 owns the version metadata. The audit §4.2 puts both in the right places. **Don't conflate** at extraction time.

---

## 4. FastMCP `mcp` instance — inherits #9 decision

Same Pattern A question as #9 §4 / #10 §4 / Step 4 §4. **Inherited from #9.**

evaluation.py does NOT register any `@mcp.tool()` decorator directly (just like runs.py). Public `extensions()` MCP tool is the surface; evaluation.py owns dispatch handlers exposed via `_JUDGMENT_ACTIONS` + `_BRANCH_VERSION_ACTIONS`. `mcp` import is technically not required for evaluation.py.

---

## 5. Test files importing evaluation symbols (and how)

Searched broadly — **no test imports `_JUDGMENT_ACTIONS`, `_BRANCH_VERSION_ACTIONS`, or any `_action_*` evaluation handler directly via `from workflow.universe_server import`.**

Tests touching the evaluation public action names go through the `extensions` MCP tool surface (e.g. `tests/test_publish_version.py:248,257,265,276,287,295` all do `from workflow.universe_server import extensions`).

| Test file | Symbol(s) imported | How |
|---|---|---|
| `tests/test_publish_version.py` | `extensions` | Via MCP tool (~6 imports) |
| `tests/test_rollback.py` | `extensions` | Via MCP tool (presumed; not grep-confirmed inline; same pattern) |
| `tests/test_branch_evaluation_iteration.py` | `extensions` | Via MCP tool |
| `tests/test_branch_versions_rollback_columns.py` | `extensions` (likely) | Via MCP tool |
| `tests/test_run_branch_version.py` | `_action_run_branch_version` (Step 4 scope, NOT here) | Via direct import |

**Strategy:** Audit §7 Strategy 1 (back-compat re-export shim) preserves all imports. After Step 5 lands, `tinyassets/universe_server.py` adds:
```python
# Phase-1 evaluation extraction — back-compat re-exports.
from workflow.api.evaluation import (  # noqa: F401
    _JUDGMENT_ACTIONS, _JUDGMENT_WRITE_ACTIONS, _dispatch_judgment_action,
    _BRANCH_VERSION_ACTIONS,
    _action_judge_run, _action_list_judgments, _action_compare_runs,
    _action_suggest_node_edit, _action_get_node_output,
    _action_list_node_versions, _action_rollback_node,
    _action_publish_version, _action_get_branch_version, _action_list_branch_versions,
    _split_tag_csv,
)
```

**~0 direct test imports require preservation** (vs runs.py's 32). **No test edits required for Step 5.**

This is the cleanest extraction in the audit's 8-step plan from a test-impact standpoint.

---

## 6. What partially-moved (the helpers-already-extracted lesson)

Searched for evidence that any evaluation-scope symbols already shipped to a submodule (e.g. `workflow.api.evaluation`, `workflow.evaluation`, `workflow.judgment`). **None found.**

Adjacent partial moves: only the 5+ helpers in #8 (`_base_path`, etc.) — `_action_compare_runs` and friends already use them; after #8 (already landed) they're `helpers.py` imports.

Note: there IS no `tinyassets/evaluation.py` (storage layer) — unlike Step 4's `tinyassets/runs.py` storage namespace collision. Cleaner namespace.

---

## 7. Total LOC moved estimate

| Block | LOC |
|---|---|
| Branch-versioning block (L8758–8839) | ~82 |
| Phase 4 banner + helpers + handlers (L9472–10241) | ~770 |
| **Total moved out of universe_server.py** | **~852** |
| Back-compat re-export block added to universe_server.py | ~16 |
| **Net reduction in universe_server.py** | **~836** |
| New `tinyassets/api/evaluation.py` size | **~880** (with imports + module docstring) |

**Audit said ~895.** Reality ~852. About 5% under (audit slightly over-estimated).

---

## 8. Risks the audit didn't anticipate

1. **Two non-contiguous source ranges.** Branch-versioning at L8758–8839 is physically separated from Phase 4 block at L9472–10241 by ~630 lines of unrelated code (messaging, scheduler, outcomes, attribution). **Extraction must surgically pick both ranges, skipping** the interleaved sections that go to other future submodules:
   - L8842–8935 messaging (runtime_ops.py future scope)
   - L8936–9127 scheduler (runtime_ops.py)
   - L9128–9281 outcomes (market.py)
   - L9282–9471 attribution (market.py)

2. **`_append_global_ledger` import path uncertainty** (§3.3). If it's still in universe_server.py preamble at Step 5 time, evaluation.py needs `from workflow.universe_server import _append_global_ledger, _truncate`. This is back-edge but not circular (universe_server.py imports evaluation.py via re-export shim AT MODULE END; evaluation.py imports `_append_global_ledger` AT MODULE TOP — order of operations works as long as the re-export is at end-of-file).

   **Recommended verification at extraction time:** check `tinyassets/api/helpers.py` for `_append_global_ledger`. If absent, the back-edge import is the path. Document this as a follow-up cleanup item for a future helpers.py expansion.

3. **`_dispatch_judgment_action` ledger writes** (L10200) call `_append_global_ledger` + `_truncate` — same dependency as #2. Both move with the function.

4. **`_action_publish_version` / `_action_rollback_node` import `workflow.daemon_server`** — that module is the engine-side branch-definition store, NOT the API surface. Stays put. Imports unchanged.

5. **`_action_rollback_node` is the largest handler in evaluation block** (~173 LOC, including the inline comment block at L9876-9881 explaining rollback semantics). If a future task touches rollback semantics, expect merge conflicts.

6. **No test edits required.** This is the cleanest extraction in the 8-step plan from a test-import standpoint. Re-export shim handles the `extensions` tool surface that all current tests go through.

7. **Pre-commit canonical-vs-plugin parity check** — same as previous steps. Run `python packaging/claude-plugin/build_plugin.py`.

8. **Sequencing.** Audit §8 puts Step 5 after Step 4. Step 4 (runs.py) extracts `_action_run_branch_version` which shares the "branch versioning" semantic territory with Step 5's `_BRANCH_VERSION_ACTIONS`. Land Step 4 first to avoid confusion about which action goes where during code review.

9. **`_split_tag_csv` is eval-only** (single consumer at L9502). Moves with the block. Don't accidentally promote to helpers.py.

---

## 9. Concrete Step 5 implementation plan

Estimated wall time: 45-75 min (smaller than Step 4 because zero direct test imports, but two non-contiguous source ranges adds care).

1. **Confirm #8, #9, #10, Step 4 have all landed.**
2. **Confirm `mcp` instance pattern from #9** — inherited; not strictly needed for evaluation.py (no `@mcp.tool` decorator inside).
3. **Verify `_append_global_ledger` location** at extraction time:
   - If in `tinyassets/api/helpers.py`: import from there.
   - If in `tinyassets/universe_server.py`: import via back-edge `from workflow.universe_server import _append_global_ledger, _truncate` (tolerated as long as re-export shim is at module END).
4. **Create `tinyassets/api/evaluation.py`:**
   - Module docstring referencing audit + extraction date + the two non-contiguous source-range list.
   - Imports: `from workflow.api.helpers import _base_path, _default_universe, _universe_dir` + storage layer imports (`workflow.branch_versions`, `workflow.daemon_server`) + ledger imports per §3 verification + std-lib + typing.
   - Move symbols **in this order** (logical not source order — evaluation handlers first, then branch-versioning handlers as a separate section, then dispatch tables):
     1. Phase 4 banner + design comment
     2. `_split_tag_csv` (L9481)
     3. `_action_judge_run` (L9485)
     4. `_action_list_judgments` (L9528)
     5. `_action_compare_runs` (L9578)
     6. `_action_suggest_node_edit` (L9690)
     7. `_action_get_node_output` (L9816)
     8. `_action_list_node_versions` (L9902) — preserve inline comment block L9876-9881
     9. `_action_rollback_node` (L10012)
     10. Branch versioning section banner (L8758)
     11. `_action_publish_version` (L8764)
     12. `_action_get_branch_version` (L8804)
     13. `_action_list_branch_versions` (L8818)
     14. `_BRANCH_VERSION_ACTIONS` (L8835)
     15. `_JUDGMENT_ACTIONS` (L10185)
     16. `_JUDGMENT_WRITE_ACTIONS` (L10195)
     17. `_dispatch_judgment_action` (L10200)
5. **Update `tinyassets/universe_server.py`:**
   - Delete the 2 source ranges in reverse order to avoid line-shift confusion:
     - L9472–10241 (Phase 4 block + dispatch tables)
     - L8758–8839 (branch-versioning block)
   - Add to back-compat shim block at end of file:
     ```python
     from workflow.api.evaluation import (  # noqa: F401
         _JUDGMENT_ACTIONS, _JUDGMENT_WRITE_ACTIONS, _dispatch_judgment_action,
         _BRANCH_VERSION_ACTIONS,
         _action_judge_run, _action_list_judgments, _action_compare_runs,
         _action_suggest_node_edit, _action_get_node_output,
         _action_list_node_versions, _action_rollback_node,
         _action_publish_version, _action_get_branch_version, _action_list_branch_versions,
         _split_tag_csv,
     )
     ```
   - The `extensions()` body's `_JUDGMENT_ACTIONS.get(action)` at L4011 and `_BRANCH_VERSION_ACTIONS.get(action)` at L4043 continue to work via the re-export.
6. **No test edits required.** This is the headline win for Step 5.
7. **Run `python packaging/claude-plugin/build_plugin.py`** to sync plugin runtime mirror.
8. **Verification:**
   - `pytest tests/test_publish_version.py tests/test_rollback.py tests/test_branch_evaluation_iteration.py tests/test_branch_versions_rollback_columns.py -q` → green (covers branch-versioning + judgment surface).
   - `pytest tests/test_run_branch_version.py -q` → green (sanity: Step 4's `_action_run_branch_version` did NOT accidentally move).
   - `pytest -q` → full suite green.
   - `ruff check tinyassets/api/evaluation.py tinyassets/universe_server.py` → clean.
   - **Visual check:** `git diff tinyassets/universe_server.py | grep -c "^-def _action_"` should equal 10 (3 branch-version + 7 judgment handlers). Anything else means an accidental pull.

**Files in eventual Step 5 SHIP handoff:**
- `tinyassets/api/evaluation.py` (NEW, ~880 LOC)
- `tinyassets/universe_server.py` (~836 LOC removed + ~16 re-export added)
- `packaging/claude-plugin/.../tinyassets/api/evaluation.py` (NEW mirror)
- `packaging/claude-plugin/.../tinyassets/universe_server.py` (mirror)

4 files, +896 / -836 LOC net.

---

## 10. Decision asks for the lead

1. **`_append_global_ledger` import path** (§3.3, §8 risk #2) — accept the back-edge `from workflow.universe_server import _append_global_ledger, _truncate` for now, OR pre-extract `_append_global_ledger` into `tinyassets/api/helpers.py` as a tiny prep step before Step 5? Recommendation: accept back-edge for Step 5; promote `_append_global_ledger` to helpers.py during eventual full universe_server shim cleanup (later than Step 8).
2. **Sequencing** — Step 4 (runs.py) lands BEFORE Step 5 to avoid confusion about which action handler goes where. Recommendation: confirmed yes, stick with audit order.
3. **`mcp` instance import** in evaluation.py — strictly not needed (no `@mcp.tool` decorator); recommend omitting consistent with Step 4 recommendation.

---

## 11. Cross-prep summary (#8 + #9 + #10 + Step 4 + Step 5 combined)

After all 5 land:

| Step | New file | Net LOC removed from universe_server.py | Cumulative universe_server.py size |
|---|---|---|---|
| baseline (2026-04-26) | — | — | 14,012 |
| #8 ✅ landed (4f98654) | extends `helpers.py` | ~16 | ~13,996 |
| #9 (in flight) | `wiki.py` | ~1,360 | ~12,636 |
| #10 (queued) | `status.py` | ~422 | ~12,214 |
| Step 4 (queued) | `runs.py` | ~1,385 | ~10,829 |
| Step 5 (this prep) | `evaluation.py` | ~836 | **~9,993** |
| **Total** | 3 new + 1 extended | ~4,019 | **~9,993** |

**universe_server.py crosses below 10,000 lines** after Step 5 (from baseline 14,012 = ~29% reduction). Larger reductions still ahead in audit steps 6–8 (`runtime_ops.py` ~444, `market.py` ~1,813, `branches.py` ~3,282).

All 5 steps are pure refactor — no behavior change. Step 5 is **the only step requiring zero direct test import preservation**, making it the cleanest extraction in the 8-step plan.
