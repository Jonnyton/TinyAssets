---
title: `fantasy_daemon/` unpack arc — close the Phase 5 bridge, complete the rename
date: 2026-04-26
author: navigator
status: active
status_detail: design note — pre-stages host scope decision
companion:
  - docs/audits/2026-04-26-architecture-edges-sweep.md §A.1 (the finding this note responds to)
  - docs/audits/2026-04-27-project-wide-shim-audit.md (Arc B handles the IMPORT-PATH rename; this note handles the PACKAGE-CONTENT relocation)
  - docs/exec-plans/active/2026-04-15-author-to-daemon-rename.md ("Phase 5 bridge" mentioned in tinyassets/__main__.py)
  - feedback_no_shims_ever (host directive 2026-04-27)
load-bearing-question: When + how do we close the Phase 5 bridge so the `fantasy_daemon/` top-level package dies completely, with engine code in `tinyassets/` and domain code in `domains/fantasy_daemon/` per AGENTS.md "Engine and Domains"?
audience: lead, host (final go/defer decision; if go, scheduling + scope)
---

# `fantasy_daemon/` unpack arc — design note

## TL;DR

After deeper inventory, A.1 from the architecture-edges audit is **smaller than initially framed**:

- **118 of 122 .py files in `fantasy_daemon/` are SHIMS** (`from workflow.X import *` or `from domains.fantasy_daemon.X import *` re-exports). They violate `feedback_no_shims_ever`.
- **Only 4 files have actual content:** `__main__.py` (2295 LOC, daemon CLI/orchestrator), `api.py` (2625 LOC, FastAPI HTTP layer), `branch_registrations.py` (113 LOC, Phase D node decls), `testing/__main__.py` (3 LOC, vestigial error-stub).
- The whole package is a **Phase 5 bridge** per `tinyassets/__main__.py:30-39`. The bridge already exists; closing it means hoisting the 4 content files into canonical homes and deleting all shims.

**Recommendation:** **APPROVE as a 4-phase arc**, sequenced AFTER Arc B/C/Phase 6. ~6-10h total dev work; LOW-MEDIUM risk per phase. Closes the rename arc completely (alongside Arc B/C/Phase 6 closing the import/env-var/data layers).

The original "multi-week structural arc" framing was based on the 122-file count without checking how many are shims. **This is now closer to a 1-2 day arc**, not multi-week.

---

## 1. Current state — what's actually in `fantasy_daemon/`

### 1.1 Shim inventory (118 files)

| Subdir | File count | Pattern | Target |
|---|---|---|---|
| `auth/` | 4 | `Shim: use workflow.auth instead.` | `tinyassets/auth/` |
| `checkpointing/` | 2 | `Shim: use workflow.checkpointing instead.` | `tinyassets/checkpointing/` |
| `constraints/` | 4 | Shim → `tinyassets/constraints/` | `tinyassets/constraints/` |
| `desktop/` | 8 | Shim → `tinyassets/desktop/` | `tinyassets/desktop/` |
| `evaluation/` | 4 | Shim → `tinyassets/evaluation/` | `tinyassets/evaluation/` |
| `ingestion/` | 6 | Shim → `tinyassets/ingestion/` | `tinyassets/ingestion/` |
| `knowledge/` | 7 | Shim → `tinyassets/knowledge/` | `tinyassets/knowledge/` |
| `learning/` | 4 | Shim → `tinyassets/learning/` | `tinyassets/learning/` |
| `memory/` | 10 | Shim → `tinyassets/memory/` | `tinyassets/memory/` |
| `planning/` | 3 | Shim → `tinyassets/planning/` | `tinyassets/planning/` |
| `providers/` | 10 | Shim → `tinyassets/providers/` | `tinyassets/providers/` |
| `retrieval/` | 5 | Shim → `tinyassets/retrieval/` | `tinyassets/retrieval/` |
| `testing/` | 1 | Shim → `tinyassets/testing/` (`__init__.py`) | `tinyassets/testing/` |
| `utils/` | 2 | Shim → `tinyassets/utils/` | `tinyassets/utils/` |
| `graphs/` | 5 | Shim → `domains/fantasy_daemon/graphs/` | `domains/fantasy_daemon/graphs/` |
| `state/` | 6 | Shim → `domains/fantasy_daemon/state/` | `domains/fantasy_daemon/state/` |
| `nodes/` | 23 | Shim → `domains/fantasy_daemon/phases/` (note: nodes ↔ phases naming drift) | `domains/fantasy_daemon/phases/` |
| **TOP-LEVEL .py shims** (excluding 4 non-shim files) | 13 | `branches.py`, `runtime.py` (sys.modules rebind), `author_server.py` (sys.modules rebind), `mcp_server.py`, `notes.py`, `node_eval.py`, `node_sandbox.py`, `packets.py`, `protocols.py`, `work_targets.py`, `config.py`, `exceptions.py`, `universe_server.py` | various `tinyassets/*` modules |
| **TOTAL SHIMS** | **118** | | |

