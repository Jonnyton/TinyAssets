---
status: research
---

# Architecture Audit — 2026-04-24

**Skills applied:** `domain-model` (stress-test against PLAN.md + actual domain boundaries) then `improve-codebase-architecture` (ranked findings with seam-level specifics).

Scope: live codebase against current state. Baselines: `2026-04-19-modularity-audit.md`, `2026-04-19-project-folder-spaghetti.md`. PLAN.md §Module Layout is the target shape all findings are measured against.

---

## PLAN.md target shape (reference)

Per PLAN.md §Module Layout, the committed end-state:

| Target subpackage | Responsibility |
|---|---|
| `tinyassets/api/` | MCP surfaces. Submodules: `api/runs.py`, `api/branches.py`, `api/judgments.py`, `api/goals.py`, `api/wiki.py`. FastMCP `mount()` pattern. No god-modules. |
| `tinyassets/storage/` | Bounded-context storage layers per context. Shared `_connect()` + migrations in `__init__.py`. |
| `tinyassets/runtime/` | Run scheduling. Consolidates `runs.py`, `work_targets.py`, `dispatcher.py`, `branch_tasks.py`, `subscriptions.py`. |
| `tinyassets/bid/` | Paid-market mechanics. `node_bid.py`, `execution_log.py`, `settlements.py`. |
| `tinyassets/servers/` | Entry-point shells. Mounts `api/` submodules. `universe_server.py` becomes a routing surface, not action-logic home. |

This is the canonical target. Any proposed fix that doesn't converge toward this shape is wrong even if it reduces line count.

---

## Prior audit verdict: what changed since 2026-04-19

| Finding | 2026-04-19 state | 2026-04-24 state |
|---|---|---|
| §3.1 `universe_server.py` mega-surface | ~8,600 lines | **11,147 lines (+30%)** — accelerating |
| §3.2 `discovery.py` fake plugin boundary | Filesystem-only, shim injected | **FIXED** — entry-points primary, filesystem dev fallback |
| §3.3 `daemon_server.py` mixed contexts | 3,200 lines | **3,289 lines** — 1,225 lines migrated to `tinyassets/storage/`; stalled |
| Spaghetti #10: `tinyassets/api/` mostly empty | Empty shell | **Still one file** — domain import violation added (new) |
| Spaghetti #9: `runs.py` + `work_targets.py` flat siblings | Flat | **Unchanged** — `tinyassets/runtime/` subpackage does not exist |

§3.2 closed. Everything else open. §3.1 growing faster than it's being addressed.

---

## Module size map (current)

```
tinyassets/ root flat modules (33 .py files):
  universe_server.py       11,147  <- 44% of root flat total
  daemon_server.py          3,289  <- R7 split in-flight
  runs.py                   1,843
  graph_compiler.py         1,167
  branches.py                 827
  work_targets.py             820
  node_eval.py                529
  git_bridge.py               463
  branch_tasks.py             444
  cloud_worker.py             425
  protocols.py                417
  node_sandbox.py             382
  mcp_server.py               325
  dispatcher.py               313
  runtime.py                   71  <- NAME CONFLICT with planned runtime/ subpackage
  [18 more below 260 lines]

tinyassets/ subpackages (conformant per PLAN.md):
  api/__init__.py              93  <- PLAN target, but empty + domain import (violation)
  bid/                   3 files  <- PARTIALLY DONE (conformant shape)
  storage/               4 files, 1,225 LOC  <- IN-FLIGHT (conformant shape)
  [many other conformant subpackages — see §What's clean]
```

---

## Ranked findings

### #1 — `tinyassets/api/__init__.py` imports wholesale from a domain (PLAN.md principle violation)

**Severity: critical. Engine importing from a domain inverts the dependency direction committed in PLAN.md.**

Evidence:
- `tinyassets/api/__init__.py:31`: `from fantasy_author.api import *  # noqa: F401,F403`
- Lines 32–38: explicit re-imports of private names (`_extract_username`, `_load_provider_keys`, `_slugify`) from `fantasy_author.api`
- `fantasy_author` is a compat shim → `fantasy_daemon` → `fantasy_daemon/api.py` (2,625 lines, FastAPI REST app)
- 6 test files import `app` and `configure` from `workflow.api`: `test_api.py`, `test_api_edge_cases.py`, `test_author_server_api.py`, `test_rest_votes_behavior.py`, `test_work_targets.py`, `test_tinyassets_runtime.py`

