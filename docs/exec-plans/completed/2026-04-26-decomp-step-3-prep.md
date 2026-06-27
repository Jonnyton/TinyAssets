---
title: Task #10 prep — tinyassets/api/status.py extraction scope
date: 2026-04-26
author: dev
status: pre-flight scoping (no edits yet)
companion: docs/audits/2026-04-25-universe-server-decomposition.md §4.2 (`status.py`), §8 step 3
target_task: #10 — Extract tinyassets/api/status.py (decomp audit step 3)
gates_on: #8 ships first; #9 land order independent (#10 may go before or after #9).
---

# Task #10 pre-flight scope

Read-only scope for extracting `get_status()` and its support helpers from `tinyassets/universe_server.py` into a new `tinyassets/api/status.py`.

---

## 1. Audit-vs-reality verdict

**Audit estimate (§3.1):** status LOC ~470, line range 12595–13067.

**Reality (current code, 2026-04-26):**
- Status banner at L13564 (`# TOOL 5 — get_status`).
- Banner + design rationale comment block L13564–13589.
- `_policy_hash` helper L13592.
- `@mcp.tool()` decorator L13604.
- `def get_status(...)` L13618.
- End of `get_status` body L13994.
- (Server entry-point banner L13997 — not in scope.)

**Total lines (banner → end of get_status): L13564 → L13994 = 431 LOC.** Audit estimate (~470) was within 10% — slight over. Audit was NOT stale on size.

**Symbol additions since audit:** `sandbox_status` block (L13960) + `missing_data_files` field; both inline in get_status body, not new top-level symbols. Audit boundaries hold.

---

## 2. Symbol enumeration (current line ranges)

### 2.1 Constants
| Symbol | Line | LOC | Notes |
|---|---|---|---|
| `_STALE_FRESH_SECONDS` | 1094 | 1 | **NOT in status section** — at top of file (preamble L1094). Used by `_daemon_liveness`. Stays where it is OR moves with `_daemon_liveness` if that helper is reclassified. |
| `_STALE_IDLE_SECONDS` | 1095 | 1 | Same. |

### 2.2 Helper functions consumed by `get_status`
| Helper | Line | Used by | Move target |
|---|---|---|---|
| `_policy_hash` | 13592 | `get_status` only | **status.py** (no other consumers) |
| `_parse_activity_line` | 3342 | `get_status`, `_action_get_recent_events` (universe.py future home) | **stays** in `helpers.py` or `universe_helpers.py` — multi-consumer |
| `_last_activity_at` | 1098 | `_daemon_liveness` (which is called by status + `_action_control_daemon` "status" subcommand) | **stays** — multi-consumer |
| `_daemon_liveness` | 1287 | `_action_control_daemon` "status" + `get_status` indirectly | **stays** — multi-consumer; lives in universe-engine territory |
| `_action_run_routing_evidence` | 8108 | `extensions get_routing_evidence` action — NOT called by `get_status`! | **NOT in #10** — lives in runs.py (Task #N future) |
| `get_sandbox_status` | imported | `get_status` body L13960 | NOT extracted — already lives in a sibling module (likely `workflow.sandbox_probe` or similar). Confirm location. |
| `inspect_storage_utilization`, `path_size_bytes` | imported | `get_status` body L13837–13838 | NOT extracted — live in `workflow.storage`. |

### 2.3 Public MCP tool
| Symbol | Line | LOC |
|---|---|---|
| `@mcp.tool(...)` decorator | 13604 | ~14 (annotations) |
| `def get_status(...)` | 13618 | ~376 (body, including 5 large blocks: dispatcher config load, endpoint resolution, activity tail parsing, caveats assembly, storage utilization+session boundary, sandbox + missing files, response assembly) |

---

## 3. Cross-references — does #10 depend on #9 symbols (or vice versa)?

**Zero direct overlap.** Verified by grep:
- `get_status` does NOT call any `_wiki_*` helper or the `wiki()` tool.
- `wiki()` does NOT call `get_status` or `_policy_hash`.

**Indirect overlap — both depend on shared #8 helpers** + a few utility functions that live in universe-engine territory (`_parse_activity_line`, `_daemon_liveness`, `_last_activity_at`). These are NOT in #9 scope and NOT in #10 scope; they stay where they are until the bigger universe-engine extraction (audit step 9).