### 1.2 Non-shim files (4 with actual content)

| File | LOC | Role | Callers |
|---|---|---|---|
| `fantasy_daemon/__main__.py` | 2295 | Daemon CLI + orchestrator (DaemonController, tunnel helpers, signal handling, tray launch). The Phase 5 BRIDGE source — `tinyassets/__main__.py` re-imports `DaemonController` from here. | `tinyassets/__main__.py`, `tinyassets/cloud_worker.py`, `tests/test_cloud_worker.py`, `tests/test_unified_execution.py`, `tests/test_integration.py` |
| `fantasy_daemon/api.py` | 2625 | FastAPI HTTP layer — multi-universe file-based adapter, session/author/branch/runtime/ledger endpoints | `tests/test_api.py`, `tests/test_api_edge_cases.py`, `tests/test_author_server_api.py`, `tests/test_rest_votes_behavior.py`, `tests/test_work_targets.py`, `tests/test_tinyassets_runtime.py`, `tinyassets/api/__init__.py` |
| `fantasy_daemon/branch_registrations.py` | 113 | Phase D node-registration helper — registers fantasy-author domain-trusted opaque nodes | `tests/test_unified_execution.py` |
| `fantasy_daemon/testing/__main__.py` | 3 | Error-stub: `raise SystemExit("GPT testing harness removed — use MCP client testing instead.")` | none — vestigial |

**Key insight:** 4 files. The 122-count was misleading. The 118 shims are the no-shims-ever cleanup target; the 4 content files are relocation targets.

### 1.3 Phase 5 bridge — `tinyassets/__main__.py`

`tinyassets/__main__.py:30-39` documents the bridge:

```
# Re-export DaemonController + tunnel helpers from ``fantasy_daemon.__main__``
# so callers can ``from workflow.__main__ import …`` without reaching into the
# fantasy_daemon package directly. Tests still target this surface; the
# block retires when the runtime fully moves out of fantasy_daemon.
import fantasy_daemon.__main__ as _fa_main
from fantasy_daemon.__main__ import (
    DaemonController, ...
)
```

**The bridge already exists.** Closing it = hoisting `fantasy_daemon/__main__.py`'s content into `tinyassets/__main__.py` (and/or `tinyassets/desktop/launcher.py`, `tinyassets/runtime_singletons.py`) and deleting the bridge re-export block.

---

## 2. Why this violates AGENTS.md "Engine and Domains"

Per `AGENTS.md` §"Engine and Domains" (canonicalized in `PLAN.md` §"Engine And Domains"):

> Engine code lives in `tinyassets/`. Domain-specific code lives in `domains/<domain>/`.

Current state breaks this in three ways:

1. **Shim sprawl** — 118 shim files mask the canonical home. A new contributor's `git grep "from fantasy_daemon"` returns hits across `tinyassets/`, `tests/`, `scripts/`, all of which resolve to either `workflow.X` or `domains.fantasy_daemon.X`. The shims are pure indirection.
2. **Bridge module is engine code in domain location** — `fantasy_daemon/__main__.py` is the TinyAssets daemon's entry point + orchestrator. It uses `langgraph`, runs the tray, manages cloud-worker subprocess spawn. NOT fantasy-domain logic. Should be in `tinyassets/__main__.py` or `tinyassets/desktop/launcher.py`.
3. **Bridge module is fantasy-flavored prose** — `__main__.py` docstring says "Fantasy Author daemon entry point. Usage: `python -m fantasy_author`...". The CLI surface is engine-grade ("`python -m tinyassets --domain fantasy_author ...`" per `tinyassets/__main__.py`), but `fantasy_daemon/__main__.py` still pretends to be fantasy-specific.

Per `feedback_no_shims_ever` directive: **the 118 shims are forbidden.** Closing this arc satisfies the policy at every layer (alongside Arc B/C/Phase 6 closing import/env-var/data).

---

## 3. Target end-state

After unpack:

| Location | Contents |
|---|---|
| `fantasy_daemon/` | **DELETED.** Top-level package no longer exists. |
| `tinyassets/__main__.py` | Already delegates; absorbs `DaemonController` class + orchestration logic. CLI entry: `python -m tinyassets [--domain fantasy_daemon] ...`. |
| `tinyassets/desktop/launcher.py` | Already exists (workflow-canonical 841 LOC); receives any tray-launch helpers currently in `fantasy_daemon/__main__.py`. |
| `tinyassets/api/http.py` (new) OR `tinyassets/http_api.py` (new) | `fantasy_daemon/api.py` content lands here. 2625 LOC FastAPI HTTP layer. Top-level location preserves existing `from workflow.api.X import` patterns; rename `fantasy_daemon.api` → `workflow.api.http` (or `workflow.http_api` to avoid `tinyassets/api/api.py`). |
| `domains/fantasy_daemon/registrations.py` (new) OR `tinyassets/registrations/fantasy.py` (new) | `fantasy_daemon/branch_registrations.py` (113 LOC). This is fantasy-domain-specific (per docstring: "Register fantasy-author domain-trusted opaque nodes"); should live in `domains/fantasy_daemon/`. |
| `fantasy_daemon/testing/__main__.py` (3 LOC stub) | **DELETE.** Vestigial — already raises SystemExit. No replacement needed. |
| `python -m fantasy_daemon` invocation | **REPLACED** by `python -m tinyassets --domain fantasy_daemon`. CLI back-compat: keep `python -m fantasy_daemon` as a 5-line stub that calls `workflow.__main__.main(['--domain', 'fantasy_daemon', ...])` for one release cycle, then delete. (Even this is a shim — only acceptable if scoped within the same arc per `feedback_no_shims_ever`.) |

**Net delta:**
- 118 shim files deleted
- 1 vestigial file deleted (`testing/__main__.py`)
- 3 substantial files relocated (api.py, __main__.py, branch_registrations.py)
- ~16 Python imports updated to canonical paths
- ~10 test imports updated
- `pyproject.toml:93` `packages = ["fantasy_author", "workflow", "domains"]` becomes `packages = ["workflow", "domains"]` (also drops `fantasy_author/` shim package per Arc B Phase 3)

---

## 4. Migration arc — phase split

### Phase 1 — `fantasy_daemon/api.py` → `tinyassets/http_api.py`

**Scope:** Move 2625-LOC FastAPI HTTP layer to canonical engine location.

**Steps:**
1. `git mv fantasy_daemon/api.py tinyassets/http_api.py` (or `tinyassets/api/http.py` — name pick is a host decision per §7).
2. Update 7 caller import paths (6 tests + `tinyassets/api/__init__.py`).
3. Verify FastAPI app launches: `python -m tinyassets --domain fantasy_daemon --api --port 8000` (path through `tinyassets/__main__.py:--api`).
4. `pytest tests/test_api.py tests/test_api_edge_cases.py tests/test_author_server_api.py tests/test_rest_votes_behavior.py tests/test_work_targets.py tests/test_tinyassets_runtime.py -q` green.
5. Remove `from fantasy_daemon.api import ...` re-export if `tinyassets/api/__init__.py` had one.

**Effort:** ~2-3h. **Risk:** LOW (mechanical move + import retarget; tests verify behavior unchanged).