PLAN.md principle: "Engine = `tinyassets/`. Domains = `domains/<name>/`." The engine's API namespace is currently a wildcard re-export of a domain's 2,625-line FastAPI REST app. Any change to `fantasy_daemon/api.py` silently becomes part of `workflow.api`.

Domain-model diagnosis: the invariant "engine is infrastructure, domains consume from it" is violated in both directions. The engine module re-exports a domain module; tests exercise engine-namespace symbols that are actually domain code. The planned `tinyassets/api/` FastMCP submodules (`api/runs.py` etc.) cannot be built while this shim occupies the namespace.

Note: `tinyassets/api/` is supposed to contain FastMCP MCP sub-apps. `fantasy_daemon/api.py` is a FastAPI REST app. These are different frameworks, different protocols. The shim merges two incompatible API paradigms under one namespace.

Proposed fix:
- Tests that use `workflow.api.app` and `workflow.api.configure` are testing `fantasy_daemon`'s REST surface. Redirect imports to `fantasy_daemon.api` directly.
- `tinyassets/api/__init__.py` becomes empty (or a minimal stub) until MCP submodules are built into it per PLAN.md.
- This is the prerequisite before any `tinyassets/api/` MCP submodule work makes sense.

Files: `tinyassets/api/__init__.py`, `tests/test_api.py`, `tests/test_api_edge_cases.py`, `tests/test_author_server_api.py`, `tests/test_rest_votes_behavior.py`, `tests/test_work_targets.py`, `tests/test_tinyassets_runtime.py`.

Effort: **1–2 days**.

---

### #2 — `universe_server.py`: 11,147 lines at +30%/5-weeks, 3 synchronized copies diverging

**Severity: high. Not converging toward PLAN.md target. Growing faster than the split is being planned.**

Evidence:
- 3 synchronized copies: `tinyassets/universe_server.py`, `packaging/claude-plugin/.../universe_server.py`, `packaging/dist/.../universe_server.py`. Any edit to action logic, a prompt rule, or a hard rule must be applied 3 times manually.
- 6 MCP tools, 57 private `_action_*` handlers, 3 sub-dispatch tables (`_BRANCH_ACTIONS`, `_RUN_ACTIONS` with 9 entries, `_JUDGMENT_ACTIONS` with 7 entries).
- `extensions()` function: 46 parameters. Every new primitive adds another. No machine-readable per-action schema — docstring is the only enforcement.
- 151 deferred `from workflow.X import Y` calls inside function bodies. `from workflow.author_server import get_branch_definition` repeated 18+ times across separate handlers.

PLAN.md target: `tinyassets/servers/` contains the routing shell; `tinyassets/api/` submodules contain action logic. PLAN.md §API And MCP Interface: "No god-modules. The current 10k-line `universe_server.py` is in-flight refactor scope, not the target state."

Immediate high-leverage fix (independent of the full split): single-source `_CONTROL_STATION_PROMPT`. It is a string constant currently copy-pasted across 3 files. Extract to `tinyassets/api/prompts.py`, import in all 3 server copies. Eliminates the 3-copy prompt sync problem today.

Longer-term: extract `_RUN_ACTIONS` handlers → `tinyassets/api/runs.py` (FastMCP sub-app), `_JUDGMENT_ACTIONS` → `tinyassets/api/judgments.py`, branch actions → `tinyassets/api/branches.py`. Mount via `tinyassets/servers/universe_server.py` routing shell. This is the PLAN.md target shape.

Files for prompt extraction: `tinyassets/universe_server.py` + 2 packaging mirrors + new `tinyassets/api/prompts.py`.

Effort: **0.5 days** for prompt extraction. **Multi-week** for full surface split.

---

### #3 — `author_server` rename regression: 70+ call sites on deprecated shim, new handlers adding more

**Severity: high. Migration moving backward. Phase 5 shim disable is blocked indefinitely.**

Evidence:
- `tinyassets/author_server.py` (39 lines): `sys.modules` rebind shim, emits `DeprecationWarning` when `TINYASSETS_DEPRECATIONS=1`.
- `tinyassets/universe_server.py`: 60+ deferred `from workflow.author_server import X` calls. Every `_action_*` handler added in the past 5 weeks uses the deprecated name. The migration is regressing with each new handler.
- `tinyassets/catalog/backend.py`: 10 more `from workflow.author_server import X` (deferred, inside methods).
- `tinyassets/work_targets.py:19`: `from workflow import author_server` at **module level** — activates DeprecationWarning on every import of `work_targets`, even in tests that don't need the warning.
- PLAN.md Design Decisions: "'Author' → 'daemon' rename in flight."