**Order doesn't matter:** #9 and #10 can ship in either order after #8.

---

## 4. FastMCP `mcp` instance — same Pattern A as #8/#9

Same Pattern A question as #9 §4. If #9 already pulled `mcp` to a leaf module, #10 reuses that. If #9 used `from workflow.universe_server import mcp`, #10 does the same.

**No new decision needed for #10** — inherits #9's choice.

---

## 5. Test files importing status symbols (and how)

All via `from workflow.universe_server import ...` — none via `workflow.api.status`:

| Test file | Symbol(s) imported | Count |
|---|---|---|
| `tests/test_get_status_primitive.py:18` | `get_status, mcp` | 1 (top-level) |
| `tests/test_bug029_chain_drain.py` | `get_status` | 3 |
| `tests/test_sandbox_status.py` | `get_status` | 2 |
| `tests/test_sandbox_unavailable.py` | `get_status` | 2 |
| `tests/test_startup_file_probe.py` | `get_status` | 2 |
| `tests/test_storage_inspect.py` | `get_status` | 2 |
| `tests/test_storage_utilization_universe.py` | `get_status` | 4 |
| `tests/test_universe_list_observability.py:17` | `_action_list_universes, get_status` | 1 (mixed; `_action_list_universes` is universe.py territory, not status.py) |

**Total:** ~17 test imports across 8 files, all via `workflow.universe_server`. Audit §7 Strategy 1 (back-compat re-export shim) preserves these unchanged. After #10 lands, `tinyassets/universe_server.py` adds:
```python
from workflow.api.status import get_status  # noqa: F401  back-compat re-export
```
Mostly trivial; `mcp` continues to be re-exported from universe_server.py regardless.