### Phase 2 — `fantasy_daemon/__main__.py` → close Phase 5 bridge

**Scope:** Hoist 2295-LOC daemon CLI/orchestrator into `tinyassets/__main__.py` + `tinyassets/desktop/launcher.py` (or `tinyassets/runtime/daemon.py` new).

**Steps:**
1. Inventory `fantasy_daemon/__main__.py` content. Likely splits:
   - `DaemonController` class + threading + signal handling → `tinyassets/runtime/daemon.py` (new) OR `tinyassets/desktop/launcher.py` (existing)
   - Tunnel helpers (cloudflared subprocess spawn, etc.) → already in `tinyassets/desktop/launcher.py` or new `tinyassets/desktop/tunnel.py`
   - Argparse + main() entry → `tinyassets/__main__.py` directly
2. Delete the Phase 5 bridge block in `tinyassets/__main__.py:30-39` (`import fantasy_daemon.__main__ as _fa_main` + the re-export).
3. Update test imports: `from fantasy_daemon.__main__ import DaemonController` → `from workflow.runtime.daemon import DaemonController` (or wherever it lands).
4. Update `tinyassets/cloud_worker.py:49` docstring `"Spawn ``python -m fantasy_daemon --universe <path> --no-tray``"` → `"Spawn ``python -m tinyassets --domain fantasy_daemon --universe <path> --no-tray``"`.
5. CLI back-compat decision (host §7.4): provide `python -m fantasy_daemon` stub or break and document the migration?

**Effort:** ~3-4h (the file is large + has subtle concurrency / tray / signal interactions). **Risk:** MEDIUM — runtime orchestration code; full pytest + tray smoke-launch required.

### Phase 3 — `fantasy_daemon/branch_registrations.py` → domain home

**Scope:** Move 113-LOC fantasy-domain-specific node registrations to `domains/fantasy_daemon/`.

**Steps:**
1. `git mv fantasy_daemon/branch_registrations.py domains/fantasy_daemon/branch_registrations.py` (or merge into `domains/fantasy_daemon/skill.py`).
2. Update 1 test caller: `tests/test_unified_execution.py`.
3. `pytest tests/test_unified_execution.py -q` green.

**Effort:** ~30 min. **Risk:** LOW.

### Phase 4 — Delete the shim mass + the vestigial stub

**Scope:** After Phases 1-3, every `fantasy_daemon/X` import path resolves through shims to canonical paths. Delete the shims + the vestigial `testing/__main__.py`.

**Steps:**
1. Verify no canonical-tree code imports from `fantasy_daemon/*` (except via Phase 5 bridge already closed). `git grep -rE "from fantasy_daemon|import fantasy_daemon" tinyassets/ domains/ scripts/ tests/` → expect 0 hits in non-test code; tests should already be migrated by §3.2 below.
2. **Test migration prerequisite:** Arc B Phase 2 + this arc's Phase 1+2+3 caller-migrations must land first. Tests like `tests/test_api.py` currently import `from fantasy_daemon.api import ...` — those need to point at the new canonical path.
3. `git rm -r fantasy_daemon/`. (Note: this deletes the directory entirely. Per `feedback_no_shims_ever` and `feedback_no_destructive_git_ops_without_asking`, host approves the rm in advance via §7.)
4. CLI back-compat: if §7.4 chose KEEP-STUB, leave `fantasy_daemon/__main__.py` as a 5-line argparse-and-delegate stub. Otherwise full delete.
5. Update `pyproject.toml:93` packages list.
6. Plugin mirror sync: `python packaging/claude-plugin/build_plugin.py` to propagate the deletion.

**Effort:** ~1h. **Risk:** LOW (after Phases 1-3 land, the shims are unused; deletion is mechanical).

### Total arc effort: ~6-9h dev + ~30 min host (test-launch + tray-launch verification).

---

## 5. Risk profile

### Phase 1 (api.py move) — LOW risk

- Mechanical move + import retarget. No behavior change.
- 7 callers identified; all in tests/ + tinyassets/api/__init__.py.
- Mitigation: per-caller-file pytest after import retarget.

