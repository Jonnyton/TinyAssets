---
title: Task #?? prep — tinyassets/api/runs.py extraction scope
date: 2026-04-26
author: navigator
status: pre-flight scoping (no edits yet)
companion: docs/audits/2026-04-25-universe-server-decomposition.md §4.2 (`runs.py`), §8 step 4
target_task: Decomp audit Step 4 — Extract tinyassets/api/runs.py
gates_on: #8 (universe_helpers) ships first; #9 (wiki.py) and #10 (status.py) land order independent of #?? but #?? assumes the `mcp` instance pattern picked in #9.
---

# Step 4 (`runs.py`) pre-flight scope

Read-only scope for extracting the run-execution subsystem from `tinyassets/universe_server.py` into a new `tinyassets/api/runs.py`. Same freshness-check protocol as #9/#10 prep — verify audit prescription against current code before trusting the spec.

---

## 1. Audit-vs-reality verdict

**Audit estimate (§3.1, §4.2):** runs LOC ~1,311, including `_RUN_ACTIONS` (~1,111), cross-run queries via `_action_query_runs` (~201). Audit lists handlers: run_branch, get_run, list_runs, stream_run, cancel_run, resume_run, wait_for_run, get_run_output, estimate_run_cost.

**Reality (current code, 2026-04-26):**
- Phase 3 banner at L7015 ("Phase 3: Graph Runner — execute a BranchDefinition").
- Run helper functions L7026–7291 (mermaid + failure taxonomy + classification).
- `_action_run_branch` at L7294.
- 9 of the audit's 10 named handlers present, contiguous L7294–7897.
- `_PROJECT_MEMORY_*` constants + handlers L7983–8050 (NOT runs scope per audit — goes to `runtime_ops.py`).
- `_action_query_runs` at L8053.
- `_action_run_routing_evidence` at L8112 (audit calls this out as runs.py-scope despite being an `extensions get_routing_evidence` action handler).
- `_action_get_memory_scope_status` at L8144 (NOT in audit's runs.py list — but registered in `_RUN_ACTIONS`; verdict below).
- `_INSPECT_DRY_ACTIONS` block L8223–8360 (NOT runs scope — goes to `runtime_ops.py`).
- `_ESCROW_ACTIONS` block L8363–8472 (NOT runs scope — goes to `market.py`).
- `_action_run_branch_version` at L8473 (IS runs scope — registered in `_RUN_ACTIONS` at L8694).
- `_action_rollback_merge` at L8589 (IS runs scope — registered in `_RUN_ACTIONS`).
- `_action_get_rollback_history` at L8654 (IS runs scope — registered in `_RUN_ACTIONS`).
- `_RUN_ACTIONS` dispatch table L8692.
- `_RUN_WRITE_ACTIONS` frozenset L8710.
- `_dispatch_run_action` L8716 (extends ledger + write tracking).
- `_action_publish_version`/`_action_get_branch_version`/`_action_list_branch_versions` L8764–8834 (NOT runs scope per audit — `_BRANCH_VERSION_ACTIONS` goes to `evaluation.py` per §4.2 "judgment, suggest_node_edit, rollback, versioning"; reality: registered as `_BRANCH_VERSION_ACTIONS` at L8835, separate from `_RUN_ACTIONS`).

**Total LOC for runs.py extraction (non-contiguous):**
- Helpers + handlers L7026–7897 = 871 LOC
- `_action_query_runs` + `_action_run_routing_evidence` L8053–8138 = 86 LOC
- `_action_get_memory_scope_status` L8144–~8222 = ~80 LOC (verdict pending — see §3.4)
- `_action_run_branch_version` L8473–8588 = ~115 LOC
- `_action_rollback_merge` + `_action_get_rollback_history` L8589–8689 = ~100 LOC
- `_RUN_ACTIONS` + `_RUN_WRITE_ACTIONS` + `_dispatch_run_action` L8692–8758 = ~67 LOC

**Net moveable: ~1,320 LOC.** Audit estimate (~1,311) is within 1% — solid sizing.

**Audit drift to flag:**
1. The 9 handlers run-scope **PLUS** the 6 added since the audit (`run_branch_version`, `rollback_merge`, `get_rollback_history`, `get_routing_evidence`, `query_runs`, `get_memory_scope_status`) all registered in `_RUN_ACTIONS`. The audit's "9 handlers" framing is incomplete — current `_RUN_ACTIONS` has **15** entries.
2. The runs section is **NOT contiguous** in current source. Escrow, branch-versioning, dispatch helpers, and dry-inspect handlers are physically interleaved between L7898 and L8758. Extraction must skip those.

---

## 2. Symbol enumeration (current line ranges)

### 2.1 Module-level constants
| Symbol | Line | Notes |
|---|---|---|
| `_RUNS_RECOVERY_DONE` | 7087 | Module-level state guard. Single-process flag for `_ensure_runs_recovery`. Moves to runs.py — single consumer. |
| `_FAILURE_TAXONOMY` | 7106 | Lazy-init list, mutated by `_build_failure_taxonomy`. Moves to runs.py. |

### 2.2 Run helpers (all stay together — single-purpose: run execution + failure classification)
| Helper | Line | Used by | Move target |
|---|---|---|---|
| `_run_mermaid_from_events` | 7026 | `_action_get_run`, `_action_list_runs`, `_action_stream_run`, `_action_wait_for_run` | **runs.py** |
| `_ensure_runs_recovery` | 7090 | `_action_run_branch`, `_action_run_branch_version` | **runs.py** |
| `_build_failure_taxonomy` | 7109 | `_classify_run_error` | **runs.py** |
| `_actionable_by` | 7134 | `_classify_run_error`, `_classify_run_outcome_error` consumers | **runs.py** |
| `_failure_payload` | 7151 | `_classify_run_error` | **runs.py** |
| `_classify_run_error` | 7164 | `_action_run_branch`, `_action_run_branch_version` | **runs.py** (also imported by `tests/test_run_branch_failure_taxonomy.py:9` — top-level import) |
| `_classify_run_outcome_error` | 7209 | `_action_run_branch`, `_action_get_run`, `_action_get_run_output` | **runs.py** (also imported by test above) |

### 2.3 Run action handlers (registered in `_RUN_ACTIONS`)
| Handler | Line | LOC | Notes |
|---|---|---|---|
| `_action_run_branch` | 7294 | ~236 | The primary entrypoint; calls `compile_branch`, persists run rows, recovers in-flight runs |
| `_action_get_run` | 7530 | ~16 | |
| `_action_list_runs` | 7546 | ~48 | |
| `_action_stream_run` | 7594 | ~52 | |
| `_action_wait_for_run` | 7646 | ~82 | |
| `_action_cancel_run` | 7728 | ~32 | |
| `_action_get_run_output` | 7760 | ~58 | |
| `_action_resume_run` | 7818 | ~66 | |
| `_action_estimate_run_cost` | 7884 | ~99 | Ends ~L7982 (immediately before `_action_project_memory_get` at L7983) |
| `_action_query_runs` | 8053 | ~59 | Cross-run query primitive |
| `_action_run_routing_evidence` | 8112 | ~26 | Note: this is registered in `_RUN_ACTIONS` as `get_routing_evidence`, NOT in `extensions()` group as the name suggests. Audit §4.2 places it in runs.py — confirmed correct. |
| `_action_get_memory_scope_status` | 8144 | ~79 | See §3.4 — verdict goes to runs.py with caveat. |
| `_action_run_branch_version` | 8473 | ~116 | Companion to `_action_run_branch` for the branch-version surface. |
| `_action_rollback_merge` | 8589 | ~65 | Surgical rollback (Task #22 Phase B per L3787 comment). |
| `_action_get_rollback_history` | 8654 | ~38 | |

### 2.4 Dispatch table + glue
| Symbol | Line | LOC |
|---|---|---|
| `_RUN_ACTIONS` | 8692 | 17 (dict literal) |
| `_RUN_WRITE_ACTIONS` | 8710 | 4 (frozenset) |
| `_dispatch_run_action` | 8716 | ~43 |

---

## 3. Cross-references — bidirectional dependency check

### 3.1 Does runs.py depend on #9 (wiki.py) or #10 (status.py) symbols?

**No.** Verified by grep:
- No `_wiki_*` symbol imported by run handlers.
- `_action_run_branch` does NOT call `wiki()` or `get_status`.
- `_classify_run_error` does NOT call `_policy_hash`.

### 3.2 Does runs.py depend on `extensions()` (branches.py future scope) symbols?

**Yes — via the dispatch routing in `extensions()`:**
- `extensions()` body at L3992 calls `_RUN_ACTIONS.get(action)` — meaning the public `extensions()` MCP tool dispatches into run actions. After runs.py extracts, the dispatch table import path changes.
- `extensions()` at L4026 dispatches into `_PROJECT_MEMORY_ACTIONS` (NOT runs scope).
- `extensions()` at L4108 dispatches into `_INSPECT_DRY_ACTIONS` (NOT runs scope).

**Implication:** `extensions()` (which lives in branches.py future scope per audit step 8) must `from workflow.api.runs import _RUN_ACTIONS, _dispatch_run_action`. This is fine as long as `extensions()` stays in `universe_server.py` (or moves to `branches.py`) AFTER runs.py extracts. Since the audit sequencing puts branches.py at step 8 (last), runs.py extraction goes first cleanly — the existing inline `_RUN_ACTIONS.get(action)` becomes a `from workflow.api.runs import _RUN_ACTIONS` at top of universe_server.py.

### 3.3 Does runs.py depend on shared #8 helpers?

**Yes:** `_action_run_branch` and friends call `_universe_dir`, `_default_universe`, `_base_path`, `_read_json`, `_read_text` — all extracted in #8 to `tinyassets/api/helpers.py`. After #8 lands, runs.py imports these.

**Indirect via run helpers:** `_classify_run_error` calls `_classify_run_outcome_error` and `_actionable_by` — all wholly internal to runs.py.

### 3.4 `_action_get_memory_scope_status` placement verdict

**Audit silent on this handler.** It was added after the audit (registered in `_RUN_ACTIONS` at L8705). Question: is it run-scope or memory-scope?

- Function lives in its own commented section ("get_memory_scope_status — self-auditing primitive §4.1") at L8139–8222.
- Logically: this audits the **memory scope router** (`workflow.retrieval.router`) — it's a status/observability primitive about the retrieval layer, not about runs.
- Practically: it's registered in `_RUN_ACTIONS`, dispatched via `extensions get_memory_scope_status`, and lives next to runs because `extensions()` doesn't have a separate router-tooling group.

**Recommendation:** Move with `_RUN_ACTIONS` to runs.py for now (preserves the dispatch table location). It can graduate to a `tinyassets/api/retrieval.py` or `tinyassets/api/router_status.py` in a later refactor when a tier-gated router-tooling submodule is justified. **No test edits required either way** — it's not currently in the import-fan-in below.

### 3.5 Sequencing constraint on `extensions()` body

`extensions()` body L3992/L4026/L4108 reads three dispatch tables: `_RUN_ACTIONS`, `_PROJECT_MEMORY_ACTIONS`, `_INSPECT_DRY_ACTIONS`. After runs.py extracts `_RUN_ACTIONS`, the `extensions()` body needs:

```python
from workflow.api.runs import _RUN_ACTIONS, _dispatch_run_action, _RUN_WRITE_ACTIONS
```

This happens at universe_server.py top (one-shot import). `_PROJECT_MEMORY_ACTIONS` and `_INSPECT_DRY_ACTIONS` stay inline until `runtime_ops.py` extracts (audit step 6).

**No circular import risk** — runs.py does NOT import from `workflow.universe_server` at module load time (only the back-compat shim re-exports the other direction).

---

## 4. FastMCP `mcp` instance — inherits #9 decision

Same Pattern A question as #9 §4 / #10 §4. If #9 picked Pattern A1 (`workflow.mcp_setup` leaf module), runs.py imports `mcp` from there. If #9 picked A2 (`from workflow.universe_server import mcp` shim), runs.py does the same.

**No new decision needed for #?? — inherits.**

**Note:** runs.py does NOT register any `@mcp.tool()` decorator directly. The `extensions()` MCP tool is the public surface; runs.py only owns dispatch handlers it exposes via `_RUN_ACTIONS`. So the `mcp` import is technically not strictly required for runs.py — the audit's Pattern A circular-import concern is moot here. Confirm by checking: no `@mcp` use inside any of the L7026–8758 symbols. Verified — none.

---

## 5. Test files importing runs symbols (and how)

All via `from workflow.universe_server import ...` — none via `workflow.api.runs`:

| Test file | Symbol(s) imported | Count |
|---|---|---|
| `tests/test_canonical_branch_mcp.py:115,126` | `_RUN_ACTIONS` (also imports `_GOAL_ACTIONS` in same statement) | 2 |
| `tests/test_dry_inspect_node.py` | `_action_dry_inspect_node`, `_action_dry_inspect_patch` | 12 (NOT runs.py — these are runtime_ops.py future scope; ignore for #??) |
| `tests/test_project_memory.py` | `_action_project_memory_get/set/list` | 12 (NOT runs.py — runtime_ops.py future scope) |
| `tests/test_query_runs.py` | `_action_query_runs` | 4 |
| `tests/test_run_branch_failure_taxonomy.py:9` | `_classify_run_error, _classify_run_outcome_error` | 1 (top-level) + 3 inline `_action_run_branch` imports |
| `tests/test_run_branch_version.py` | `_RUN_ACTIONS`, `_action_run_branch_version` | ~12 |

**Strategy:** Audit §7 Strategy 1 (back-compat re-export shim) preserves all imports. After #?? lands, `tinyassets/universe_server.py` adds:
```python
# Phase-1 runs extraction — back-compat re-exports for tests.
from workflow.api.runs import (  # noqa: F401
    _RUN_ACTIONS, _RUN_WRITE_ACTIONS, _dispatch_run_action,
    _action_run_branch, _action_run_branch_version,
    _action_get_run, _action_list_runs, _action_stream_run, _action_wait_for_run,
    _action_cancel_run, _action_get_run_output, _action_resume_run,
    _action_estimate_run_cost,
    _action_query_runs, _action_run_routing_evidence,
    _action_get_memory_scope_status,
    _action_rollback_merge, _action_get_rollback_history,
    _classify_run_error, _classify_run_outcome_error,
    _actionable_by, _failure_payload,
    _ensure_runs_recovery, _run_mermaid_from_events,
    _build_failure_taxonomy, _FAILURE_TAXONOMY,
)
```

**~32 test imports across 3 files** (`test_canonical_branch_mcp`, `test_query_runs`, `test_run_branch_failure_taxonomy`, `test_run_branch_version`) continue to work; **no test edits required for #??**.

---

## 6. What partially-moved (the helpers-already-extracted lesson)

Searched for evidence that any run-scope symbols already shipped to a submodule (e.g. `workflow.api.runs`, `workflow.runs`). **None found in the API layer.**

Note: there IS a `tinyassets/runs.py` (not `tinyassets/api/runs.py`) — that's the **storage/persistence layer** for run rows (the `runs.recover_in_flight_runs`, `runs.query_runs`, etc. that handlers import). The new file lives at `tinyassets/api/runs.py` — a different namespace. Confirm no name confusion at extraction time. Suggest the dev double-check the import statements after move (`from workflow.runs import ...` continues to work; `from workflow.api.runs import ...` is the new path).

The only adjacent partial moves are the 5 helpers in #8 (`_base_path`, etc.) — `_action_run_branch` already uses them; after #8 lands they're `helpers.py` imports.

---

## 7. Total LOC moved estimate

| Block | LOC |
|---|---|
| Phase 3 banner + helpers (L7015–7291) | ~277 |
| Primary run handlers (L7294–7897) | ~604 |
| Cross-run + routing + memory-scope handlers (L8053–8222, partial) | ~245 |
| Branch-version + rollback handlers (L8473–8689) | ~217 |
| `_RUN_ACTIONS` + dispatch glue (L8692–8758) | ~67 |
| **Total moved out of universe_server.py** | **~1,410** |
| Back-compat re-export block added to universe_server.py | ~25 |
| **Net reduction in universe_server.py** | **~1,385** |
| New `tinyassets/api/runs.py` size | **~1,460** (with imports + module docstring) |

**Audit said ~1,311.** Reality ~1,410. About 7% over due to the 6 handlers added since the audit (`run_branch_version`, `rollback_merge`, `get_rollback_history`, `get_memory_scope_status`, plus richer `_classify_run_outcome_error` taxonomy from BUG-029 fix in 0f5ccc4).

---

## 8. Risks the audit didn't anticipate

1. **Non-contiguous source range.** Unlike #9 (wiki: contiguous L12036–L13543) and #10 (status: contiguous L13546–L13994), runs.py extraction must surgically pick from L7015–L8758, **skipping**:
   - `_PROJECT_MEMORY_*` L7983–8050 (runtime_ops.py future scope)
   - `_INSPECT_DRY_*` L8223–8360 (runtime_ops.py)
   - `_ESCROW_*` L8363–8472 (market.py)
   - `_action_publish_version`/`get_branch_version`/`list_branch_versions` L8764+ (audit §4.2 puts these in evaluation.py with `_BRANCH_VERSION_ACTIONS`)

   **Higher chance of accidentally pulling adjacent code.** Recommend dev does a dry `git diff` review before commit, line-by-line, against this prep doc's enumeration.

2. **`_action_get_memory_scope_status` placement is judgment call** (§3.4). Default to runs.py with the dispatch table; revisit when retrieval-tooling submodule is justified.

3. **`_action_run_routing_evidence`** lives in runs.py per audit §4.2 even though the action name suggests "extensions" surface. This is a router-evidence primitive, not a routing decision — name is misleading. Confirm with code: registered in `_RUN_ACTIONS` at L8704 as `"get_routing_evidence"`. Audit assignment correct.

4. **`_dispatch_run_action` ledger writes** (L8716) call `from workflow.ledger import ...` (or similar — TODO confirm at extraction time). This module-level dependency moves cleanly with the function — no circular risk.

5. **`extensions()` body at L3992/4026/4108** dispatches into 3 tables. After runs.py extracts `_RUN_ACTIONS` only (the other two stay), the `extensions()` body in universe_server.py needs **one new import line** at top of file. **Trivial; not a refactor of `extensions()` body.**

6. **`tinyassets/runs.py` (storage layer) name collision.** New `tinyassets/api/runs.py` is a sibling namespace, not a duplicate. Inside the new file, imports stay as `from workflow.runs import recover_in_flight_runs, query_runs, ...` (storage layer). No rename needed. Just confirm no test or script does `from workflow.api.runs import recover_in_flight_runs` (should be `from workflow.runs`).

7. **Pre-commit canonical-vs-plugin parity check** — same as #9/#10. Run `python packaging/claude-plugin/build_plugin.py`.

8. **In-flight Tasks** — TaskList shows #8 SHIP gate in-progress, #9 in-progress, #10 pending. **Step 4 (#??) MUST land AFTER all three.** If #??/runs.py dispatches concurrently with #9 (wiki.py), no file-level conflict (different sections), but the back-compat shim block in universe_server.py becomes shared edit territory. Recommend strict sequencing: #8 → #9 → #10 → #??.

9. **`_action_run_branch` is the largest handler in the codebase** (~236 LOC). If a future task touches it (e.g., adds a new failure taxonomy entry, like the BUG-029 fix did), expect merge conflicts on this function. Coordinate with anyone editing run failure semantics before claiming #??.

---

## 9. Concrete Step 4 implementation plan

Estimated wall time: 75-105 min (larger than #9 because of non-contiguous source + 32 test-import surface, but no test edits required).

1. **Confirm #8, #9, #10 have all landed.**
2. **Confirm `mcp` instance pattern from #9** — runs.py doesn't strictly need it (no `@mcp.tool` decorator inside), but pick a pattern for the module header consistency anyway.
3. **Create `tinyassets/api/runs.py`:**
   - Module docstring referencing audit + extraction date + the non-contiguous source-range list.
   - Imports: `from workflow.api.helpers import _base_path, _default_universe, _universe_dir, _read_json, _read_text` (the 5 it actually uses) + `from workflow.runs import recover_in_flight_runs, query_runs, _VALID_AGGREGATES` (+ whatever else `_action_query_runs` etc. import) + std-lib + typing.
   - Move symbols **in this order** (matching source order to minimize diff confusion):
     1. `_run_mermaid_from_events` (L7026)
     2. `_RUNS_RECOVERY_DONE` + `_ensure_runs_recovery` (L7087, L7090)
     3. `_FAILURE_TAXONOMY` + `_build_failure_taxonomy` (L7106, L7109)
     4. `_actionable_by` (L7134)
     5. `_failure_payload` (L7151)
     6. `_classify_run_error` (L7164)
     7. `_classify_run_outcome_error` (L7209)
     8. `_action_run_branch` (L7294)
     9. `_action_get_run` through `_action_estimate_run_cost` (L7530–L7982)
     10. `_action_query_runs` + `_action_run_routing_evidence` (L8053, L8112)
     11. `_action_get_memory_scope_status` (L8144) — with section comment preserved
     12. `_action_run_branch_version` (L8473)
     13. `_action_rollback_merge` + `_action_get_rollback_history` (L8589, L8654)
     14. `_RUN_ACTIONS` + `_RUN_WRITE_ACTIONS` + `_dispatch_run_action` (L8692, L8710, L8716)
4. **Update `tinyassets/universe_server.py`:**
   - Delete the 5 source ranges enumerated in §8 risk #1 (in reverse order to avoid line-shift confusion):
     - L8692–8758 (dispatch glue)
     - L8589–8689 (rollback handlers)
     - L8473–8588 (branch_version handler)
     - L8144–8222 (memory_scope_status, ~79 LOC)
     - L8112–8138 (routing_evidence)
     - L8053–8111 (query_runs)
     - L7026–7982 (Phase 3 banner + helpers + 9 primary handlers)
   - Add to top of file (after existing imports):
     ```python
     # Phase-1 runs extraction — back-compat re-exports for tests + dispatch.
     from workflow.api.runs import (  # noqa: F401
         _RUN_ACTIONS, _RUN_WRITE_ACTIONS, _dispatch_run_action,
         _action_run_branch, _action_run_branch_version,
         _action_get_run, _action_list_runs, _action_stream_run, _action_wait_for_run,
         _action_cancel_run, _action_get_run_output, _action_resume_run,
         _action_estimate_run_cost,
         _action_query_runs, _action_run_routing_evidence,
         _action_get_memory_scope_status,
         _action_rollback_merge, _action_get_rollback_history,
         _classify_run_error, _classify_run_outcome_error,
         _actionable_by, _failure_payload,
         _ensure_runs_recovery, _run_mermaid_from_events,
         _build_failure_taxonomy, _FAILURE_TAXONOMY,
     )
     ```
   - The `extensions()` body's `_RUN_ACTIONS.get(action)` at L3992 (and `_dispatch_run_action` if used inline) continues to work via the re-export.
5. **No test edits required** — re-export shim preserves the existing import paths.
6. **Run `python packaging/claude-plugin/build_plugin.py`** to sync plugin runtime mirror.
7. **Verification:**
   - `pytest tests/test_run_branch_failure_taxonomy.py tests/test_query_runs.py tests/test_canonical_branch_mcp.py tests/test_run_branch_version.py -q` → green.
   - `pytest tests/test_dry_inspect_node.py tests/test_project_memory.py -q` → green (these touch sibling sections that did NOT move; sanity check no accidental pulls).
   - `pytest -q` → full suite green.
   - `ruff check tinyassets/api/runs.py tinyassets/universe_server.py` → clean.
   - **Visual check:** `git diff tinyassets/universe_server.py | grep -c "^-def _action_"` should equal 15 (the 15 handlers moved). Anything else means an accidental pull.

**Files in eventual #?? SHIP handoff:**
- `tinyassets/api/runs.py` (NEW, ~1,460 LOC)
- `tinyassets/universe_server.py` (~1,385 LOC removed + ~25 re-export added)
- `packaging/claude-plugin/.../tinyassets/api/runs.py` (NEW mirror)
- `packaging/claude-plugin/.../tinyassets/universe_server.py` (mirror)

4 files, +1,485 / -1,385 LOC net.

---

## 10. Decision asks for the lead

1. **`_action_get_memory_scope_status` placement** (§3.4) — runs.py for now, or split immediately into a `tinyassets/api/router_status.py`? Recommendation: runs.py for now; revisit with audit step 6 (runtime_ops.py) when `_PROJECT_MEMORY_ACTIONS` move out together.
2. **Sequencing** — strict #8 → #9 → #10 → Step 4 → audit step 5+? Recommendation: yes, stick with audit's `wiki → status → runs → evaluation → runtime_ops → market → branches` order. Each step is a clean refactor with a back-compat shim; running them concurrently risks merge conflicts on the shim block.
3. **`mcp` instance import** in runs.py — strictly not needed (no `@mcp.tool` decorator), but pick a convention for module-header parity with #9/#10. Recommendation: omit the `mcp` import in runs.py since unused; audit it on next pass.

---

## 11. Cross-prep summary (#8 + #9 + #10 + Step 4 combined)

After all 4 land:

| Step | New file | Net LOC removed from universe_server.py | Cumulative universe_server.py size |
|---|---|---|---|
| baseline (2026-04-26) | — | — | 14,012 |
| #8 | extends `helpers.py` | ~16 | ~13,996 |
| #9 | `wiki.py` | ~1,360 | ~12,636 |
| #10 | `status.py` | ~422 | ~12,214 |
| Step 4 | `runs.py` | ~1,385 | ~10,829 |
| **Total** | 2 new + 1 extended | ~3,183 | ~10,829 |

universe_server.py shrinks by **~23%** after the 4 steps. Larger reductions still ahead in audit steps 5–8 (`evaluation.py` ~895, `runtime_ops.py` ~444, `market.py` ~1,813, `branches.py` ~3,282 LOC).

All 4 steps are pure refactor — no behavior change, no test edits required (back-compat shim preserves existing test imports).
