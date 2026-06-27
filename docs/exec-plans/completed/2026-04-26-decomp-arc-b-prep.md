---
title: Arc B prep — Author→Daemon rename infrastructure deletion (~406 LOC + caller migration)
date: 2026-04-26
author: navigator
status: completed
completed_on: 2026-05-02
completion_evidence:
  - 0cbdea9 Arc B caller migration phase 1
  - c967272 Arc B phase 2 import migration
  - 1ae48ef Arc B phase 3 shim deletion
  - b049f0d retired landed Arc B STATUS rows
companion:
  - docs/audits/2026-04-27-project-wide-shim-audit.md (Arc B definition + original 4-file inventory; Phase 2 takeover found the fifth gated shim)
  - docs/exec-plans/completed/2026-04-15-author-to-daemon-rename.md (rename arc Phases 1-5)
  - feedback_no_shims_ever (host directive 2026-04-27)
  - docs/exec-plans/completed/2026-04-26-decomp-step-11-prep.md (prep-doc shape model)
target_task: STATUS Work table #23 — Arc B (rename infra deletion). 5 files / ~406 LOC of compat infrastructure to delete + verify. Closes Phase 5 of the Author→Daemon rename arc.
gates_on: Task #18 (Step 11+ retarget sweep + Arc A/E shim deletion) MUST land first. Test files touched by Arc B caller migration overlap with #18's test-import surface; sequencing #18 before #23 avoids merge-conflict thrash.
---

# Arc B (Author→Daemon rename infrastructure deletion) — pre-flight scope

Completion note 2026-05-02: this plan is retained as the historical scope and
execution record. Arc B is no longer live work; see the completion_evidence
frontmatter for the landed commits.

Read-only scope for deleting the Author→Daemon rename compat infrastructure: `tinyassets/_rename_compat.py` + 3 alias modules + their downstream consumers. **The biggest win-per-effort cleanup remaining** in the post-decomp shim ledger if rename caller-migration verifies clean.

The audit framed Arc B as "4 files, 366 LOC, 2-3h." Verification surfaced **208 import sites across 47 files** still using `domains.fantasy_author.*` paths — far more caller migration than the audit estimate. Most live in `tests/` (192 sites / ~38 files); 13 live in `tinyassets/` (~8 files); 3 live in `domains/` (the alias modules themselves).