Regression mechanism: new `_action_*` handlers are written by copying existing handler structure, which uses `from workflow.author_server import X`. There is no linter or pre-commit gate blocking new usages. Each new handler deepens the debt.

Proposed fix:
1. Add pre-commit gate: block new `from workflow.author_server` imports (ruff `extend-select` or `forbidden-import` hook). Stop the regression first.
2. Bulk rename in `universe_server.py`: collapse 18 unique `author_server` symbols to module-level imports from `workflow.daemon_server`. Mechanical, but the deferred-import pattern means it must be done per-function (not as a global sed).
3. Migrate `catalog/backend.py` and `work_targets.py` in the same pass.

Files: `tinyassets/universe_server.py`, `tinyassets/catalog/backend.py`, `tinyassets/work_targets.py`, `tinyassets/author_server.py`.

Effort: **2–3 days**.

---

### #4 — `tinyassets/runtime.py` name collides with planned `tinyassets/runtime/` subpackage

**Severity: medium. Blocks PLAN.md §Module Layout commitment for `tinyassets/runtime/` subpackage.**

Evidence:
- `tinyassets/runtime.py` (71 lines): LangGraph singleton container. Module-level refs for non-serializable objects (`MemoryManager`, `OutputVersionStore`, `SeriesPromiseTracker`, `knowledge_graph`, `vector_store`, `raptor_tree`, `embed_fn`, `universe_config`). Has a `reset()` function called by `DaemonController._cleanup()`.
- PLAN.md §Module Layout: `tinyassets/runtime/` is the planned subpackage consolidating `runs.py` (1,843 lines), `work_targets.py` (820), `dispatcher.py` (313), `branch_tasks.py` (444), `subscriptions.py` (161).
- You cannot `mkdir runtime/` without first renaming or moving `runtime.py`. Python package resolution would break.

The singleton container is a distinct concept from run scheduling — it's the daemon's in-process hot context, not the scheduling layer. It belongs in `tinyassets/runtime/singletons.py` (or `tinyassets/runtime/context.py`) once the subpackage exists.

Proposed fix: rename `tinyassets/runtime.py` → `tinyassets/runtime_singletons.py`. Update all callers (`from workflow.runtime import` and `from workflow import runtime`). This is a prerequisite for creating `tinyassets/runtime/`.

Effort: **0.5 days** (rename + caller update). Unblocks the larger `runtime/` consolidation.

---

### #5 — `daemon_server.py`: R7 split stalled at 37%, 23 CREATE TABLE statements remain inline

**Severity: medium. Status structurally unchanged since 2026-04-19 audit.**

Evidence:
- 3,289 lines, 95 functions, 23 `CREATE TABLE` statements in one file.
- Migrated: `storage/accounts.py` (307), `storage/rotation.py` (193), `storage/caps.py` (156), `storage/__init__.py` (569) = 1,225 lines (37%).
- Remaining: branch lifecycle + snapshots (~lines 615–808), request/vote lifecycle (~lines 979–1220), goals/gates/leaderboards (~lines 2816+), search (~lines 3025+).
- PLAN.md target: `storage/universes_branches.py`, `storage/requests_votes.py`, `storage/notes_work_targets.py`, `storage/goals_gates.py`.

