# Fantasy Shim Import Audit — Phase 0

**Date:** 2026-04-25
**Scope:** All Python files outside `fantasy_author/`, `fantasy_daemon/`, `fantasy_author_original/`, `domains/` that import `fantasy_author.*`, `fantasy_daemon.*`, or `fantasy_author_original.*`.
**Method:** `git grep -n "from fantasy_author|import fantasy_author|from fantasy_daemon|import fantasy_daemon"` filtered to non-shim paths.
**Total live importers:** 73 references across 25 files.

---

## Summary

| Category | Files | References |
|---|---|---|
| Production | 3 | 9 |
| Tests | 22 | 64 |

Phase 1 target: rewrite all production imports. Tests are lower risk (shim is transparent), but migrate them in Phase 2.

---

## Production Files (Phase 1 — Immediate)

### `tinyassets/__main__.py`

| Line | Current import | Target |
|---|---|---|
| 38 | `import fantasy_author.__main__ as _fa_main` | `import workflow.__main__ as _fa_main` (or remove alias) |
| 39-? | `from fantasy_author.__main__ import (...)` | `from workflow.__main__ import (...)` |
| 173 | `from fantasy_author.__main__ import DaemonController` | `from workflow.__main__ import DaemonController` |

Comment at lines 31–33 explains the alias was intentional back-compat during migration; the comment and the re-export block should be removed together.

### `tinyassets_tray.py`

| Line | Current import | Target |
|---|---|---|
| 374 | `"from fantasy_author.universe_server import mcp; "` (string in exec'd code) | `"from workflow.universe_server import mcp; "` |

This is a runtime `exec()` string, not a static import. Must be updated as a string literal.

### `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/__main__.py`

Mirror of `tinyassets/__main__.py` inside the packaging bundle. Same lines 31, 33, 38, 39, 173.

| Line | Current import | Target |
|---|---|---|
| 38 | `import fantasy_author.__main__ as _fa_main` | `import workflow.__main__ as _fa_main` |
| 39-? | `from fantasy_author.__main__ import (...)` | `from workflow.__main__ import (...)` |
| 173 | `from fantasy_author.__main__ import DaemonController` | `from workflow.__main__ import DaemonController` |

---

## Test Files (Phase 2)

Lower risk: shim transparently resolves to `workflow.*` / `fantasy_daemon.*`. Migrate after production is clean.

| File | Lines | Import pattern | Target module |
|---|---|---|---|
| `tests/test_api.py` | 17 | `from fantasy_daemon.api import (...)` | `from workflow.api import (...)` |
| `tests/test_api.py` | 1417, 1445 | `from fantasy_author import api as api_mod` | `from workflow import api as api_mod` |
| `tests/test_api.py` | 1685 | `from fantasy_daemon.api import app as api_app` | `from workflow.api import app as api_app` |
| `tests/test_api.py` | 2376–2428, 2489, 2519 | `import fantasy_author.api as api_mod` / `from fantasy_author.api import ...` | `import workflow.api as api_mod` |
| `tests/test_api_edge_cases.py` | 15 | `from fantasy_daemon.api import app, configure` | `from workflow.api import app, configure` |
| `tests/test_author_server_api.py` | 10, 171 | `from fantasy_daemon.api import app, configure` / `from fantasy_author.api import configure` | `from workflow.api import ...` |
| `tests/test_import_compatibility.py` | 9, 19 | various `fantasy_author.*` compat checks | Keep as-is (tests the shim itself) |
| `tests/test_integration.py` | 2415 | `import fantasy_author.__main__ as main_mod` | `import workflow.__main__ as main_mod` |
| `tests/test_phase_d_unified_execution.py` | 48, 51, 237–238, 262, 274, 306, 325, 383, 446–447, 479, 524, 532 | `import fantasy_author.*` / `from fantasy_author.*` | `from workflow.*` |
| `tests/test_phase_e_dispatcher.py` | 375, 398, 435 | `from fantasy_author.__main__ import _dispatcher_observe, _dispatcher_startup` | `from workflow.__main__ import ...` |
| `tests/test_phase_f_goal_pool.py` | 590, 602, 632, 666, 681 | `from fantasy_author.__main__ import _try_dispatcher_pick, _finalize_claimed_task` | `from workflow.__main__ import ...` |
| `tests/test_phase_g_node_bid.py` | 1074, 1124, 1160 | `from fantasy_author.__main__ import _try_execute_claimed_node_bid` | `from workflow.__main__ import ...` |
| `tests/test_phase_h_activity_log_parity.py` | 195, 280 | `from fantasy_author.__main__ import DaemonController` | `from workflow.__main__ import DaemonController` |
| `tests/test_research_probe.py` | 154–181 | assertions that `fantasy_author` is NOT imported | Keep as-is (tests shim-free paths) |
| `tests/test_rest_votes_behavior.py` | 28 | `from fantasy_daemon.api import app, configure` | `from workflow.api import app, configure` |
| `tests/test_runtime_status_bridge.py` | 31, 387 | `from fantasy_author.__main__ import DaemonController` / `from fantasy_author.providers import router` | `from workflow.__main__ import ...` |
| `tests/test_task_producers.py` | 62 | `from domains import fantasy_author` | `from domains import fantasy_daemon` |
| `tests/test_work_targets.py` | 19 | `from fantasy_daemon.api import app, configure` | `from workflow.api import app, configure` |
| `tests/test_tinyassets_runtime.py` | 166, 174 | `from fantasy_daemon.api import app` / `from fantasy_daemon.api import configure` | `from workflow.api import ...` |

---

## Excluded / Keep-as-is

- `tinyassets/api/__init__.py` line 8: comment in docstring, not an import
- `scripts/build_shims.py`: shim-builder script — must reference shim names
- `scripts/migrate_imports.py`: migration tool — must reference old names by design
- `tests/test_import_compatibility.py`: tests backward-compat of the shim itself; retire after shim deleted
- `tests/test_research_probe.py`: assertions that certain modules are shim-free; keep until shim deleted

---

## Phase Plan

| Phase | Scope | Gate |
|---|---|---|
| **Phase 0** (this doc) | Audit — enumerate all live importers | Done |
| **Phase 1** | Rewrite 3 production files (`tinyassets/__main__.py`, `tinyassets_tray.py`, packaging mirror) | Full suite green + ruff clean |
| **Phase 2** | Rewrite 22 test files | Full suite green + ruff clean |
| **Phase 3** | Delete `fantasy_author/`, `fantasy_author_original/` shim trees | Confirm zero remaining importers |

Phase 1 is mechanical: every `fantasy_author.__main__` → `workflow.__main__`, every `fantasy_daemon.api` → `workflow.api`. The `tinyassets_tray.py` string-exec case needs special handling (string literal replacement, not AST rewrite).
