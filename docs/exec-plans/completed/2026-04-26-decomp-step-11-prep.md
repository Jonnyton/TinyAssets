---
title: Step 11 prep — tinyassets/api/extensions.py extraction scope
date: 2026-04-26
author: navigator
status: pre-flight scoping (no edits yet)
companion: docs/audits/2026-04-25-universe-server-decomposition.md (audit's "100-LOC routing shell" target — Steps 9+10+11 are post-original-8-step extension); docs/exec-plans/completed/2026-04-26-decomp-step-{9,10}-prep.md
target_task: Decomp post-Step-10 — Extract tinyassets/api/extensions.py (the `extensions()` MCP tool body + standalone-node infrastructure: NodeRegistration class + `_load_nodes`/`_save_nodes` + `_ext_*` handlers). FINAL extraction in the planned decomposition; lands the audit's "~100-LOC routing shell" target.
gates_on: Steps 8 + 9 + 10 MUST land first. Step 11 depends on Step 9 (universe.py) for the Pattern A2 pattern proof, and on Steps 4-8 for the dispatch-table extractions that `extensions()` consumes.
---

# Step 11 (`extensions.py`) pre-flight scope

Read-only scope for extracting the `extensions()` MCP tool surface from `tinyassets/universe_server.py` into a new `tinyassets/api/extensions.py`. **Second-largest extraction** by LOC after universe.py (~786 moveable LOC); **the most cross-tool-coupled** (extensions() body dispatches into 11 dispatch tables from Steps 4-8). Same freshness-check protocol as Steps 1-10 prep.

This step is NOT in the original 8-step audit plan. Per Step 10 prep §6.4 + §9.2: lead approves Step 11 if going for the audit's "~100-LOC routing shell" target. Final residual after Step 11: **~1,300 LOC** — still ~13× the audit's 100-LOC target but materially closer than today's 7,778. The audit's literal 100-LOC target requires "Step 11+ retarget sweep" of 150-200 test imports across the codebase — recommend deferring that as a separate scope decision (see §9.7).

---

## 1. Audit-vs-reality verdict

**Audit estimate (§9 step 8 + §10 future):** Audit framed the "~100-LOC routing shell" target. After Step 8, the audit assumed residual would be ~100 LOC + preamble + extensions wrappers + 6 wrapper preservations. The audit did NOT enumerate `extensions.py` as a separate step — Step 9 prep §4 + Step 10 prep §6.4 surfaced it as the gap.

**Reality (current code, 2026-04-26 post-Step-7, pre-Steps-8/9/10):**

| Block | Banner / Section | Line range | LOC (est.) |
|---|---|---|---|
| TOOL 2 banner | "TOOL 2 — Extensions (node registration system)" L3700 | L3700-L3702 | ~3 |
| `NodeRegistration` dataclass | (no banner) | L3705-L3730 | ~26 |
| `STANDALONE_NODES_BRANCH_ID` constant + docstring | (no banner) | L3733-L3735 | ~3 |
| `_nodes_path` | (no banner) | L3738-L3740 | ~3 |
| `_ensure_standalone_branch` | (no banner) | L3743-L3789 | ~47 |
| `_load_nodes`, `_save_nodes` | (no banner) | L3791-L3818 | ~28 |
| `VALID_PHASES`, `ALLOWED_DEPENDENCIES` constants | (no banner) | L3821-L3830 | ~10 |
| `@mcp.tool() extensions()` body | (no banner) | L3833-L4350 | ~518 |
| `_ext_register`, `_ext_list`, `_ext_inspect`, `_ext_manage` | (no banner) | L4353-L4489 | ~137 |
| **Total moveable** | | | **~775** |

**Total moveable: ~775 LOC.** Smaller than universe.py (~3,075) but materially larger than engine_helpers.py (~336). Second-largest API submodule extraction.

**Important narrowing:** The `extensions()` body is purely a **dispatch shim** that funnels kwargs into 11 dispatch tables already extracted in Steps 4-8:
- `_BRANCH_ACTIONS` + `_BRANCH_WRITE_ACTIONS` (Step 8 → branches.py).
- `_RUN_ACTIONS` (Step 4 → runs.py).
- `_JUDGMENT_ACTIONS` (Step 5 → evaluation.py).
- `_PROJECT_MEMORY_ACTIONS` + `_PROJECT_MEMORY_WRITE_ACTIONS` (Step 6 → runtime_ops.py).
- `_BRANCH_VERSION_ACTIONS` (Step 5 → evaluation.py).
- `_MESSAGING_ACTIONS` (Step 6 → runtime_ops.py).
- `_ESCROW_ACTIONS` (Step 7 → market.py).
- `_GATE_EVENT_ACTIONS` (Step 7 → market.py).
- `_INSPECT_DRY_ACTIONS` (Step 6 → runtime_ops.py).
- `_SCHEDULER_ACTIONS` (Step 6 → runtime_ops.py).
- `_OUTCOME_ACTIONS` (Step 7 → market.py).
- `_ATTRIBUTION_ACTIONS` (Step 7 → market.py).

After Step 11, extensions.py becomes a **pure routing module** that imports those 12 dispatch tables from their respective api/ submodules and dispatches based on `action`. Net effect: no logic moves, just the dispatch glue.

---

## 2. Symbol enumeration (current line ranges)

### 2.1 TOOL 2 banner + standalone-node infrastructure (L3700-L3830)

| Symbol | Line | LOC | Notes |
|---|---|---|---|
| TOOL 2 banner | 3700 | ~3 | "TOOL 2 — Extensions (node registration system)" |
| `NodeRegistration` dataclass | 3705 | ~26 | `@dataclass` for individually registered nodes. **NOT test-imported.** |
| `STANDALONE_NODES_BRANCH_ID` | 3733 | ~3 | Constant + docstring. **Test-imported in 1 file** (`test_node_registry_migration.py`). |
| `_nodes_path` | 3738 | ~3 | Legacy JSON registry path resolver. |
| `_ensure_standalone_branch` | 3743 | ~47 | Migration logic from legacy JSON to SQLite-backed branch. |
| `_load_nodes`, `_save_nodes` | 3791 | ~28 | Standalone-node SQLite I/O. **2 test-patch sites** (mock.patch on `_load_nodes` / `_save_nodes`). |
| `VALID_PHASES`, `ALLOWED_DEPENDENCIES` | 3821 | ~10 | Validation constants. **Test-imported in 1-2 files.** |

Total: ~120 LOC.

### 2.2 `@mcp.tool() extensions()` body (L3833-L4350)

| Block | Line | LOC | Notes |
|---|---|---|---|
| `@mcp.tool(...)` decorator | 3833 | ~12 | title="Graph Extensions", tags + ToolAnnotations. |
| `def extensions(...)` signature | 3844 | ~105 | **80+ keyword args** — the largest signature in the entire codebase. |
| Docstring | 3950 | ~140 | Action-group reference for every extensions verb. |
| Body L4080-L4350 | (no banner) | ~270 | 11-way dispatch into Step-4-8 tables. |

Total: ~518 LOC. **First extraction with `@mcp.tool()` decorator on an 80+ arg signature** — Pattern A2 wrapper preservation cost is ~120 LOC (decorator + signature + delegation), the largest of any Pattern A2 wrapper so far.

### 2.3 Standalone-node action handlers (L4353-L4489)

| Symbol | Line | LOC | Notes |
|---|---|---|---|
| `_ext_register` | 4353 | ~67 | Standalone-node registration with dependency validation + dangerous-pattern guard. |
| `_ext_list` | 4422 | ~24 | List standalone nodes with filters. |
| `_ext_inspect` | 4448 | ~9 | Inspect a standalone node by id. |
| `_ext_manage` | 4458 | ~33 | approve / disable / enable / remove on a standalone node. |

Total: ~137 LOC. These are called from `extensions()` body L4080-L4090 area (the `if action == "register"` / etc. branches). After Step 11, they move with extensions.py.

---

## 3. Cross-references — bidirectional dependency check

### 3.1 Does extensions.py depend on Steps 1-10 modules?

**Yes — the heaviest cross-module dependency surface of any extraction.** Lazy-imports needed for ~12 dispatch tables:

| Dispatch table | Source module | Used at line(s) in extensions() |
|---|---|---|
| `_BRANCH_ACTIONS`, `_BRANCH_WRITE_ACTIONS`, `_dispatch_branch_action` | `workflow.api.branches` (Step 8) | L4123-L4125 |
| `_RUN_ACTIONS`, `_dispatch_run_action` | `workflow.api.runs` (Step 4) | L4148-L4150 |
| `_JUDGMENT_ACTIONS`, `_dispatch_judgment_action` | `workflow.api.evaluation` (Step 5) | L4167-L4171 |
| `_PROJECT_MEMORY_ACTIONS`, `_PROJECT_MEMORY_WRITE_ACTIONS` | `workflow.api.runtime_ops` (Step 6) | L4182-L4196 |
| `_BRANCH_VERSION_ACTIONS` | `workflow.api.evaluation` (Step 5) | L4199-L4209 |
| `_MESSAGING_ACTIONS` | `workflow.api.runtime_ops` (Step 6) | L4212-L4226 |
| `_ESCROW_ACTIONS` | `workflow.api.market` (Step 7) | L4229-L4240 |
| `_GATE_EVENT_ACTIONS` | `workflow.api.market` (Step 7) | L4243-L4261 |
| `_INSPECT_DRY_ACTIONS` | `workflow.api.runtime_ops` (Step 6) | L4264-L4272 |
| `_SCHEDULER_ACTIONS` | `workflow.api.runtime_ops` (Step 6) | L4275-L4289 |
| `_OUTCOME_ACTIONS` | `workflow.api.market` (Step 7) | L4292-L4305 |
| `_ATTRIBUTION_ACTIONS` | `workflow.api.market` (Step 7) | L4308-L4318 |

**Plus:**
- `_append_global_ledger` (engine_helpers.py after Step 10, currently in Step-8 branches.py range L4561) — used at L4189 for project_memory writes.
- `_current_actor` (engine_helpers.py after Step 10) — used at L4316 for attribution_kwargs.

**Strategy:** **Top-of-module imports** (not lazy), since extensions.py becomes a leaf-only routing module:
```python
from workflow.api.branches import _BRANCH_ACTIONS, _BRANCH_WRITE_ACTIONS, _dispatch_branch_action
from workflow.api.runs import _RUN_ACTIONS, _dispatch_run_action
from workflow.api.evaluation import _JUDGMENT_ACTIONS, _BRANCH_VERSION_ACTIONS, _dispatch_judgment_action
from workflow.api.runtime_ops import (
    _PROJECT_MEMORY_ACTIONS, _PROJECT_MEMORY_WRITE_ACTIONS,
    _MESSAGING_ACTIONS, _INSPECT_DRY_ACTIONS, _SCHEDULER_ACTIONS,
)
from workflow.api.market import (
    _ESCROW_ACTIONS, _GATE_EVENT_ACTIONS, _OUTCOME_ACTIONS, _ATTRIBUTION_ACTIONS,
)
from workflow.api.engine_helpers import _current_actor, _append_global_ledger  # post-Step-10 path
```

**Risk:** **Circular import risk.** branches.py + runs.py + evaluation.py + runtime_ops.py + market.py currently lazy-import preamble helpers from `workflow.universe_server` (which after Step 10 should retarget to `workflow.api.engine_helpers`). If any of those submodules also imports from extensions.py at top-of-module, we get a cycle. **Mitigation:** Verify at extraction time — none of Steps 4-8 modules need to import from extensions.py (extensions is downstream of all of them in the dataflow). Verified by grep: no `from workflow.api.extensions import ...` anywhere.

### 3.2 Do Steps 1-10 submodules depend on extensions.py symbols?

**No — clean leaf module.**

- No Steps-1-10 module imports `_load_nodes`, `_save_nodes`, `NodeRegistration`, `_ext_*`, or `VALID_PHASES` / `ALLOWED_DEPENDENCIES`.
- The `extensions()` MCP tool function is at the chatbot-facing edge — nothing internal calls it.
- Verified via grep: no `from workflow.api.extensions import ...` anywhere in Steps 1-10 modules.

**This is the cleanest leaf extraction structurally.** extensions.py is downstream of every other api/ submodule.

### 3.3 Does extensions.py depend on universe_server preamble?

**Light dependency:**
- `_current_actor`, `_append_global_ledger` — Step 10 routes these to `workflow.api.engine_helpers`.
- `logger` — universe_server-scoped; extensions.py defines its own `logger = logging.getLogger("universe_server.extensions")`.
- `_base_path` — used by `_ensure_standalone_branch` + `_load_nodes` + `_save_nodes`. Already in `workflow.api.helpers`.

**No NEW preamble dependencies introduced** — all already routed via Steps 8/10.

### 3.4 Does extensions.py share dispatch surface with `universe()`?

**No — verified via universe.py extraction (Step 9) and current code scan.** `extensions()` body does NOT reference any `_action_*` handler from the universe-tool scope; `universe()` body does NOT reference `_ext_*` or `_BRANCH_ACTIONS`. The two MCP tools are siblings with no cross-tool dispatch — confirmed in Step 9 prep §3.4. Same isolation applies to `goals`, `gates`, `wiki`, `get_status` (Pattern A2 wrappers — they delegate to api/market.py + api/wiki.py + api/status.py respectively).

---

## 4. FastMCP `mcp` instance — Pattern A2 decision required

`extensions()` IS an `@mcp.tool()` registration. Same Pattern A2 question as Step 9 (universe.py):

- **Option A** (recommended, consistent with Step 9 §4 + Step 8 + #6/#7): Move the `extensions()` body to `tinyassets/api/extensions.py` as a plain function `_extensions_impl(action: str, **kwargs: Any) -> str`. Preserve `@mcp.tool() def extensions(...)` decorator + 80+ arg signature in `tinyassets/universe_server.py` wrapping a delegation to `_extensions_impl`. ~120-line wrapper (largest Pattern A2 wrapper so far — extensions has the most arguments).
- **Option B**: Move `@mcp.tool()` decoration WITH the body to `tinyassets/api/extensions.py`. Requires `mcp` instance import in extensions.py (back-edge `from workflow.universe_server import mcp` — same leaf-module concern).

**Recommendation: Option A** — consistent with how `goals`, `gates`, `wiki`, `get_status`, Step 8's `@mcp.prompt` Branch Design Guide, and Step 9's `@mcp.tool() universe()` are handled. Avoids the leaf-module question entirely. Wrapper preservation cost ~120 LOC is the price of consistency.

**Decision asked of lead in §9.**

---

## 5. Test files importing extensions-tool symbols (and how)

**Surveyed all extensions-tool symbols + dispatch entry points:**

| Symbol | Test files importing | Approx. import count |
|---|---|---|
| `extensions` (MCP tool function — direct call) | 36 sites | ~8-10 test files |
| `_load_nodes` (mock.patch) | 3 sites | `test_node_registry_migration.py`, `test_publish_version.py`, others |
| `_save_nodes` (mock.patch) | 2 sites | similar |
| `NodeRegistration`, `STANDALONE_NODES_BRANCH_ID`, `VALID_PHASES`, `ALLOWED_DEPENDENCIES` | sparse — 1-3 each | various |

**Test files with extensions-tool dependencies** (sampled from grep): `test_attribution_mcp.py`, `test_continue_branch.py`, `test_cross_run_state_query.py`, `test_dry_inspect_node.py`, `test_gate_event_mcp.py`, `test_node_registry_migration.py`, `test_outcome_mcp.py`, `test_payments_escrow_mcp.py`, `test_project_memory.py`, `test_publish_version.py`, plus 5-10 others. **Total estimated: ~50-70 test imports across ~15-20 test files.**

**Strategy: back-compat re-export shim** preserves all imports. Re-export block in `tinyassets/universe_server.py` after Step 11:

```python
from workflow.api.extensions import (  # noqa: E402, F401
    ALLOWED_DEPENDENCIES,
    NodeRegistration,
    STANDALONE_NODES_BRANCH_ID,
    VALID_PHASES,
    _ensure_standalone_branch,
    _ext_inspect,
    _ext_list,
    _ext_manage,
    _ext_register,
    _load_nodes,
    _nodes_path,
    _save_nodes,
)
```

**Monkeypatch-target risk: MEDIUM.** 5 confirmed `mock.patch("workflow.universe_server._load_nodes" / "_save_nodes", ...)` sites. After Step 11, those patches need mirrors at `workflow.api.extensions._load_nodes` / `_save_nodes` per the #9/#11/Step-8/Step-10 pattern. **Expected: 5 mirror-patch additions across 3-4 test files.**

**Direct `extensions(action="...")` call sites:** 36 sites. These continue working through the Pattern A2 wrapper at `workflow.universe_server.extensions` — **no test edits needed** because the wrapper is a transparent delegation.

---

## 6. Risks the audit didn't anticipate

1. **Largest Pattern A2 wrapper.** `extensions()` has 80+ keyword args (vs `universe()`'s 23). Wrapper preservation is ~120 LOC. Unavoidable cost for keeping the `mcp` instance owned by universe_server.py.

2. **Most cross-tool-coupled extraction.** extensions.py imports from 5 prior submodules (branches, runs, evaluation, runtime_ops, market) at top-of-module. Other api/ submodules use lazy imports because they're called inside hot paths. extensions.py is a routing module — its imports are needed at every dispatch, so top-of-module is correct.

3. **Circular-import risk** (verified §3.1 — none today, but extraction-time grep required). If any Step-1-10 submodule grew an import of extensions.py at top-of-module before Step 11 lands, the cycle would break the build. Run `python -c "import workflow.api.extensions"` as a verification step.

4. **Circular import via `_append_global_ledger`.** `extensions()` calls `_append_global_ledger(...)` inside `_PROJECT_MEMORY_ACTIONS` handling. `_append_global_ledger` lives in branches.py (Step 8 range L4561) until Step 10 retargets it to engine_helpers.py. **Sequencing constraint:** Step 11 should ideally land AFTER Step 10 so the `_append_global_ledger` import is at its canonical engine_helpers.py path. If lead approves Step 11 BEFORE Step 10, we lazy-import from `workflow.universe_server` until Step 10 ships.

5. **5 monkeypatch mirror additions.** Lower friction than Step 10's 13, but still mechanical. Acceptable cost.

6. **`NodeRegistration` is the only `@dataclass` in scope.** Move with extensions.py — used only by `_ext_register`. No test-import.

7. **`_nodes_path` is legacy** — used only by `_ensure_standalone_branch` for the JSON migration probe. Keep with extensions.py until the migration is dropped (separate cleanup).

8. **The `extensions()` docstring (~140 LOC)** is the chatbot-facing reference for every action verb. After Pattern A2, this docstring stays in universe_server.py (on the wrapper) — chatbots see the same docstring. Alternative: move docstring to `_extensions_impl` and the wrapper docstring just says "see _extensions_impl"; risk that some MCP clients render the wrapper docstring, not the implementation's. **Recommend: keep the full ~140-line docstring on the universe_server.py wrapper** to preserve client-side discoverability.

9. **`extensions()` "available_actions" error block** (L4322-L4349) is a hardcoded list of 60+ action names. Stays with `_extensions_impl` body in extensions.py. **Risk:** if a new action is added via Steps 4-8 dispatch tables but not registered in this hardcoded list, the error message goes stale. Known debt — not introduced by Step 11.

10. **Pre-commit canonical-vs-plugin parity check** — same as previous steps. Run `python packaging/claude-plugin/build_plugin.py`.

11. **Sequencing constraint.** Step 11 strictly after Step 10 (preferred — clean engine_helpers.py import path) OR Step 10 + 11 in parallel with explicit lazy-import scaffolding. **Recommend serial: Step 10 → Step 11.**

12. **Module docstring** carries the audit + decomposition history + the audit-target reflection ("after Step 11, residual is ~1,300 LOC; the literal 100-LOC audit target requires the test-import retarget sweep — see §9.7").

---

## 7. Total LOC moved estimate

| Block | LOC moved to extensions.py |
|---|---|
| TOOL 2 banner + standalone-node infrastructure (L3700-L3830) | ~120 |
| `extensions()` body L3833-L4350 — moves to `_extensions_impl` (Option A) | ~398 (loses @mcp.tool decorator + 80-arg signature, kept in shim) |
| `_ext_register`, `_ext_list`, `_ext_inspect`, `_ext_manage` (L4353-L4489) | ~137 |
| **Total moved out of universe_server.py** | **~655** |
| Back-compat re-export block added to universe_server.py | ~25 |
| `@mcp.tool() def extensions(...)` decorator + 80-arg signature wrapper preserved (Option A) | ~120 (decorator + sig + delegation; body is in extensions.py) |
| **Net reduction in universe_server.py** | **~510** |
| New `tinyassets/api/extensions.py` size | **~800** (with imports + module docstring + Pattern A2 docstring) |

**Materially smaller than Step 9 (~2,959 net reduction)** — extensions.py is a routing module, so the body LOC count is much smaller than universe.py's 28-handler suite.

---

## 8. Concrete Step 11 implementation plan

Estimated wall time: **120-180 min** (largest Pattern A2 wrapper preservation; cross-tool dependency wiring; 5 monkeypatch mirror additions).

1. **Confirm Steps 8 + 9 + 10 landed.** Step 11 should ideally serialize after Step 10 for clean engine_helpers.py imports.
2. **AST scan for circular-import risk** (per §3.1 + §6.3). Run `python -c "import workflow.api.extensions"` against a stub before authoring extensions.py.
3. **Verify dispatch-table extraction landed in Steps 4-8.** All 12 dispatch tables (`_BRANCH_ACTIONS`, `_RUN_ACTIONS`, `_JUDGMENT_ACTIONS`, `_PROJECT_MEMORY_ACTIONS`, `_BRANCH_VERSION_ACTIONS`, `_MESSAGING_ACTIONS`, `_ESCROW_ACTIONS`, `_GATE_EVENT_ACTIONS`, `_INSPECT_DRY_ACTIONS`, `_SCHEDULER_ACTIONS`, `_OUTCOME_ACTIONS`, `_ATTRIBUTION_ACTIONS`) must be importable from their canonical api/ paths.
4. **Create `tinyassets/api/extensions.py`:**
   - Module docstring referencing audit + extraction date + the source ranges + Pattern A2 explanation for `@mcp.tool() extensions()` + circular-import-risk note + audit-target reflection.
   - **Top-of-module imports** (not lazy):
     ```python
     from workflow.api.branches import _BRANCH_ACTIONS, _BRANCH_WRITE_ACTIONS, _dispatch_branch_action
     from workflow.api.runs import _RUN_ACTIONS, _dispatch_run_action
     from workflow.api.evaluation import _JUDGMENT_ACTIONS, _BRANCH_VERSION_ACTIONS, _dispatch_judgment_action
     from workflow.api.runtime_ops import _PROJECT_MEMORY_ACTIONS, _PROJECT_MEMORY_WRITE_ACTIONS, _MESSAGING_ACTIONS, _INSPECT_DRY_ACTIONS, _SCHEDULER_ACTIONS
     from workflow.api.market import _ESCROW_ACTIONS, _GATE_EVENT_ACTIONS, _OUTCOME_ACTIONS, _ATTRIBUTION_ACTIONS
     from workflow.api.engine_helpers import _current_actor, _append_global_ledger  # post-Step-10
     from workflow.api.helpers import _base_path, _read_json
     from workflow.daemon_server import get_branch_definition, initialize_author_server, save_branch_definition, update_branch_definition
     ```
   - Move L3700-L3830 verbatim (TOOL 2 banner + standalone-node infrastructure).
   - Move L3833-L4350 verbatim (`extensions()` body) → rename to `_extensions_impl(action, **kwargs)` for Pattern A2.
   - Move L4353-L4489 verbatim (`_ext_*` handlers).
5. **Update `tinyassets/universe_server.py`:**
   - Delete L3700-L4489 (single contiguous range).
   - Add back-compat shim block (~12 symbols re-exported).
   - Add `@mcp.tool(...) def extensions(action, ..., since_days) -> str: return _extensions_impl(action, ..., since_days)` Pattern A2 wrapper. Preserve full 80+ arg signature + decorator + `title="Graph Extensions"` + tags + ToolAnnotations + ~140-line docstring.
6. **Test edits expected.** Add mirror patches to 3-4 test files for `_load_nodes` / `_save_nodes` (5 sites total). Direct `extensions(action="...")` call sites (~36) need NO edit — Pattern A2 wrapper passes through.
7. **Run `python packaging/claude-plugin/build_plugin.py`** to sync plugin runtime mirror.
8. **Verification:**
   - `pytest tests/test_node_registry_migration.py tests/test_publish_version.py tests/test_attribution_mcp.py tests/test_dry_inspect_node.py tests/test_gate_event_mcp.py tests/test_outcome_mcp.py tests/test_payments_escrow_mcp.py tests/test_project_memory.py -q` → green.
   - `pytest -k "extensions or ext_ or node_registry" -q` → cross-cutting smoke.
   - `pytest -q` → full suite green (essential — Step 11 wires the chatbot-facing dispatch surface).
   - `ruff check tinyassets/api/extensions.py tinyassets/universe_server.py` → clean.
   - **Visual check:** `git diff tinyassets/universe_server.py | grep -c "^-def _ext_"` should equal **4** (`_ext_register`, `_ext_list`, `_ext_inspect`, `_ext_manage`).
   - **MCP probe:** `python scripts/mcp_probe.py --tool extensions --args '{"action":"list"}'` → returns valid node list. Validates Pattern A2 wrapper.
   - **Circular-import check:** `python -c "import workflow.api.extensions; import workflow.universe_server"` → both succeed cleanly.

**Files in eventual Step 11 SHIP handoff:**
- `tinyassets/api/extensions.py` (NEW, ~800 LOC)
- `tinyassets/universe_server.py` (~655 LOC removed + ~25 re-export added + ~120 wrapper preservation = net ~−510)
- `tests/test_api_extensions.py` (NEW, 50-80 tests recommended)
- 3-4 existing test files with monkeypatch-target mirror updates
- `packaging/claude-plugin/.../tinyassets/api/extensions.py` (NEW mirror)
- `packaging/claude-plugin/.../tinyassets/universe_server.py` (mirror)

5-7 files, +850 / −510 LOC net.

---

## 9. Decision asks for the lead

1. **Option A (recommended) vs Option B for `@mcp.tool() extensions()`** — see §4. Recommend Option A (preserve `@mcp.tool()` decorator + 80+ arg signature + ~140-line docstring in universe_server.py with delegation to `_extensions_impl` in extensions.py). Wrapper cost ~120 LOC — largest Pattern A2 wrapper of any extraction, but consistent with all 6 prior wrappers.

2. **Sequencing: Step 11 strictly after Step 10.** See §6.4 + §6.11. Step 11's `extensions()` body calls `_append_global_ledger` which lives in branches.py until Step 10 retargets it to engine_helpers.py. Recommend serial Step 10 → Step 11.

3. **Top-of-module imports vs lazy.** See §3.1. Recommend **top-of-module imports** for the 12 dispatch tables — extensions.py is a routing module, imports are needed at every dispatch. (Lazy imports waste call-time on this hot path.) Verify circular-import safety per §6.3.

4. **5 monkeypatch mirror additions.** Lower friction than Step 10's 13. Mechanical mirror additions (don't replace existing `us.X` patches). Confirm acceptable.

5. **`extensions()` ~140-line docstring placement.** See §6.8. Recommend keeping the full docstring on the `universe_server.py` wrapper (Pattern A2 preserves client-side discoverability). The implementation file's `_extensions_impl` gets a short delegating docstring "see workflow.universe_server.extensions for chatbot-facing reference."

6. **`available_actions` hardcoded list staleness debt.** See §6.9. Known issue, NOT introduced by Step 11. Worth a follow-up task to make it dynamically derived from the dispatch tables. **Out of scope for Step 11** but flagged for the backlog.

7. **Audit's literal "~100-LOC routing shell" target.** Step 11 reduces residual to **~1,300 LOC**, not 100. The 100-LOC literal target requires "Step 11+ retarget sweep" — change ~150-200 test imports across the codebase from `workflow.universe_server.X` to the canonical `workflow.api.<module>.X` path. Only after that sweep can the back-compat re-export shims in universe_server.py be deleted (~700 LOC of shim removal). **Recommend acceptance criteria for the retarget sweep:**
   - **Acceptance:** universe_server.py contains only the FastMCP `mcp` instance + 7 Pattern A2 wrappers (universe + extensions + goals + gates + wiki + get_status + branch_design_guide + control_station + extension_guide) + `main()` + `@mcp.custom_route("/")` health-check + module imports. Final size: ~150 LOC.
   - **Risk profile:** ~150-200 mechanical sed-style test edits, NO behavior change. Risk = low. Effort = 4-6 hours wall time. ROI debate: hits the audit's stated target; vs. residual ~1,300 LOC is already 91% reduction from baseline 14,012. **Recommend deferring the retarget sweep as a separate scope decision** — Step 11 ships standalone with ~1,300 LOC residual, the host can decide whether the additional 6-hour retarget sweep is worth the final 1,150-LOC reduction.

---

## 10. Cross-prep summary (Steps 1-11 combined, projected)

After Step 11 lands:

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
| Step 9 (prep) | `universe.py` | ~2,959 | ~2,150 |
| Step 10 (prep) | `engine_helpers.py` | ~245 | ~1,900 |
| Step 11 (this prep) | `extensions.py` | ~510 | **~1,400** |
| **Subtotal after Step 11** | 9 new + 1 extended | ~12,624 | **~1,400** |

**universe_server.py drops below ~1,400 LOC after Step 11** (from baseline 14,012 = ~90% reduction). Remaining content:
- 7 Pattern A2 wrappers (universe + extensions + goals + gates + wiki + get_status + branch_design_guide) ~470 LOC
- 2 `@mcp.prompt` registrations (control_station + extension_guide) ~30 LOC
- `main()` daemon entrypoint ~50 LOC
- `@mcp.custom_route("/")` health check ~20 LOC
- Module imports + setup ~150 LOC
- Cross-module re-export shims (Steps 1-7 imports) ~315 LOC
- Step-8/9/10/11 back-compat re-export shims ~300 LOC
- Banners/comments ~65 LOC

**With the Step 11+ retarget sweep (see §9.7), residual drops to ~150 LOC** — finally hits the audit's "~100-LOC routing shell" target. Decision deferred to host per §9.7.

All 11 steps remain pure refactor — no behavior change. The decomposition's stated goal of "make universe_server.py readable + composable" is fully met. **At ~1,400 LOC residual + 9 well-bounded api/ submodules averaging ~1,400 LOC each (range 350-3,150), the platform achieves: (a) every MCP tool is one file, (b) every dispatch table is co-located with its action handlers, (c) the `mcp` instance + Pattern A2 wrappers are unambiguously owned by universe_server.py.**

The audit's "100-LOC routing shell" is an aspirational target — Step 11 brings us to the practical floor without the test-import sweep. The retarget sweep is mechanical work whose ROI is debate-worthy: 6 hours of effort to drop residual from 1,400 to 150 LOC = 89% additional reduction, but the 1,400-LOC residual is ALREADY 90% reduction from baseline. **Recommend host evaluate after Step 11 ships.**