**Recommended split:** Phase 1 (tinyassets/ + domains/ tree migration, ~16 sites) is suitable for dev-2 NOW (non-overlapping with #18). Phase 2 (tests/ tree migration, ~192 sites) lands AFTER #18 ships, since #18 already touches the test-import surface. Phase 3 (shim/test/script deletion + smoke verify) closes Arc B once Phases 1+2 land.

---

## 1. Audit-vs-reality verdict

**Audit estimate (`docs/audits/2026-04-27-project-wide-shim-audit.md` §Arc B):**

> "4 modules, ~366 LOC. 2-3h (smoke + delete). The biggest win-per-effort in this audit if rename caller-migration is complete."

The audit's "if rename caller-migration is complete" caveat was load-bearing. **It is not complete.** Verified 2026-04-27 via:

```
grep -rE "from domains.fantasy_author|import domains.fantasy_author" tinyassets/ tests/ domains/ --include='*.py'
```

→ 208 distinct lines across 47 distinct files.

**Per-tree breakdown:**

| Tree | Sites | Files | Status |
|---|---|---|---|
| `tinyassets/` | 13 | 8 | NOT migrated (lazy imports, mostly inside try/except) |
| `tests/` | 192 | 37 | NOT migrated (top-level `from domains.fantasy_author.X import Y` patterns) |
| `domains/` | 3 | 2 | The alias modules' own self-references — fold into deletion |
| **TOTAL** | **208** | **47** | |

**Reality:** Arc B is **not 2-3h.** Realistic scope is ~6-10h split across 3 phases:
- Phase 1 (tinyassets/ + domains/ migration): ~1-2h, 16 sites, 10 files. **Dispatchable now to dev-2 (non-#18 overlap).**
- Phase 2 (tests/ migration): ~3-5h, 192 sites, 37 files. **Blocked on #18 ship** (test-import surface conflict).
- Phase 3 (shim/test/script deletion + `TINYASSETS_AUTHOR_RENAME_COMPAT=0` smoke + plugin mirror): ~1-2h. **Blocked on Phases 1+2 green.**

Total revised: ~6-10h. Still LOW risk per arc (mechanical sed + smoke), but materially larger than the audit estimate.

---

## 2. Symbol enumeration — files to delete (Arc B end-state)

The five compat files that die when Arc B ships:

### 2.1 `tinyassets/_rename_compat.py` (~189 LOC)

PEP-451 meta-path finder + loader infrastructure. Provides:

| Symbol | Role |
|---|---|
| `_FLAG_ENV = "TINYASSETS_AUTHOR_RENAME_COMPAT"` | Env-var flag name |
| `rename_compat_enabled() -> bool` | Public predicate; default `True`; reads `TINYASSETS_AUTHOR_RENAME_COMPAT` env var |
| `_RenameAliasLoader` | PEP-451 Loader; resolves alias module name → canonical target module |
| `_AliasModuleProxy` | `types.ModuleType` subclass that proxies `getattr` to canonical target |
| `_RenameAliasFinder` | PEP-451 Finder; intercepts imports matching `alias_prefix` |
| `install_module_alias(alias_prefix, target_prefix)` | Public registrar — used by alias modules to register themselves |

**Live external consumers (non-shim files that import from `_rename_compat`):**

| File | Line | Symbol |
|---|---|---|
| `tinyassets/discovery.py` | L40 | `from workflow._rename_compat import rename_compat_enabled` |

Single non-shim consumer. `discovery.py:111-125` uses `rename_compat_enabled()` to gate a `fantasy_author` registry compat lookup. When Arc B deletes `_rename_compat.py`, this `discovery.py` gate also dies — verify `discovery.py` is functionally clean without it.

### 2.2 `tinyassets/author_server.py` (~39 LOC)

Pure legacy redirect. `sys.modules[__name__] = workflow.daemon_server` (after import). Any `from workflow.author_server import X` resolves to `workflow.daemon_server.X`.

**Live external consumers:** 0 (verified 2026-04-27 grep — only `tests/test_pre_commit_invariant_author_server.py` references the literal string `workflow.author_server` and that's a fixture for the pre-commit invariant test, NOT an import).

### 2.3 `domains/fantasy_author/__init__.py` (~50 LOC)

Calls `install_module_alias("domains.fantasy_author", "domains.fantasy_daemon")`. All deep imports (`domains.fantasy_author.skill`, `domains.fantasy_author.graphs.scene`, etc.) resolve to canonical `domains.fantasy_daemon.*`.

### 2.4 `domains/fantasy_author/phases/__init__.py` (~88 LOC)

Custom `_PhaseAliasModule` proxy needed because deep-submodule imports (`from domains.fantasy_author.phases import orient`) race with the meta-path finder during test setup. More elaborate than #3 because tests import `phases.orient`, `phases.commit`, `phases.world_state_db` etc. as concrete modules.

---

## 3. Caller migration sites — concrete enumeration

### 3.1 Phase 1 — tinyassets/ + domains/ trees (16 sites, 10 files)

All migrations are mechanical: `domains.fantasy_author.X` → `domains.fantasy_daemon.X`. No symbol-name changes; canonical tree at `domains/fantasy_daemon/` mirrors `domains/fantasy_author/` 1:1 (verified — same `phases/`, `graphs/`, `skill.py`, etc.).

| File | Line(s) | Current import | Migration target |
|---|---|---|---|
| `tinyassets/api/runs.py` | 391, 889, 1236 | `from domains.fantasy_author.phases._provider_stub import (...)` | `from domains.fantasy_daemon.phases._provider_stub import (...)` |
| `tinyassets/checkpointing/sqlite_saver.py` | 167 | `from domains.fantasy_author.graphs import (...)` | `from domains.fantasy_daemon.graphs import (...)` |
| `tinyassets/evaluation/editorial.py` | 119 | `from domains.fantasy_author.phases._provider_stub import call_provider` | `from domains.fantasy_daemon.phases._provider_stub import call_provider` |
| `tinyassets/ingestion/extractors.py` | 259, 260 | `from domains.fantasy_author.phases._provider_stub import (...)` + `phases.worldbuild import _write_canon_file` | `from domains.fantasy_daemon.phases._provider_stub` + `phases.worldbuild` |
| `tinyassets/knowledge/raptor.py` | 333 | `from domains.fantasy_author.phases._provider_stub import call_provider` | `from domains.fantasy_daemon.phases._provider_stub import call_provider` |
| `tinyassets/memory/reflexion.py` | 205, 260 | `from domains.fantasy_author.phases._provider_stub import (...)` | `from domains.fantasy_daemon.phases._provider_stub import (...)` |
| `tinyassets/registry.py` | 13 | `from domains.fantasy_author.skill import FantasyAuthorDomain` | `from domains.fantasy_daemon.skill import FantasyAuthorDomain` (class name UNCHANGED — verified 2026-04-27: `domains/fantasy_daemon/skill.py:19` still defines `class FantasyAuthorDomain`. Class-rename is a separate arc; not in Arc B scope.) |
| `tinyassets/retrieval/agentic_search.py` | 140, 317 | `from domains.fantasy_author.phases._paths import resolve_kg_path` + `from domains.fantasy_author.phases import _provider_stub` | `from domains.fantasy_daemon.phases._paths` + `from domains.fantasy_daemon.phases` |

**Class-name continuity verified 2026-04-27.** `domains/fantasy_daemon/skill.py:19` still defines `class FantasyAuthorDomain` (the rename was module-path, not class-name). All Phase 1 migrations are pure-import-path edits; no symbol-rename burden. Class-rename is a separate concern outside Arc B scope.

### 3.2 Phase 2 — tests/ tree (192 sites, 37 files)

37 test files. Most are 2-10 sites each. Pattern is identical to Phase 1 (mechanical sed). Test-file list (alphabetical): `conftest.py`, `test_api.py`, `test_api_edge_cases.py`, `test_checkpointing.py`, `test_commit_kg_integration.py`, `test_commit_scene_history.py`, `test_dispatch_execution.py`, `test_evaluation.py`, `test_execution_kind_generic.py`, `test_fact_extraction.py`, `test_graph_topology.py`, `test_import_compatibility.py`, `test_ingestion.py`, `test_integration.py`, `test_knowledge_graph.py`, `test_learning.py`, `test_nodes_real.py`, `test_orient_reflection.py`, `test_packets.py`, `test_phase7.py`, `test_planning.py`, `test_provider_retry.py`, `test_research_probe.py`, `test_scene_dispatch_advance.py`, `test_stability.py`, `test_submit_request_wiring.py`, `test_synthesis_skip_fix.py`, `test_task_producers.py`, `test_universe_cycle_noop_guardrail.py`, `test_universe_isolation.py`, `test_universe_nodes.py`, `test_work_target_advance_on_accept.py`, `test_work_targets.py`, `test_tinyassets_runtime.py`, `test_world_state_db.py`, `test_worldbuild_noop_integration.py`, `test_writer_tools.py`.

**Special case: `tests/test_import_compatibility.py`.** Likely tests that BOTH old + new paths resolve. After Phase 3 deletes the alias modules, the "old path" assertions fail by design. This test file either:
(a) Gets deleted along with the alias modules (the test is testing the alias infrastructure, which dies), OR
(b) Keeps only the new-path assertions.

Recommend: delete the file in Phase 3. It's purpose-built for the migration window.

**Special case: `tests/test_pre_commit_invariant_author_server.py`.** Tests the pre-commit hook that BLOCKS new `from workflow.author_server import` lines. This test stays — the invariant should outlive the alias deletion (so future contributors don't accidentally re-introduce the import).

### 3.3 Phase 3 — alias module + infrastructure deletion

After Phases 1+2 land (zero callers in tinyassets/ + domains/ + tests/):

| File to delete | LOC | Risk |
|---|---|---|
| `tinyassets/_rename_compat.py` | 189 | LOW (only consumer is `discovery.py:40`; that line + L111-125 fold into the same commit) |
| `tinyassets/author_server.py` | 39 | LOW (no callers) |
| `fantasy_daemon/author_server.py` | ~40 | LOW (imports `_rename_compat`; must die with the shared gate after callers migrate) |
| `fantasy_author/__init__.py` | ~50 | LOW (top-level import shim; imports `_rename_compat`) |
| `fantasy_author/__main__.py` | ~8 | LOW (old CLI shim) |
| `domains/fantasy_author/__init__.py` | 50 | LOW (no callers post-Phase-1+2) |
| `domains/fantasy_author/phases/__init__.py` | 88 | LOW (no callers post-Phase-2) |
| `domains/fantasy_author/` directory | (empty after above) | `git rm -r` once directory is empty |
| `scripts/build_shims.py` | (file) | LOW (rename-era shim generator; retire with shims) |
| `scripts/migrate_imports.py` | (file) | LOW (one-shot migration helper; retire after caller migration) |
| **Plus update:** `tinyassets/discovery.py:40, 111-125` (delete the rename_compat gate) | ~15 | LOW |
| **Plus delete:** `tests/test_import_compatibility.py` (purpose-built migration test) | (file) | LOW |
| **Plus update:** `AGENTS.md` config table — delete the deprecation row if present | ~2 | LOW |
| **Total** | **~406** | **LOW** |

---

## 4. Sequencing dependencies

### Hard dependencies (must ship first)

- **Task #18 SHIP** — retarget sweep touches the same test-import surface as Phase 2. If Phase 2 lands before #18, the symbol → destination map in #18 has to handle `domains.fantasy_daemon.*` AND `domains.fantasy_author.*` (extra branch). Sequencing #18 first lets Phase 2 work on a clean slate.

### Soft dependencies (nice-to-have)

- **Step 11 SHIPPED** (commit `d662249`) — already landed.

### What can run NOW (Phase 1 dispatch-ready for dev-2)

Phase 1 (tinyassets/ + domains/ tree, 16 sites, 10 files) does NOT touch tests/. **Zero overlap with Task #18's Files boundary.** Dispatchable to dev-2 today.

### Cannot block

- Phase 6 `.author_server.db` rename (different layer — data, not code).
- Methods-prose evaluator design.
- Public-surface uptime work.

---

## 5. Risk profile

### Phase 1 (tinyassets/ + domains/ migration) — LOW risk

- Mechanical sed; tests still run via the `_rename_compat` alias finder during the migration so green-state holds throughout.
- Loud failure mode: if canonical `domains.fantasy_daemon.X` is missing a symbol, `ImportError` at first test.
- Mitigation: verify canonical tree completeness via `python -c "from domains.fantasy_daemon.X import Y"` for each migration target before dispatch.

### Phase 2 (tests/ migration) — LOW-MEDIUM risk

- Mechanical at scale (192 sites). Higher chance of a typo in one of 37 files.
- Mitigation: per-file `pytest tests/<file>.py -q` before moving on.
- One coupling risk: `tests/conftest.py` migration affects ALL tests. Migrate conftest LAST + run full suite immediately after.

### Phase 3 (shim/test/script deletion + smoke) — LOW risk

- The smoke test is `TINYASSETS_AUTHOR_RENAME_COMPAT=0 pytest -q`. If green, all callers have migrated; safe to delete.
- If not green, the failing test names the holdout caller; iterate.
- Plugin mirror: `python packaging/claude-plugin/build_plugin.py` after deletion to propagate.

### High-risk (none)

- No behavior change (mechanical import retarget).
- No external API surface change (`workflow.author_server` not imported externally).
- No data migration.

---

## 6. ROI

### What Arc B buys

| Metric | Before | After |
|---|---|---|
| Shim modules in `tinyassets/` + `domains/` | 4 | 0 |
| `workflow.author_server` legacy import path | live | dead |
| `domains.fantasy_author` legacy import path | live | dead |
| `TINYASSETS_AUTHOR_RENAME_COMPAT` env var | live | dead |
| Total shim LOC | ~406 | 0 |
| `feedback_no_shims_ever` compliance | partial | full (code layer) |
| New-contributor confusion ("what's an author?") | yes | no |
| Plugin mirror carries dead alias code every rebuild | yes | no |

### What Arc B does NOT change

- No public MCP behavior.
- No chatbot UX.
- No data migration (that's Phase 6).
- `.author_server.db` filename remains until Phase 6.

---

## 7. Acceptance criteria

Arc B is "done" when:

1. `git ls-files tinyassets/_rename_compat.py tinyassets/author_server.py fantasy_daemon/author_server.py fantasy_author/ domains/fantasy_author/ scripts/build_shims.py scripts/migrate_imports.py` returns nothing.
2. `grep -rE "from workflow.author_server|import workflow.author_server|from domains.fantasy_author|import domains.fantasy_author" tinyassets/ tests/ domains/ --include='*.py'` returns 0 lines (excluding the pre-commit invariant test fixtures, which are string literals not imports).
3. `TINYASSETS_AUTHOR_RENAME_COMPAT=0 pytest -q` is fully green.
4. `pytest -q` (default env) is fully green.
5. `python packaging/claude-plugin/build_plugin.py` clean parity check.
6. `tinyassets/discovery.py` no longer imports from `_rename_compat`; the `fantasy_author` registry compat lookup at L111-125 is deleted.
7. `AGENTS.md` config table has no `TINYASSETS_AUTHOR_RENAME_COMPAT` reference (if it existed).
8. `tests/test_import_compatibility.py` deleted (purpose-built migration test).

---

## 8. Decision asks for the lead → host

1. **Approve Phase 1 dispatch to dev-2 NOW?** 16 sites / 10 files / ~1-2h mechanical migration. No #18 overlap. Closes 16/208 of Arc B's caller-migration burden ahead of schedule.
2. **Approve Phase 2 dispatch to dev (or dev-2) post-#18?** 192 sites / 37 files / ~3-5h. Largest single chunk; sequenced after #18 lands.
3. **Approve Phase 3 (shim/test/script deletion) as a separate dev task post-Phase-2?** ~1-2h with smoke verify. Final closing commit on the rename arc.
4. **`tinyassets/registry.py:13` class-name check** — verify `FantasyAuthorDomain` vs `FantasyDaemonDomain` before Phase 1 dispatch. (Navigator: I'll verify before lead dispatches.)
5. **`tests/test_import_compatibility.py` deletion confirmed?** Recommend yes — file's purpose dies with the alias modules.

---

## 9. Cross-references

- `docs/audits/2026-04-27-project-wide-shim-audit.md` §Arc B — original audit (4-file inventory + LOC estimates, pre-caller-migration count).
- `feedback_no_shims_ever` (memory) — host directive driving this work.
- `docs/exec-plans/completed/2026-04-15-author-to-daemon-rename.md` — original rename arc; Arc B closes Phase 5.
- `docs/exec-plans/active/2026-04-26-decomp-arc-c-prep.md` — env-var alias deletion; runs after Arc B.
- `docs/design-notes/2026-04-27-author-server-db-filename-migration.md` — Phase 6 data rename; runs after Arc C.
- `tinyassets/_rename_compat.py:18` — `_FLAG_ENV` constant.
- `tinyassets/discovery.py:40, 111-125` — only non-shim consumer of `rename_compat`.