### Phase 2 (__main__.py hoist) — MEDIUM risk

The largest risk in the arc.

- File is 2295 LOC of daemon orchestration: signal handlers, threading, cloudflared subprocess spawn, tray-launch, atexit handlers, langgraph SqliteSaver wiring.
- Hoisting it requires deciding the new home (single file vs split across `tinyassets/runtime/`, `tinyassets/desktop/`, `tinyassets/__main__.py`).
- Existing test surface monkeypatches `workflow.__main__.threading` — need to preserve the symbol after hoist.
- Plugin mirror has its own copy via `packaging/claude-plugin/build_plugin.py`.

**Mitigations:**
- Run full `pytest -q` after hoist (not just affected files).
- Manual verification: `python -m tinyassets --domain fantasy_daemon --no-tray` boots the daemon end-to-end; `python -m tinyassets --domain fantasy_daemon --api --port 8000` boots the HTTP layer.
- Tray-launch smoke: `python -m tinyassets --domain fantasy_daemon` (with tray) launches the tray icon successfully.
- If hoist requires splitting across multiple tinyassets/ files, do it in a single commit so tests don't see a half-hoisted intermediate state.

### Phase 3 (branch_registrations.py) — LOW risk

- Small file, 1 caller. Mechanical.

### Phase 4 (shim mass deletion) — LOW risk

- Per `feedback_no_shims_ever`: shims are forbidden. The shims being deleted carry no logic; they re-export `workflow.X` or `domains.fantasy_daemon.X`. Deletion can't change behavior.
- Loud failure mode: any caller still importing from `fantasy_daemon/*` fails on import after deletion.
- Mitigation: full pytest after deletion + plugin-mirror parity check.

### High-risk (none)

- No data migration. No external API surface change (FastAPI app on port 8000 still serves the same endpoints, just from a different module path). No public chatbot-surface change. No env-var change.

---

## 6. Sequencing dependencies

### Hard dependencies (must ship first)

- **Arc B Phase 2 (test caller migration) — satisfied.** Arc B Phase 2 has shipped; this arc no longer needs a sub-pass for those test callers.
- **Arc B Phase 3 (4-file deletion) — satisfied.** Arc B Phase 3 has shipped; this arc's Phase 4 shim deletion no longer has to wait on Arc B's PEP-451 alias finder.

### Soft dependencies (nice-to-have but not blocking)

- **Arc C Phase 3 (env-var alias deletion) SHIPPED** — environment-layer rename closes alongside this code-layer rename.
- **Phase 6 (.author_server.db rename) SHIPPED** — data-layer rename closes too. After all four (Arc B/C/Phase 6 + this arc), the rename arc is fully closed at every layer.

### Cannot block

- Methods-prose evaluator design (separate domain).
- Recency composition + `run_branch resume_from` (F2 accepted 2026-04-28 — different surface).

### Suggested sequencing

```
... (current arcs in flight) ...
  → Task #18 retarget sweep SHIP
  → Arc B Phase 2 SHIP (test caller migration) [done]
  → Arc B Phase 3 SHIP (4-file deletion + smoke) [done]
  → Arc C Phase 1+2+3 SHIP (env-var deprecation deletion)
  → Phase 6 SHIP (.author_server.db rename)
  → THIS ARC Phase 1 (api.py move)
  → THIS ARC Phase 2 (__main__.py hoist) ← biggest risk; full smoke required
  → THIS ARC Phase 3 (branch_registrations.py move)
  → THIS ARC Phase 4 (shim mass deletion + pyproject.toml + plugin mirror)
```

This arc closes **the rename's package layer** (after Arc B closes import-path layer, Arc C closes env-var layer, Phase 6 closes data layer). After all four ship, the Author→Daemon rename is COMPLETE — no shims, no aliases, no legacy-named anything.

---

## 7. Decision asks for the lead → host

