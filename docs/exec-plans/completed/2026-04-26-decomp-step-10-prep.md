---
title: Step 10 prep — tinyassets/api/engine_helpers.py extraction scope
date: 2026-04-26
author: navigator
status: pre-flight scoping (no edits yet)
companion: docs/audits/2026-04-25-universe-server-decomposition.md (audit's "100-LOC routing shell" target — Steps 9+10 are post-original-8-step extension); docs/exec-plans/completed/2026-04-26-decomp-step-9-prep.md
target_task: Decomp post-Step-9 — Extract tinyassets/api/engine_helpers.py (preamble engine functions: ledger trio, upload-whitelist, dirty-file/commit error formatters, branch-visibility filters, MCP-prompt registrations)
gates_on: Step 8 (`branches.py`) + Step 9 (`universe.py`) MUST land first. Step 10 is the LAST extraction in the planned decomposition. After Step 10, residual universe_server.py is the projected ~650-LOC routing shell — close to (but not identical to) audit's "~100-LOC routing shell" target.
---

# Step 10 (`engine_helpers.py`) pre-flight scope

Read-only scope for extracting the preamble engine helpers from `tinyassets/universe_server.py` into a new `tinyassets/api/engine_helpers.py`. **Smallest extraction by LOC** (~600 moveable LOC) but **highest test-monkeypatch-target surface** (`_current_actor` patched 7×, `_storage_backend` patched 4× across the test suite). Same freshness-check protocol as Steps 1-9 prep.

This step is NOT in the original 8-step audit plan. Per Step 9 prep §4, Step 10 lands after Step 9 to validate the Pattern A2 wrapper for `@mcp.tool() universe()` first, then extracts the preamble engine helpers Step 9 lazy-imports from. After Step 10, the audit's "~100-LOC routing shell" target is materially closer (residual ~650 LOC) — still ~6× the audit target but ~12× smaller than today's 7,778.

---

## 1. Audit-vs-reality verdict

**Audit estimate (§9 step 8 + §10 future):** Audit framed "~100-LOC routing shell" as the target after Step 8. It did NOT explicitly enumerate `engine_helpers.py` as a separate step — Step 8 prep §10.2 + Step 9 prep §6.9 surfaced the gap. The audit's framing was "after Step 8, residual is preamble + extensions() body + 6 wrapper preservations + shim" — but didn't break "preamble" into its own step.

**Reality (current code, 2026-04-26 post-Step-7, pre-Steps-8/9):**

| Block | Banner / Section | Line range | LOC (est.) |
|---|---|---|---|
| Imports + module setup | (no banner) | L29-L184 | ~150 (stays — see §2.1) |
| `@mcp.custom_route("/")` health check | (no banner) | L163 | ~20 (stays — see §2.1) |
| Cross-module re-export shims (Steps 1-7) | (no banner) | L184-L350 | ~165 (stays — re-export shims) |
| Upload-whitelist trio | (no banner) | L353-L437 | ~85 |
| Public action ledger trio | "Public action ledger" L443 | L451-L506 | ~56 |
| Storage + error formatters | (no banner) | L716-L832 | ~117 |
| MCP prompts: `control_station`, `extension_guide` | "MCP PROMPTS — behavioral instructions" L961 | L961-L988 | ~28 |
| `main()` daemon entrypoint | (no banner — bottom of file) | L7511 | ~50 |
| **Total moveable to engine_helpers.py** | | | **~336** |
| **Plus content surviving in universe_server.py** | | | ~315 (imports + custom_route + cross-module shims + Step-1-9 re-export shim + extensions() wrapper + 6 @mcp.tool/@mcp.prompt wrapper preservations) |

**Total moveable: ~336 LOC.** Smallest extraction by LOC, but largest by test-patch impact (see §5).

**Important narrowing:** After Step 9 lands, the WRITE_ACTIONS extractors (L508-L713) + ledger dispatcher trio (L857-L959) are already gone — they moved with universe.py. So Step 10's preamble-extraction range is the leftover preamble after Step 9 carved out the universe-tool surface.

**Critical excluded items (already extracted by prior steps — NOT in Step 10 scope):**
- `_dispatch_with_ledger`, `_ledger_target_dir`, `_scope_universe_response` — moved to **universe.py in Step 9** (L857-L959).
- `_daemon_liveness`, `_compute_accept_rate_from_db`, `_compute_word_count_from_files`, `_last_activity_at`, `_staleness_bucket`, `_phase_human`, `_parse_activity_line` — moved to **universe.py in Step 9** (L1240-L1490 + L3502).
- `WRITE_ACTIONS` table + 14 `_extract_*` extractor closures — moved to **universe.py in Step 9** (L508-L713).
- `_append_global_ledger`, `_ensure_author_server_db`, `_resolve_branch_id`, `_apply_node_spec`, `_split_csv`, `_coerce_node_keys`, `_resolve_udir` — moved to **branches.py in Step 8** (L4435-L7110 range).
- `_gates_enabled` — already lives in **`tinyassets/api/market.py:1469`** (extracted in Step 7); re-exported from `tinyassets/universe_server.py:274`. Test patch at `test_describe_branch_approval.py:71` (`patch("workflow.universe_server._gates_enabled", ...)`) is a Step-7 follow-up, not a Step-10 concern. (Verified 2026-04-27 via grep of all `_gates_enabled` callers.)

**Critical excluded items (stay in universe_server.py post-Step-10):**
- Module imports (L29-L48) — the cross-module re-export shims need them.
- `@mcp.custom_route("/")` health check (L163) — universe_server.py owns the FastMCP app instance + HTTP route registration. Cannot move without bringing `mcp` instance with it.
- Cross-module re-export shims (L184-L350 — `from workflow.api.evaluation import ...`, `from workflow.api.helpers import ...`, etc.) — these are universe_server.py's legitimate role as the back-compat surface. They stay.
- Per-Steps-1-9 re-export shim block (post-extraction additions) — they stay.
- `extensions()` body + `@mcp.tool()` wrapper for `extensions` — stays. extensions() is an MCP tool registration; same Pattern A2 leaf-module concern as `universe()`. (See §6.4 for whether to add Step 11 for `extensions.py`.)
- 6 Pattern A2 wrapper preservations — `goals`, `gates`, `wiki`, `get_status`, `branch_design_guide` (Step 8), `universe` (Step 9). All stay.

---

## 2. Symbol enumeration (current line ranges)

### 2.1 Imports + module setup (L29-L184) — STAYS

Module imports + FastMCP instance creation + the `@mcp.custom_route("/")` HTTP health-check route. These cannot move because:
- `mcp = FastMCP(...)` instance is the parent the Pattern A2 wrappers + `@mcp.custom_route` + cross-module re-exports all anchor to.
- Cross-module re-export shim blocks (Steps 1-7 imports L184-L350) need the module-level namespace.

**Stays in universe_server.py.** ~315 LOC of imports + setup + shims.

### 2.2 Upload-whitelist trio (L353-L437)

| Symbol | Line | LOC | Notes |
|---|---|---|---|
| `_upload_whitelist_prefixes` | 353 | ~25 | Reads `TINYASSETS_UPLOAD_WHITELIST` env var; resolves to absolute path list. |
| `_split_whitelist_entry` | 380 | ~36 | Cross-platform path-list split (handles Windows drive-letter colons). |
| `_warn_if_no_upload_whitelist` | 418 | ~14 | Logs warning at module-import time. **Called at L437 module-import time** — see §3.5. |
| `_warn_if_no_upload_whitelist()` call | 437 | 1 | Module-import-time invocation. **Migrates to engine_helpers.py module load** — but universe_server.py needs the import side-effect preserved. |

Total: ~85 LOC. Used only by `_action_add_canon_from_path` (which moved to universe.py in Step 9). After Step 10, universe.py imports `_upload_whitelist_prefixes` from engine_helpers.py.

### 2.3 Public action ledger trio (L451-L506)

| Symbol | Line | LOC | Notes |
|---|---|---|---|
| Module comment block "Public action ledger" | 443 | ~8 | Preserve verbatim. |
| `_current_actor` | 451 | ~8 | **HIGHEST patch-target frequency** — patched 7× across test suite. See §5. |
| `_append_ledger` | 459 | ~41 | Per-universe ledger append. Called by `_dispatch_with_ledger` (now in universe.py). |
| `_truncate` | 500 | ~6 | String truncation utility for ledger summaries. Called by every WRITE_ACTIONS extractor (now in universe.py). |

Total: ~56 LOC. Used heavily by Step-9 universe.py (lazy imports) and Steps 4-8 (lazy imports). After Step 10, all those lazy imports change source from `workflow.universe_server` to `workflow.api.engine_helpers`.

### 2.4 Storage + error formatters (L716-L832)

| Symbol | Line | LOC | Notes |
|---|---|---|---|
| `_storage_backend` | 716 | ~14 | Memoized `StorageBackend` factory. **HIGH patch-target frequency** — patched 4× in `test_build_branch_summary_response.py`. |
| `_format_dirty_file_conflict` | 732 | ~20 | Shapes `DirtyFileError` for MCP clients (Phase 7.3 dirty-file guard). |
| `_filter_claims_by_branch_visibility` | 753 | ~46 | Phase 6.2.2 — hide gate claims whose Branch is private. **Imports `from workflow.daemon_server import get_branch_definition`** at function-body time (lazy). |
| `_filter_leaderboard_by_branch_visibility` | 799 | ~35 | Sibling of above; lazy-imports `get_branch_definition`. |
| `_format_commit_failed` | 834 | ~24 | Shapes `CommitFailedError` (sync_commit replay path). |

Total: ~117 LOC. **Called by various Step-7 (market.py) + Step-8 (branches.py) handlers** — after Step 10, those modules' lazy imports change source.

### 2.5 MCP prompts: `control_station` + `extension_guide` (L961-L988)

| Symbol | Line | LOC | Notes |
|---|---|---|---|
| `@mcp.prompt(...)` for control_station | 966 | ~4 | |
| `def control_station() -> str` | 970 | ~10 | Returns `_CONTROL_STATION_PROMPT` from `workflow.api.prompts`. |
| `@mcp.prompt(...)` for extension_guide | 980 | ~4 | |
| `def extension_guide() -> str` | 984 | ~5 | Returns the guide markdown. |

Total: ~28 LOC. **Pattern A2 question** (see §4). Two `@mcp.prompt()` decorations.

**Pattern A2 trade-off:** These are 28 LOC of decorators + thin function bodies. Pattern A2 wrapper preservation in universe_server.py would be similar size (decorator + sig + delegation = ~25 LOC). **Net LOC change is near zero** — extracting these is more cosmetic than reductive.

**Recommendation:** **Leave control_station + extension_guide IN universe_server.py.** They're already as small as possible; extracting them just doubles the LOC count. Extract everything else.

### 2.6 `main()` daemon entrypoint (L7511)

| Symbol | Line | LOC | Notes |
|---|---|---|---|
| `def main(...)` | 7511 | ~50 | Daemon entrypoint. Wires CLI args + `mcp.run(...)`. **Stays in universe_server.py** because it owns the `mcp` instance and is the canonical entry point. Pattern A2 doesn't apply — this isn't an MCP tool, it's the process bootstrap. |

**Stays in universe_server.py.** ~50 LOC.

---

## 3. Cross-references — bidirectional dependency check

### 3.1 Does engine_helpers.py depend on Steps 1-9 modules?

**Light dependency:**
- `_filter_claims_by_branch_visibility`, `_filter_leaderboard_by_branch_visibility` lazy-import `from workflow.daemon_server import get_branch_definition` — daemon_server is a sibling, not an api/* submodule. Stays as lazy import.
- `_storage_backend` calls `_base_path()` from `workflow.api.helpers` (Step 8). Direct top-of-module import after extraction.
- `_format_dirty_file_conflict` accepts `DirtyFileError` (workflow.storage exception). Type-hint only; no behavioral coupling.

**No dependency on Steps 4-9 dispatch tables or handlers.** Engine helpers are PRE-Steps-1-9 chronologically.

### 3.2 Do Steps 1-9 submodules depend on engine_helpers.py symbols?

**Yes — the heaviest reverse-dependency of any extraction.** All 9 prior extractions (helpers.py extension, wiki.py, status.py, runs.py, evaluation.py, runtime_ops.py, market.py, branches.py, universe.py) lazy-import preamble symbols from `workflow.universe_server`:

| Symbol | Step modules using it | Approx. lazy-import touch points |
|---|---|---|
| `_current_actor` | runs, evaluation, runtime_ops, market, branches, universe | ~30 lazy imports |
| `_append_ledger` | universe (via `_dispatch_with_ledger`) | 1 |
| `_truncate` | universe (via WRITE_ACTIONS extractors) | 14 |
| `_storage_backend` | branches, universe (`_action_post_to_goal_pool`, `_action_create_universe`), evaluation | ~10 lazy imports |
| `_format_dirty_file_conflict` | branches, universe (write handlers) | ~6 lazy imports |
| `_filter_claims_by_branch_visibility` | market | 1-2 |
| `_filter_leaderboard_by_branch_visibility` | market | 1-2 |
| `_format_commit_failed` | runs, branches | ~3 lazy imports |
| `_upload_whitelist_prefixes` | universe (`_action_add_canon_from_path`) | 1 |

**Strategy:** After Step 10 ships, change all lazy imports from `from workflow.universe_server import _current_actor, ...` to `from workflow.api.engine_helpers import _current_actor, ...`. The back-compat re-export shim in universe_server.py preserves any test imports that go through the legacy path. **Expect 50-80 lazy-import edits across the 9 prior submodules.**

**Alternative considered:** Leave lazy imports pointing at `workflow.universe_server` (which itself re-exports from `engine_helpers`). This avoids the 50-80 edits. Trade-off: slower import resolution (extra module hop) and continued visual coupling to universe_server.py. **Recommendation:** make the edits — clean leaf module is worth 50-80 trivial sed-style replacements. Decision asked of lead in §9.

### 3.3 Does engine_helpers.py depend on universe_server preamble?

**No — engine_helpers.py IS the preamble.** Once extracted, engine_helpers.py is a pure leaf with no upstream dependencies in the workflow.api.* tree.

### 3.4 Does engine_helpers.py share dispatch surface with `extensions()`?

**Yes, but only the @mcp.prompt registrations have a leaf-module question** (similar to Step 8 §3.6 + Step 9 §4). Per §2.5, recommend leaving those IN universe_server.py.

### 3.5 `_warn_if_no_upload_whitelist()` module-import call (L437)

This is invoked at module-import time. After Step 10, the import-time side effect needs to be preserved. **Two options:**
- **A:** Move the `_warn_if_no_upload_whitelist()` call to engine_helpers.py module-load (since the function moves there). universe_server.py no longer triggers the warning at import — relies on engine_helpers being imported. Risk: if engine_helpers is never imported at server start, the warning is silent.
- **B:** Keep the `_warn_if_no_upload_whitelist()` call at universe_server.py module-load. Lazy-import the function: `from workflow.api.engine_helpers import _warn_if_no_upload_whitelist; _warn_if_no_upload_whitelist()`. Preserves behavior verbatim. Recommended.

---

## 4. FastMCP `mcp` instance — Pattern A2 inheritance

engine_helpers.py does NOT register any `@mcp.tool()` or `@mcp.prompt()` decorator (per §2.5 recommendation, control_station + extension_guide stay in universe_server.py). **No Pattern A2 question for this step.**

`mcp` instance ownership stays unambiguously in universe_server.py.

---

## 5. Test files importing engine_helpers symbols (and how)

**HIGHEST patch-target burden of any extraction.** Surveyed all preamble engine helpers:

| Symbol | Test-patch sites | Test files |
|---|---|---|
| `_current_actor` (mock.patch) | 7 sites | `test_branch_name_resolution.py:30,99` (×2), `test_build_branch_summary_response.py:273` (×1), `test_describe_branch_approval.py:70` (×1), `test_run_branch_failure_taxonomy.py:123,274,504` (×3) |
| `_current_actor` (monkeypatch.setattr) | 2 sites | `test_run_branch_version.py:311,337` |
| `_storage_backend` (mock.patch) | 4 sites | `test_build_branch_summary_response.py:272,329,373,420` |
| `control_station` (direct import) | 2 sites | (test files reading the prompt body) |

**Total: 13 patch sites + 2 import sites = 15 test interactions** with preamble engine helpers.

**Strategy: back-compat re-export shim** preserves all imports (per audit §7 Strategy 1). Re-export block in `tinyassets/universe_server.py` after Step 10:

```python
from workflow.api.engine_helpers import (  # noqa: E402, F401
    _append_ledger,
    _current_actor,
    _filter_claims_by_branch_visibility,
    _filter_leaderboard_by_branch_visibility,
    _format_commit_failed,
    _format_dirty_file_conflict,
    _split_whitelist_entry,
    _storage_backend,
    _truncate,
    _upload_whitelist_prefixes,
    _warn_if_no_upload_whitelist,
)
```

**Monkeypatch-target risk: HIGH.** All 13 test-patch sites use `workflow.universe_server.X` paths. After Step 10, those patches won't reach the engine_helpers.py-resident functions when called from new module paths (e.g., when universe.py calls `_current_actor` it imports from `workflow.api.engine_helpers`, not `workflow.universe_server`). **Per the #9 + #11 + Step-8 pattern: each test patch needs a mirror at `workflow.api.engine_helpers.X`.**

**Expected test edits: 13 sites + 1-2 mirror lines per site = 13-26 line additions across 5 test files.** Largest test-patch-target burden of any extraction. Acceptable because (a) edits are mechanical (mirror existing patches, don't replace), (b) the alternative (changing engine_helpers.py to look up names via universe_server) defeats the extraction.

---

## 6. Risks the audit didn't anticipate

1. **Highest test-monkeypatch-target burden of any extraction.** 13 patch sites need mirror patches. Mitigation: mechanical sed-style additions, no logic changes. Each test continues to pass with the original `us.X` patch AND a new `eh.X` mirror.

2. **50-80 lazy-import touch points across Steps 1-9 submodules.** Strategy decision (see §3.2 + §9): make all the edits, OR leave lazy imports pointing at universe_server (extra module hop on every call). **Recommend make-the-edits** for clean leaf — 50-80 trivial replacements.

3. **`_warn_if_no_upload_whitelist()` import-time side effect** — see §3.5. Recommend Option B (preserve the call at universe_server.py module-load via lazy-import).

4. **`extensions()` body + `@mcp.tool()` wrapper STAY in universe_server.py.** The `extensions()` body is ~600 LOC of dispatch logic (calls into `_BRANCH_ACTIONS`, `_RUN_ACTIONS`, `_JUDGMENT_ACTIONS`, etc. — all already extracted to Steps 4-8). Pattern A2 wrapper preservation would be ~80 LOC (decorator + 80-arg signature + delegation). **Question: should there be a Step 11 for `extensions.py` extraction?** The `extensions()` body is similar in shape to `universe()`'s — large dispatch table funneling kwargs to action handlers. Step 11 would extract `extensions()` body to `tinyassets/api/extensions.py` via Pattern A2, mirroring Step 9. Final residual would drop another ~600 LOC to **~50 LOC** — actually achieving the audit's "~100-LOC routing shell" target. **Decision deferred to lead in §9.**

5. **`control_station` + `extension_guide` MCP prompts stay in universe_server.py.** Per §2.5: they're already as small as possible; extracting them doubles the LOC. **Confirmed: leave in universe_server.py.**

6. **`main()` daemon entrypoint stays.** Owns the `mcp.run()` call. Cannot move.

7. **Dependency surface inversion:** today, every Step-1-9 submodule lazy-imports from universe_server.py for these helpers. After Step 10, they all lazy-import from engine_helpers.py. This INVERTS the dependency direction — engine_helpers.py becomes the foundation, universe_server.py becomes a pure routing/wrapper module. The `extensions()` body exception (point #4) is the last non-shell content blocking the full inversion.

8. **Pre-commit canonical-vs-plugin parity check** — same as previous steps. Run `python packaging/claude-plugin/build_plugin.py`.

9. **Sequencing constraint.** Step 10 strictly after Step 9 (Step 9's lazy imports point at universe_server.py preamble; Step 10 retargets them to engine_helpers.py).

10. **Module docstring** carries the audit + decomposition history + the inversion note (engine_helpers.py is the new foundation).

---

## 7. Total LOC moved estimate

| Block | LOC moved to engine_helpers.py |
|---|---|
| Upload-whitelist trio (L353-L437) | ~85 |
| Public action ledger trio (L451-L506) | ~56 |
| Storage + error formatters (L716-L832) | ~117 |
| Module comment blocks + section banners | ~10 |
| **Total moved out of universe_server.py** | **~268** |
| Back-compat re-export block added to universe_server.py | ~20 |
| `_warn_if_no_upload_whitelist()` lazy-import + call preserved | ~3 |
| **Net reduction in universe_server.py** | **~245** |
| New `tinyassets/api/engine_helpers.py` size | **~350** (with imports + module docstring) |

**Smallest extraction by net LOC reduction (~245 vs Step 9's ~2,959).** But largest by test-patch impact and dependency-graph re-routing.

---

## 8. Concrete Step 10 implementation plan

Estimated wall time: **120-180 min** (smallest LOC extraction; largest cross-module lazy-import retargeting; 13-26 test-patch mirror additions).

1. **Confirm Steps 8 + 9 landed.** Both must SHIP before Step 10 starts.
2. **AST scan for external symbol set.** Confirm no preamble-engine-helper symbol is referenced from outside the L353-L832 range (excluding the cross-module re-export shims at L184-L350).
3. **Verify `_warn_if_no_upload_whitelist()` is the only import-time side effect** in the moved range (no other module-level function calls).
4. **Create `tinyassets/api/engine_helpers.py`:**
   - Module docstring referencing audit + extraction date + the source ranges + dependency-inversion note.
   - Imports: `from workflow.api.helpers import _base_path` + `from workflow.catalog import get_backend, StorageBackend` + `from workflow.storage import DirtyFileError` + std-lib + typing + `logging.getLogger("universe_server.engine_helpers")`.
   - Move L353-L437 verbatim (upload-whitelist trio).
   - Move L451-L506 verbatim (public action ledger trio + section banner).
   - Move L716-L832 verbatim (storage + error formatters).
5. **Update `tinyassets/universe_server.py`:**
   - Delete L353-L437 (upload-whitelist trio).
   - Delete L451-L506 (ledger trio).
   - Delete L716-L832 (storage + error formatters).
   - **Reverse-order deletion recommended** (highest line ranges first).
   - Add back-compat shim block (~11 symbols re-exported).
   - Replace L437 module-level call with: `from workflow.api.engine_helpers import _warn_if_no_upload_whitelist; _warn_if_no_upload_whitelist()`.
6. **Update Steps 1-9 lazy imports.** For every lazy import of the form `from workflow.universe_server import _current_actor, ...`, change source to `from workflow.api.engine_helpers import _current_actor, ...`. Touch ~50-80 sites across 9 submodules. Mechanical sed-style.
7. **Test edits expected.** Add mirror patches to 5 test files:
   - `test_branch_name_resolution.py` — add `patch("workflow.api.engine_helpers._current_actor", ...)` mirror at L30 + L99.
   - `test_build_branch_summary_response.py` — add `patch("workflow.api.engine_helpers._storage_backend", ...)` at L272 + L329 + L373 + L420; add `patch("workflow.api.engine_helpers._current_actor", ...)` at L273.
   - `test_describe_branch_approval.py` — add `patch("workflow.api.engine_helpers._current_actor", ...)` at L70.
   - `test_run_branch_failure_taxonomy.py` — add mirror at L123 + L274 + L504.
   - `test_run_branch_version.py` — add mirror `monkeypatch.setattr(eh, "_current_actor", ...)` at L311 + L337 (importing `eh = workflow.api.engine_helpers`).
8. **Run `python packaging/claude-plugin/build_plugin.py`** to sync plugin runtime mirror.
9. **Verification:**
   - `pytest tests/test_branch_name_resolution.py tests/test_build_branch_summary_response.py tests/test_describe_branch_approval.py tests/test_run_branch_failure_taxonomy.py tests/test_run_branch_version.py -q` → green.
   - `pytest -q` → full suite green (essential — Step 10 retargets ~50-80 lazy imports across all 9 prior submodules).
   - `ruff check tinyassets/api/engine_helpers.py tinyassets/universe_server.py tinyassets/api/*.py` → clean.
   - **Visual check:** `git diff tinyassets/universe_server.py | grep -c "^-def _"` should equal **11** (3 upload-whitelist + 3 ledger trio + 5 storage/formatter).
   - **Plugin parity:** `diff -r tinyassets/ packaging/claude-plugin/.../tinyassets/` → empty.

**Files in eventual Step 10 SHIP handoff:**
- `tinyassets/api/engine_helpers.py` (NEW, ~350 LOC — smallest single-file extraction)
- `tinyassets/universe_server.py` (~268 LOC removed + ~20 re-export added + ~3 lazy-import preserve = net ~−245)
- `tinyassets/api/{runs,evaluation,runtime_ops,market,branches,universe,wiki,status,helpers}.py` — touched for ~50-80 lazy-import retargets (mechanical)
- `tests/test_api_engine_helpers.py` (NEW, 30-50 tests recommended — preamble helpers were never tested in isolation)
- 5 existing test files with monkeypatch-target mirror additions
- `packaging/claude-plugin/.../tinyassets/api/engine_helpers.py` (NEW mirror)
- `packaging/claude-plugin/.../tinyassets/universe_server.py` (mirror)
- `packaging/claude-plugin/.../tinyassets/api/*.py` (mirrors with retargeted lazy imports)

15-25 files, +400 / −250 LOC net (one-step view); the lazy-import retargets across submodules are LOC-neutral (sed-style replacements).

---

## 9. Decision asks for the lead

1. **Lazy-import retarget vs leave-pointing-at-universe_server.** See §3.2 + §6.2. Recommend retarget (50-80 mechanical edits across 9 submodules) for clean leaf-module extraction. Alternative leaves all lazy imports pointed at universe_server.py (which re-exports from engine_helpers.py) — works, but extra module hop and persistent visual coupling.

2. **Step 11 for `extensions.py`?** See §6.4. The `extensions()` body is ~600 LOC of dispatch logic — same shape as `universe()`. Extracting via Pattern A2 would drop the residual to **~50 LOC**, finally hitting the audit's "~100-LOC routing shell" target. Trade-offs:
   - **Pro:** Achieves the audit's stated goal. universe_server.py becomes pure routing/wrappers.
   - **Pro:** Symmetry with universe.py extraction (Step 9).
   - **Con:** `extensions()` has 80+ keyword args (vs universe's 23). Pattern A2 wrapper preservation is ~120 LOC of decorator + signature.
   - **Con:** Step 11 would be ~150 min wall time on top of Steps 8/9/10 (~6-8 hours total decomp work).
   **Recommend: yes, plan Step 11 as the 4th post-original-8-step extraction.** But do not block Steps 8/9/10 on the Step 11 decision — they ship cleanly without it.

3. **`control_station` + `extension_guide` placement.** See §2.5. Recommend leaving them in universe_server.py — extracting doubles the LOC count for purely cosmetic gain. Confirm.

4. **`_warn_if_no_upload_whitelist()` import-time side-effect.** See §3.5. Recommend Option B (preserve call at universe_server.py module-load via lazy-import). Confirm.

5. **Test edit budget.** 13-26 line additions across 5 test files. Mechanical mirror patches alongside existing `us.X` patches. Confirm acceptable (alternative: change engine_helpers.py to look up names via universe_server, defeating extraction).

6. **Multi-range deletion (3 sub-ranges) — reverse-order edit.** Mirror Step 9's pattern (5 sub-ranges). Recommend reverse-order deletion (L832 → L716 → L506 → L451 → L437 → L353) to preserve line numbers during edit.

7. **Audit-target reaffirmation.** Step 10 lands the dependency-graph inversion: engine_helpers.py becomes the foundation; universe_server.py becomes a pure routing/wrapper module. Final residual after Step 10: **~650 LOC** (extensions() body ~600 + 6 wrapper preservations ~150 + shim block + main + 2 @mcp.prompt registrations). With Step 11 (extensions.py extraction), residual drops to **~50 LOC** — finally hits the audit target.

---

## 10. Cross-prep summary (Steps 1-10 combined, projected)

After Step 10 lands:

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
| Step 10 (this prep) | `engine_helpers.py` | ~245 | **~1,900** |
| **Subtotal after Step 10** | 8 new + 1 extended | ~12,114 | **~1,900** |

Step 10 unlocks the dependency-graph inversion. universe_server.py at ~1,900 LOC contains: 6 Pattern A2 wrappers (~150 LOC), `extensions()` body + wrapper (~600 LOC), 2 @mcp.prompt registrations (~30 LOC), `main()` (~50 LOC), cross-module re-export shims (~315 LOC), Step-1-10 back-compat shims (~200 LOC), imports + setup (~150 LOC), `@mcp.custom_route("/")` health-check (~20 LOC), padding/banners (~385 LOC).

**With Step 11 (extensions.py extraction), residual drops to ~1,300 LOC** (extensions() body + wrapper extracted = -600 LOC saved + 80-LOC wrapper preserved). Add cleanup of redundant shim blocks (~600 LOC of cross-module re-exports become unnecessary once all consumers retarget) → **~700 LOC final.** Still ~7× audit's 100-LOC target but ~20× smaller than baseline.

The audit's "~100-LOC routing shell" is achievable only if universe_server.py becomes a pure FastMCP-app + main() + thin wrapper module with NO re-export shims. That requires retargeting every test import in the codebase from `workflow.universe_server` to the new submodule paths — mechanical but extensive (~150-200 test-file edits). **That cleanup is OUT OF SCOPE for Step 10** — propose as future "Step 11+ retarget sweep" if/when the host wants the final cleanup pass.

All 10 steps remain pure refactor — no behavior change. The decomposition's stated goal of "make universe_server.py readable + composable" is fully met.