**Notable:** `tests/test_get_status_primitive.py` is THE contract test for the `get_status` shape — referenced in the docstring at L13598 of the canonical (per Task #4 docstring edit). Confirms the test surface is rigorously covered. After #10 lands, this test continues to import via universe_server shim — no edit.

---

## 6. What partially-moved (the helpers-already-extracted lesson)

Searched for evidence that `get_status` or its helpers already shipped to a submodule. **None found.** Status section is fully contiguous in universe_server.py.

The only adjacent partial moves are:
- The 5 helpers in #8 (`_base_path`, etc.) — `get_status` already uses them; after #8 lands they're `helpers.py` imports. No action needed for #10.
- `inspect_storage_utilization`, `path_size_bytes` — already live in `workflow.storage` (imported lazily inside `get_status` body L13836). NOT new movement.

---

## 7. Total LOC moved estimate

| Block | LOC |
|---|---|
| Banner + design rationale (L13564–13589) | ~25 |
| `_policy_hash` (L13592–13602) | ~10 |
| `@mcp.tool` decorator + `get_status` def + body (L13604–13994) | ~390 |
| **Total moved out of universe_server.py** | **~425** |
| Back-compat re-export block added to universe_server.py | ~3 |
| **Net reduction in universe_server.py** | **~422** |
| New `tinyassets/api/status.py` size | **~450** (with imports + docstring) |

**Audit said ~470.** Reality ~450. Within 5% — audit's LOC estimate solid for #10.

---

## 8. Risks the audit didn't anticipate

1. **`_STALE_FRESH_SECONDS` / `_STALE_IDLE_SECONDS` at L1094-1095** are NOT in the status section (they're in the preamble). They support `_daemon_liveness` which is universe-engine territory. **Do NOT move them in #10.** `get_status` doesn't use them directly — only via `_daemon_liveness`, which stays in universe_server.py for now.

2. **Lazy imports inside `get_status` body** — the function does `from workflow.dispatcher import ...` (L13670), `from workflow.storage import inspect_storage_utilization, path_size_bytes` (L13836), `from workflow.sandbox_probe import get_sandbox_status` (or similar — confirm location at L13959). These move WITH `get_status` to status.py. Their target modules stay put — no circular import risk.

3. **`mcp` re-export must remain accessible** at `from workflow.universe_server import mcp` — `tests/test_get_status_primitive.py:18` imports it explicitly. Whatever #9 does for the `mcp` instance, #10 must preserve that import path.

4. **`_action_run_routing_evidence` at L8108 is NOT in #10 scope** despite the name. It's an `extensions get_routing_evidence` handler — runs.py / extensions.py territory. Don't accidentally pull it in.

5. **`tests/test_universe_list_observability.py:17` imports both `_action_list_universes, get_status`** in one statement. After #10 ships, that test continues to work via the universe_server shim, but the import is now satisfying two different submodules through one shim. Not a problem; just observation.

6. **Pre-commit canonical-vs-plugin parity check** — same as #8/#9. Run `python packaging/claude-plugin/build_plugin.py`.

7. **#10 is smaller and more isolated than #9** — could ship before #9 if lead wants the smaller wins first. Audit §8 sequencing recommends #9 → #10 (wiki then status), but technically #10 → #9 is also safe.

---

## 9. Concrete Task #10 implementation plan

Estimated wall time: 30-45 min (smaller than #9, no test edits, contiguous block).

1. **Confirm #8 has landed** (helpers extraction).
2. **Confirm `mcp` instance pattern from #9** (or settle it independently if #10 ships first).
3. **Locate `get_sandbox_status`** import target — grep for `def get_sandbox_status` to confirm it lives at the path L13959 imports from.
4. **Create `tinyassets/api/status.py`:**
   - Module docstring referencing audit + extraction date.
   - Imports: `from workflow.api.helpers import _base_path, _default_universe, _universe_dir` (the 3 it actually uses) + `mcp` per §4.
   - Move L13564–13994 verbatim (banner + `_policy_hash` + `@mcp.tool` + `get_status`).
5. **Update `tinyassets/universe_server.py`:**
   - Delete L13564–13994.
   - Add to back-compat shim block: `from workflow.api.status import get_status  # noqa: F401`.
6. **No test edits required.**
7. **Run `python packaging/claude-plugin/build_plugin.py`**.
8. **Verification:**
   - `pytest tests/test_get_status_primitive.py tests/test_sandbox_status.py tests/test_sandbox_unavailable.py tests/test_storage_inspect.py tests/test_storage_utilization_universe.py tests/test_startup_file_probe.py tests/test_bug029_chain_drain.py tests/test_universe_list_observability.py` → green (~17 imports exercised).
   - `pytest -q` → full suite green.
   - `ruff check tinyassets/api/status.py tinyassets/universe_server.py` → clean.

**Files in eventual #10 SHIP handoff:**
- `tinyassets/api/status.py` (NEW, ~450 LOC)
- `tinyassets/universe_server.py` (~422 LOC removed + ~3 re-export added)
- `packaging/claude-plugin/.../tinyassets/api/status.py` (NEW mirror)
- `packaging/claude-plugin/.../tinyassets/universe_server.py` (mirror)

4 files, +453 / -422 LOC net.

---

## 10. Decision asks for the lead

1. **Sequencing: #9 → #10 or #10 → #9?** Audit recommends #9 first; #10 is smaller and more isolated, would be a faster win. Recommendation: stick with audit order (#9 → #10) since #9 establishes the `mcp` pattern that #10 inherits.
2. **`mcp` instance pattern** — same question as #9 §4. Inherited.
3. **`_STALE_FRESH_SECONDS` / `_STALE_IDLE_SECONDS` constants** — leave at L1094-95 in universe_server preamble (only used by `_daemon_liveness`)? Confirmed yes, they're not status.py concerns.

---

## 11. Cross-prep summary (#8 + #9 + #10 combined)

After all 3 land:

| Step | New file | Net LOC removed from universe_server.py | Cumulative universe_server.py size |
|---|---|---|---|
| baseline | — | — | 14,031 |
| #8 | extends `helpers.py` | ~16 | ~14,015 |
| #9 | `wiki.py` | ~1,360 | ~12,655 |
| #10 | `status.py` | ~422 | ~12,233 |
| **Total** | 1 new + 1 extended | ~1,798 | ~12,233 |

universe_server.py shrinks by ~13% after the 3 steps. Larger reductions land in subsequent audit steps (`branches.py` ~3,282 LOC, `market.py` ~1,813 LOC).

All 3 steps are pure refactor — no behavior change, no test edits required (back-compat shim preserves the 17+ existing test imports).