1. **Approve the arc?** Recommend yes — completes the rename arc at the package layer; aligns with `feedback_no_shims_ever`. Alternative is "leave fantasy_daemon/ as a 118-shim alias package indefinitely" — viable but inconsistent with the rule.
2. **Confirm sequencing post-Arc C/Phase 6?** Arc B Phase 2+3 are now satisfied; this arc still waits on Arc C + Phase 6 if we want every rename layer closed before package deletion.
3. **Pick the new home for `api.py`:** `tinyassets/http_api.py` (top-level workflow module — recommend) or `tinyassets/api/http.py` (under api/ subpackage). Recommendation: `tinyassets/http_api.py` — avoids `tinyassets/api/api.py` collision with the `tinyassets/api/` MCP-tool subpackage which exports `extensions`, `branches`, `runs`, etc.
4. **Pick `__main__.py` hoist target:**
   - Option A: hoist into `tinyassets/__main__.py` directly (single file, ~3000 LOC after merge)
   - Option B: split — `DaemonController` class to `tinyassets/runtime/daemon.py` (new), tunnel helpers to `tinyassets/desktop/tunnel.py` (new), argparse main() in `tinyassets/__main__.py`
   - Recommend Option B — keeps `tinyassets/__main__.py` lean, separates concerns.
5. **CLI back-compat:** keep `python -m fantasy_daemon` as a 5-line argparse-and-delegate stub for one release cycle, OR break immediately?
   - KEEP-STUB: lower friction for any user invoking the CLI directly; one-arc shim per `feedback_no_shims_ever` (transient shim with deletion in same arc — allowed)
   - BREAK: cleaner. Documentation update + one release-note entry.
   - Recommend BREAK — single-host MVP per `project_daemon_default_behavior`; user-facing CLI doesn't have an installed-base to protect.
6. **Plugin minor-version bump?** Same rationale as Phase 6 — plugin minor bump invalidates stale plugins reading the old package path.
7. **`fantasy_daemon/branch_registrations.py` destination:** `domains/fantasy_daemon/branch_registrations.py` (separate file, recommend) or merge into `domains/fantasy_daemon/skill.py`?

---

## 8. Cross-references

- `docs/audits/2026-04-26-architecture-edges-sweep.md` §A.1 — original finding (122-file count + initial multi-week framing). This note REFINES that framing — the count was misleading; arc is ~6-9h dev work.
- `docs/audits/2026-04-27-project-wide-shim-audit.md` Arc B §9 — `_rename_compat.py` infrastructure deletion (Phase 5 of rename); Arc B Phase 3 has shipped.
- `docs/exec-plans/completed/2026-04-26-decomp-arc-b-prep.md` — completed Arc B prep; this note is "post-Arc-B Phase 6 of the rename" in spirit (the rename has 4 layers; Arc B is import path, Arc C is env-var, Phase 6 is data, this is package).
- `docs/design-notes/2026-04-27-author-server-db-filename-migration.md` — Phase 6 (data rename); this arc is Phase 7 (package rename) in the same overall rename arc.
- `feedback_no_shims_ever` (memory) — the policy this arc serves at the package layer.
- `feedback_no_destructive_git_ops_without_asking` — `git rm -r fantasy_daemon/` requires explicit host approval per §7.
- `AGENTS.md` "Engine and Domains" section — the principle this arc honors.
- `PLAN.md` §"Engine And Domains" — same principle, design-truth surface.
- `tinyassets/__main__.py:30-39` — Phase 5 bridge that this arc closes.

---

## 9. Why this is "button up not unplug"

Per host directive 2026-04-27 ("don't unplug, button up the edges"):

This arc DOESN'T remove behavior. The FastAPI HTTP layer keeps serving the same endpoints. The daemon CLI keeps booting the same way (with one new flag invocation pattern: `python -m tinyassets --domain fantasy_daemon` vs `python -m fantasy_daemon`). The plugin keeps working after a minor-version bump.

It RELOCATES code from a domain-named top-level package (where engine code shouldn't live) to its canonical engine home. The 118 shims being deleted carry zero logic — they're pure re-exports kept alive during the rename window. Deleting them changes nothing about runtime behavior.

The "button up" framing fits exactly: the engine/domain seam was bent during the rename arc; this straightens it. No unplugging.