Each extraction is independent. Depends on rename migration (#3) being frozen first so the extracted modules import from the correct namespace.

Files per extraction:
- `storage/universes_branches.py` (new): branch CRUD, snapshots, branch_heads
- `storage/requests_votes.py` (new): user_requests, vote_windows, vote_ballots
- `storage/goals_gates.py` (new): goals, gate_claims, leaderboards

Effort: **1–2 weeks** total; each extraction is 2–3 days, independently dispatchable.

---

### #6 — `catalog/backend.py`: storage abstraction layer calling the service layer (inverted dependency)

**Severity: medium. New since prior audit; emerged during Phase 7 dual-write work.**

Evidence:
- `tinyassets/catalog/backend.py` (886 lines): `StorageBackend` protocol implementation.
- 10 deferred `from workflow.author_server import X` inside backend methods for write operations (`save_branch_definition`, `save_goal`, `claim_gate`, `retract_gate_claim`, `_connect`).
- A storage backend (infrastructure) calling a service function (`daemon_server` via the author_server shim) that owns schema + business logic. Storage layer should be called by services, not call them.
- Effect: `sqlite_cached` backend cannot be unit-tested without mocking `author_server` internals.

Fix: after #3 lands, replace author_server calls with direct `daemon_server` calls (or target `storage/` layer calls if R7 split has progressed). Resolve which operations should call the service layer vs. the raw storage layer.

Files: `tinyassets/catalog/backend.py`.

Effort: **1–2 days** after #3 lands.

---

## What's clean (no action needed)

- `tinyassets/discovery.py` — §3.2 resolved. Entry-points + filesystem fallback. No compat aliases in discovery.
- `tinyassets/providers/` — 6 provider files, self-contained. No cross-layer coupling.
- `tinyassets/retrieval/router.py` — no coupling to MCP or service surfaces.
- `tinyassets/context/compaction.py` — clean.
- `tinyassets/evaluation/structural.py` — clean domain module, graceful optional deps (spaCy, ASP).
- `tinyassets/bid/` — partially complete, conformant shape. Verify whether `bid_ledger.py` is a separate gap or already folded into `execution_log.py`.
- `tinyassets/storage/` — partially complete, conformant shape, progressing.
- All other conformant subpackages: `auth/`, `catalog/`, `checkpointing/`, `constraints/`, `context/`, `evaluation/`, `ingestion/`, `knowledge/`, `learning/`, `memory/`, `planning/`, `providers/`, `retrieval/`, `desktop/`, `testing/`, `utils/`.

---

## Recommended dispatch order

| Priority | Task | PLAN.md target | Effort | Depends |
|---|---|---|---|---|
| 1 | Clear domain import from `tinyassets/api/__init__.py`; redirect 6 test files to `fantasy_daemon.api` | `tinyassets/api/` = engine MCP only | 1–2 days | — |
| 2 | Pre-commit gate: block new `from workflow.author_server` imports | Stop rename regression | 0.5 days | — |
| 3 | Single-source `_CONTROL_STATION_PROMPT` → `tinyassets/api/prompts.py` | Eliminate 3-copy drift | 0.5 days | — |
| 4 | Rename `tinyassets/runtime.py` → `tinyassets/runtime_singletons.py` | Unblock `tinyassets/runtime/` | 0.5 days | — |
| 5 | Bulk rename `workflow.author_server` → `workflow.daemon_server` in `universe_server.py`, `catalog/backend.py`, `work_targets.py` | Phase 5 shim disable | 2–3 days | #2 |
| 6 | R7: `storage/universes_branches.py` extraction | `daemon_server.py` split | 2–3 days | #5 |
| 7 | R7: `storage/requests_votes.py` extraction | `daemon_server.py` split | 2–3 days | #5 |
| 8 | R7: `storage/goals_gates.py` extraction | `daemon_server.py` split | 2–3 days | #5 |
| 9 | Extract `_RUN_ACTIONS` → `tinyassets/api/runs.py` (FastMCP sub-app, mounted) | `tinyassets/api/` MCP submodules | 3–5 days | #1, #3, #5 |
| 10 | Extract `_JUDGMENT_ACTIONS` → `tinyassets/api/judgments.py` | `tinyassets/api/` MCP submodules | 3–5 days | #9 |
| 11 | Extract branch actions → `tinyassets/api/branches.py` | `tinyassets/api/` MCP submodules | 3–5 days | #9 |

Items 1–4 are independent and low-risk (1–2 days each). Items 5–8 are mechanical with clear file boundaries. Items 9–11 are the full architectural reshape, blocked on preceding items.

---

## Domain-model corrections to prior draft

The first draft of this audit (before domain-model application) proposed extraction to `tinyassets/mcp_runs.py`, `tinyassets/mcp_judgments.py`, `tinyassets/mcp_extensions.py`. These names are wrong — they don't fit the PLAN.md-committed `tinyassets/api/` submodule layout or the `tinyassets/servers/` server-shell layout. Using wrong names for new files creates a third naming convention alongside the two already in flight.

The first draft also missed:
- Finding #1: `tinyassets/api/__init__.py` domain import — the highest-priority PLAN.md principle violation.
- Finding #4: `tinyassets/runtime.py` naming collision — blocks the `tinyassets/runtime/` subpackage commitment.

Both surfaced by stress-testing proposed fixes against the actual PLAN.md domain model before recommending them.
