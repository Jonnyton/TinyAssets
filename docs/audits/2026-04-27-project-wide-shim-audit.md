---
title: Project-wide shim audit (2026-04-27)
date: 2026-04-27
author: navigator
status: read-only inventory + removal plan — host curates triage
companion:
  - feedback_no_shims_ever (memory — host directive 2026-04-27)
  - docs/exec-plans/active/2026-04-15-author-to-daemon-rename.md (Phases 1-5 rename)
  - docs/exec-plans/active/2026-04-19-rename-end-state.md (R7 storage split)
  - docs/exec-plans/active/2026-04-27-step-11plus-retarget-sweep-roi.md (originally recommended defer; host overrode → Task #18)
  - docs/audits/2026-04-25-universe-server-decomposition.md (universe_server.py decomp)
load-bearing-question: Which shims still exist, why, and what's the path to deletion?
audience: lead, host (final removal sequencing)
---

# Project-wide shim audit

## TL;DR

**14 distinct shim instances** found across **9 files** + 1 deprecated env-var pair + 1 deprecated DB-filename constant. They cluster into **5 removal arcs**:

| Arc | Shim count | Trigger to remove |
|---|---|---|
| **A. universe_server.py back-compat re-export blocks** | 8 import blocks (~280 LOC) | Task #18 (Step 11+ retarget sweep) — APPROVED, in queue |
| **B. Author→Daemon rename infrastructure** | 4 modules (`_rename_compat.py`, `author_server.py`, `domains/fantasy_author/__init__.py`, `domains/fantasy_author/phases/__init__.py`) | Phase 5 of rename — needs caller-migration verification (`TINYASSETS_AUTHOR_RENAME_COMPAT=0` smoke test) |
| **C. Legacy env-var deprecation aliases** | 2 (`UNIVERSE_SERVER_BASE` → `TINYASSETS_DATA_DIR`, `WIKI_PATH` → `TINYASSETS_WIKI_PATH`) | Caller migration + one release cycle |
| **D. Legacy module stubs** | 1 (`tinyassets/judges/__init__.py` — one-liner "will be removed") | Immediate (no callers in canonical tree) |
| **E. Storage-package legacy F401 re-exports** | 3 (`hashlib` / `secrets` / `uuid` re-exports for "legacy callers of daemon_server") | Verify no caller uses `from workflow.storage import hashlib`; delete |

**Headline:** Arc A is the largest by LOC and the highest-leverage cleanup; it's already in the dev queue as Task #18. Arc D is the cheapest immediate win (1-line module + zero callers). Arcs B + C are gated on caller-migration verification, not new design work. Arc E is trivial pending grep.

**Recommended sequence:** D (immediate) → A (Task #18, in queue) → E (post-A) → B (post-A, after rename caller-migration verify) → C (post-B).

---

## 1. Header summary table

| # | Shim | Type | Files | LOC | Removal blocker | Effort | Priority |
|---|------|------|-------|-----|-----------------|--------|----------|
| 1 | `engine_helpers` re-export block | Re-export | `tinyassets/universe_server.py:195` | ~13 | Task #18 retarget sweep | (folded into #18) | High |
| 2 | `evaluation` re-export block | Re-export | `tinyassets/universe_server.py:208` | ~40 | Task #18 retarget sweep | (folded into #18) | High |
| 3 | `market` re-export block | Re-export | `tinyassets/universe_server.py:247` | ~55 | Task #18 retarget sweep | (folded into #18) | High |
| 4 | `runs` re-export block | Re-export | `tinyassets/universe_server.py:302` | ~40 | Task #18 retarget sweep | (folded into #18) | High |
| 5 | `runtime_ops` re-export block | Re-export | `tinyassets/universe_server.py:342` | ~25 | Task #18 retarget sweep | (folded into #18) | High |
| 6 | `universe` re-export block | Re-export | `tinyassets/universe_server.py:491` | ~40 | Task #18 retarget sweep | (folded into #18) | High |
| 7 | `branches` re-export block | Re-export | `tinyassets/universe_server.py:1521` | ~30 | Task #18 retarget sweep + Step 8 ship | (folded into #18) | High |
| 8 | `status` `_policy_hash` re-export | Re-export | `tinyassets/universe_server.py:1836` | 1 | Task #18 retarget sweep | (folded into #18) | High |
| 9 | `_rename_compat.py` infrastructure | Compat module | `tinyassets/_rename_compat.py` | 189 | Phase 5 of rename | 2-3h (smoke + delete) | Medium |
| 10 | `author_server.py` legacy redirect | Legacy redirect | `tinyassets/author_server.py` | 39 | Phase 5 of rename | folds into #9 | Medium |
| 11 | `domains/fantasy_author/__init__.py` | Compat alias module | full file | 50 | Phase 5 of rename | folds into #9 | Medium |
| 12 | `domains/fantasy_author/phases/__init__.py` | Compat alias module | full file | 88 | Phase 5 of rename | folds into #9 | Medium |
| 13 | `UNIVERSE_SERVER_BASE` env-var alias | Env-var deprecation | `tinyassets/storage/__init__.py:210-222` | ~13 | One release cycle + caller verify | 1h | Low |
| 14 | `WIKI_PATH` env-var alias | Env-var deprecation | `tinyassets/storage/__init__.py:272-283` | ~12 | One release cycle + caller verify | folds into #13 | Low |
| 15 | `tinyassets/judges/__init__.py` legacy stub | Legacy module | full file | 1 | None — zero callers in canonical tree | 5 min | Low |
| 16 | `hashlib`/`secrets`/`uuid` `# legacy callers of daemon_server` F401 re-exports | Re-export | `tinyassets/storage/__init__.py:34,36,39` | 3 | Verify no caller uses `from workflow.storage import hashlib` | 30 min | Low |
| 17 | `.author_server.db` filename constant | Data-format alias | `tinyassets/storage/__init__.py:47` | 1 | Schema migration — separate concern | (out of scope for this audit) | Deferred |

**Total moveable shim LOC: ~640** (Arc A ~280, Arc B ~366, Arc C ~25, Arc D 1, Arc E 3). Arc A is in the dev queue (Task #18).

---

## 2. Per-shim detail

### Arc A — `universe_server.py` back-compat re-export blocks (8 instances)

**Pattern:** After Steps 1-10 of the universe_server.py decomp (Steps 1-7 + 9 + 10 LANDED today; Step 8 in flight via Task #1; Step 11 queued via Task #13), each extraction left a re-export block in `tinyassets/universe_server.py` so existing test imports continue to work without code edits.

**Why they exist:** Audit `docs/audits/2026-04-25-universe-server-decomposition.md` §7 Strategy 1 — "back-compat re-export shim" was the explicit choice to land 11 extractions without 317 mechanical test-import edits. Each block tagged `# noqa: E402, F401  — back-compat re-exports`.

**Files + line ranges (verified 2026-04-27 against post-Step-7 code):**

| Re-export source module | Line in universe_server.py | Symbols re-exported (approx.) |
|---|---|---|
| `workflow.api.engine_helpers` | L195 | `_current_actor`, `_truncate`, `_append_ledger`, `_storage_backend`, `_format_dirty_file_conflict`, `_filter_*_by_branch_visibility`, `_format_commit_failed`, `_upload_whitelist_prefixes` (post-Step-10 — already shipped) |
| `workflow.api.evaluation` | L208 | `_JUDGMENT_ACTIONS`, `_BRANCH_VERSION_ACTIONS`, `_dispatch_judgment_action` + ~10 handlers |
| `workflow.api.market` | L247 | `_ESCROW_ACTIONS`, `_GATE_EVENT_ACTIONS`, `_OUTCOME_ACTIONS`, `_ATTRIBUTION_ACTIONS`, `_gates_enabled`, `goals`/`gates` Pattern A2 wrappers |
| `workflow.api.runs` | L302 | `_RUN_ACTIONS`, `_dispatch_run_action`, `_ensure_runs_recovery`, `_run_mermaid_from_events`, ~12 handlers |
| `workflow.api.runtime_ops` | L342 | `_PROJECT_MEMORY_ACTIONS`, `_PROJECT_MEMORY_WRITE_ACTIONS`, `_MESSAGING_ACTIONS`, `_INSPECT_DRY_ACTIONS`, `_SCHEDULER_ACTIONS` + handlers |
| `workflow.api.universe` | L491 | `WRITE_ACTIONS`, `_action_*` (28 universe-tool handlers), `_daemon_liveness` (post-Step-9 — already shipped) |
| `workflow.api.branches` | L1521 | `_BRANCH_ACTIONS`, `_BRANCH_WRITE_ACTIONS`, `_dispatch_branch_action`, `_ext_branch_*` handlers + `_resolve_branch_id` (post-Step-8 — pending dev SHIP) |
| `workflow.api.status` | L1836 | `_policy_hash` |

**Removal plan:** Task #18 already approved + queued. The plan is the Step 11+ retarget sweep documented at `docs/exec-plans/active/2026-04-27-step-11plus-retarget-sweep-roi.md` — change ~317 test imports + monkeypatches to canonical paths, then delete the shim blocks. ~6 hours mechanical work.

**Dependencies:** All 4 in-flight decomp steps (Steps 8 + 11 dev tasks) must SHIP first. Step 11 specifically needs the shim block to exist until extensions.py extraction lands; after Step 11 SHIP, all 8 shim blocks die together in the retarget sweep.

**Notes:**
- The `branches.py` module docstring (L30) explicitly references the back-compat re-export contract — that docstring needs updating to "exports public surface" after the shim dies.
- Same for api/{engine_helpers,evaluation,market,runs,runtime_ops,universe}.py module docstrings — all reference `back-compat re-exported via workflow.universe_server`.
- All 8 blocks share a single removal commit; no per-block sequencing needed.

---

### Arc B — Author→Daemon rename infrastructure (4 modules)

**Pattern:** During the 2026-04-15 Author→Daemon project-wide rename, three alias modules + one infrastructure module keep old import paths (`workflow.author_server`, `domains.fantasy_author`, `domains.fantasy_author.phases`) resolving to canonical (`workflow.daemon_server`, `domains.fantasy_daemon`, `domains.fantasy_daemon.phases`). Gated by `TINYASSETS_AUTHOR_RENAME_COMPAT` env var (default on); `=0` raises `ImportError` from each shim so callers must migrate.

**Files + structure:**

#### Shim #9 — `tinyassets/_rename_compat.py` (189 LOC)

**Role:** Infrastructure. Provides `_RenameAliasFinder` (PEP-451 meta-path finder) + `_RenameAliasLoader` + `_AliasModuleProxy` + `install_module_alias(alias_prefix, target_prefix)`. The other three rename shims call `install_module_alias` to register their aliases.

**Why it exists:** Per the file's own docstring + `docs/exec-plans/active/2026-04-15-author-to-daemon-rename.md`: "Active during Phases 1-4. Flipped off (and file removed) in Phase 5."

**Removal plan:**
1. Verify rename completion: `TINYASSETS_AUTHOR_RENAME_COMPAT=0 pytest -q` → all green.
2. If green, NO caller in the test surface still uses `workflow.author_server` / `domains.fantasy_author` / `domains.fantasy_author.phases`.
3. Delete the 4 files (this + #10 + #11 + #12).
4. Remove the env-var reference from `tinyassets/discovery.py:40` (`from workflow._rename_compat import rename_compat_enabled`) — that's the only non-shim file that imports from `_rename_compat.py`.

**Dependencies:** None blocking. The hardest part is the smoke-test verification in step 1 — if any caller still imports old paths, that caller needs migration first.

**Effort estimate:** 2-3 wall-hours for the smoke verification + caller-migration of any holdouts + 4-file deletion + plugin-mirror sync. Could be done THIS week; not blocked on Steps 8/11.

#### Shim #10 — `tinyassets/author_server.py` (39 LOC)

**Role:** Pure legacy redirect. Re-binds `sys.modules[__name__] = workflow.daemon_server`. All `from workflow.author_server import X` calls resolve to `workflow.daemon_server.X`.

**Why it exists:** Same docstring as #9. Phase 5 cleanup target.

**Removal plan:** Folds into #9 — delete after rename smoke verify.

#### Shim #11 — `domains/fantasy_author/__init__.py` (50 LOC)

**Role:** Same pattern as #10 but for `domains.fantasy_author` → `domains.fantasy_daemon`. Uses `install_module_alias` from `_rename_compat.py` for deep-submodule import support.

**Why it exists:** Same.

**Removal plan:** Folds into #9.

#### Shim #12 — `domains/fantasy_author/phases/__init__.py` (88 LOC)

**Role:** Same pattern but for `domains.fantasy_author.phases` → `domains.fantasy_daemon.phases`. More elaborate (88 LOC) because it needs to keep `from domains.fantasy_author.phases import orient` returning the actual `orient` module even after old-path submodules are imported by tests. Uses a custom `_PhaseAliasModule` subclass to prevent shadowing.

**Why it exists:** Same. Requires the elaborate proxy because deep-submodule imports race with the meta-path finder during test setup.

**Removal plan:** Folds into #9.

**Net Arc B:** 4 files, ~366 LOC total. One smoke test + 4-file deletion. **The biggest win-per-effort in this audit if rename caller-migration is complete.**

---

### Arc C — Legacy env-var deprecation aliases (2 instances)

#### Shim #13 — `UNIVERSE_SERVER_BASE` env-var

**File:** `tinyassets/storage/__init__.py:210-222`.

**Pattern:** `data_dir()` resolver checks `TINYASSETS_DATA_DIR` first, then falls back to legacy `UNIVERSE_SERVER_BASE` with a `DeprecationWarning`. Documented in `AGENTS.md` §Configuration: "Deprecated. Legacy alias for `TINYASSETS_DATA_DIR`. Still honored; emits `DeprecationWarning` when `TINYASSETS_DEPRECATIONS=1`."

**Why it exists:** Cross-environment migration window — host's environments + CI + tests need time to switch from `UNIVERSE_SERVER_BASE` (legacy) to `TINYASSETS_DATA_DIR` (canonical). Pre-commit invariant 5 already blocks new reads outside `tinyassets/storage/__init__.py`.

**Removal plan:**
1. `git grep "UNIVERSE_SERVER_BASE"` across the codebase + `.env` files + GH Actions secrets. Confirm only the resolver itself + AGENTS.md doc + tests verifying the deprecation behavior reference it.
2. Migrate any environments/CI/secrets still using the legacy name.
3. Wait one release cycle (or skip if no external callers — single-host project).
4. Delete L210-222 + the `_reject_windows_path_on_posix(legacy, "UNIVERSE_SERVER_BASE")` call. Update AGENTS.md docs.

**Dependencies:** None blocking. Caller-migration is the only step.

**Effort estimate:** 1h.

#### Shim #14 — `WIKI_PATH` env-var

**File:** `tinyassets/storage/__init__.py:272-283`.

**Pattern:** Identical shape to #13 — `wiki_path()` resolver checks `TINYASSETS_WIKI_PATH` first, falls back to legacy `WIKI_PATH` with `DeprecationWarning`.

**Why it exists:** Same — cross-environment migration window.

**Removal plan:** Folds into #13. Same grep + migrate + delete.

**Net Arc C:** ~25 LOC, 1 file. Trivial cleanup once caller-migration verified.

---

### Arc D — Legacy module stubs (1 instance)

#### Shim #15 — `tinyassets/judges/__init__.py` (1 LOC)

**File contents:** `"""Judge infrastructure -- legacy module, will be removed."""`

**Verified callers (2026-04-27 grep):** None in canonical workflow tree. Only references:
- `C:/Users/Jonathan/Projects/TinyAssets/.claude/worktrees/agent-a54683e4/fantasy_author/judges/__init__.py` — separate worktree, not part of main checkout.
- `C:/Users/Jonathan/Projects/TinyAssets/fantasy_daemon/judges/__init__.py` — sibling fantasy_daemon tree (post-rename canonical), separate file.

**Why it exists:** Probably leftover from a pre-rename judge architecture. Has been sitting as a 1-line stub for unknown duration.

**Removal plan:**
1. `git rm tinyassets/judges/__init__.py`.
2. `pytest -q` to confirm no implicit imports break (none expected — nothing in canonical tree references `workflow.judges`).
3. Delete the empty `tinyassets/judges/` directory.

**Dependencies:** None.

**Effort estimate:** 5 minutes.

**Status: cheapest immediate win. Recommend dispatching as a one-line dev task today.**

#### POST-DISPATCH WRINKLE (2026-04-27, dev-2 surfaced during Task #22)

The original "zero callers in canonical tree" claim above was **95% right but missed three references** that dev-2 caught while executing the deletion:

1. **`fantasy_daemon/judges/__init__.py`** — sibling-tree shim, also being deleted with `tinyassets/judges/`. The sibling tree (`fantasy_daemon/`) carries its own `judges/` stub for the same reason; both die together. The audit grep saw it but classified it as "separate file" — should have classified it as "sibling-tree shim, in scope."
2. **`tinyassets/desktop/launcher.py:547`** — `_RELOAD_PACKAGES` string-list constant references `"workflow.judges"` for desktop reloader cosmetic logic. Cosmetic (the package being absent at reload time degrades gracefully) but worth cleaning in the same commit so the allowlist doesn't drift.
3. **`PLAN.md:63` + `docs/design-notes/2026-04-24-architecture-audit.md:209`** — both list `judges/` in "subpackages that already conform." Stale once the package is deleted; can't conform after deletion. Updated 2026-04-27 by navigator (this commit batch).

**Lesson for future audits.** "Zero callers in canonical tree" is necessary but not sufficient. Future `git grep <symbol>` sweeps must also check:

| Reference type | Where to look | Why missed in this audit |
|---|---|---|
| Sibling-tree shims | `fantasy_daemon/`, future sibling roots | Originally classified as "separate file, not in scope" — should have been "sibling shim, dies together." |
| Launcher reload allowlists | `tinyassets/desktop/launcher.py` `_RELOAD_PACKAGES` | Cosmetic constants don't break runtime; easy to miss in caller-search; clean in same commit so allowlist stays accurate. |
| Design-note conformance lists | `PLAN.md`, `docs/design-notes/*.md` | Documentation references "the package conforms" — stale post-deletion. Grep for the package name across all design notes + PLAN + AGENTS. |
| Restore runbooks | `deploy/RESTORE.md`, `docs/ops/*.md` | Documentation that names the file/package by literal string. Grep for filename. |
| Plugin-runtime mirror | `packaging/claude-plugin/plugins/*/runtime/` | Mirror copies the source tree; deletion must propagate via `python packaging/claude-plugin/build_plugin.py`. |

Going-forward audit checklist (added to navigator's standing rule per `feedback_no_shims_ever` event-driven cadence):

- [ ] Canonical-tree caller grep (this audit's baseline check).
- [ ] Sibling-tree caller grep (across `domains/*/`, `fantasy_daemon/`, etc.).
- [ ] Launcher reload allowlists + similar cosmetic constants.
- [ ] Design-note + PLAN.md + AGENTS.md conformance lists.
- [ ] Deploy + ops runbook references.
- [ ] Plugin packaging mirror parity.

---

### Arc E — Storage-package legacy F401 re-exports (3 instances)

#### Shim #16 — `hashlib` / `secrets` / `uuid` re-exports

**File:** `tinyassets/storage/__init__.py:34, 36, 39`.

```python
import hashlib  # noqa: F401  (re-exported for legacy callers of daemon_server)
...
import secrets  # noqa: F401  (re-exported for legacy callers of daemon_server)
...
import uuid     # noqa: F401  (re-exported for legacy callers of daemon_server)
```

**Why they exist:** Per the `# noqa` comment — when `daemon_server.py` was the god-module (3,575 LOC, since split into the `workflow.storage` bounded-context subpackage per `2026-04-19-storage-package-split.md`), some callers did `from workflow.daemon_server import hashlib` (instead of `import hashlib`). Re-exports preserve those imports during the migration.

**Removal plan:**
1. `git grep -E "from workflow.storage import.*hashlib|from workflow.storage import.*secrets|from workflow.storage import.*uuid"` → expect 0 hits in canonical tree.
2. `git grep -E "from workflow.daemon_server import.*hashlib|from workflow.daemon_server import.*secrets|from workflow.daemon_server import.*uuid"` → expect 0 hits.
3. If both grep at 0, delete the 3 `# noqa: F401` lines (just remove the `# noqa` comments and let the linter delete the unused imports, OR delete the lines outright).

**Dependencies:** None.

**Effort estimate:** 30 min (5 min grep + 5 min edit + 20 min full pytest to confirm no surprise import).

---

## 3. Out-of-scope items flagged for separate concerns

### Item 17 — `.author_server.db` filename constant

**File:** `tinyassets/storage/__init__.py:47` — `DB_FILENAME = ".author_server.db"`.

**Why out of scope:** This is a data-format alias, not a code shim. The SQLite database file on disk is named `.author_server.db` — changing the constant requires a data migration (rename the file in every existing `TINYASSETS_DATA_DIR`) which is a separate concern from code-shim cleanup.

**Recommended:** Leave as-is for this audit. If/when the rename arc has a Phase 6 ("rename data artifacts"), add a migration step there.

### Items not flagged as shims (verified non-shim during sweep)

- `tinyassets/api/branches.py:344-380` ("legacy NodeRegistration dict shape" conversion methods) — these are dict-format converters between two data shapes that BOTH currently exist; not a code shim. (Could be cleaned up if "legacy NodeRegistration" dict shape is truly unused, but that's a data-cleanup arc, not a code-shim arc.)
- `tinyassets/branches.py:196-235` ("default false to preserve back-compat with branches that ...") — these are runtime-behavior flags with default-value rationale, not import shims.
- `tinyassets/daemon_server.py:2290-2332` ("legacy column fallback for canonical_bindings") — dual-write data migration with explicit warning + telemetry counter (`_LEGACY_FALLBACK_HITS`); this is a working dual-write pattern, NOT a code shim. Has its own removal arc per Step-2 dual-write completion.
- `tinyassets/discovery.py:111-125` (`fantasy_author` registry compat lookup) — gated by `rename_compat_enabled()`; this is a downstream consumer of the rename infrastructure (Arc B), NOT a shim itself. Cleanup folds into Arc B.

---

## 4. Recommended removal sequence

| Order | Arc | Trigger | Effort | Result |
|---|---|---|---|---|
| 1 | **D** (judges stub) | Immediate | 5 min | 1 file deleted |
| 2 | **A** (universe_server.py shim blocks) | Already in queue (Task #18); waits for Step 8 + Step 11 SHIP | ~6h | 8 blocks deleted (~280 LOC) |
| 3 | **E** (storage F401 re-exports) | Post-A (or anytime — independent) | 30 min | 3 lines deleted |
| 4 | **B** (Author→Daemon rename infrastructure) | Caller-migration smoke verify (`TINYASSETS_AUTHOR_RENAME_COMPAT=0 pytest -q` green) | 2-3h | 4 files deleted (~366 LOC) |
| 5 | **C** (legacy env-var aliases) | Caller-migration verify (grep + env scrub) | 1h | ~25 LOC deleted |

**Total cleanup effort if all sequenced: ~10-12 wall-hours.** Yields ~640 LOC of pure-deadweight shim code deleted plus 5-6 files removed.

**Parallelization:** D + E + first-pass-grep for B/C + first-pass-grep for A can all happen concurrently (read-only investigation). Actual deletes serialize per arc.

**Critical path:** A (~6h) is the longest single arc and is already approved + queued. B (~3h) is the second-largest and is the highest *win-per-effort* if rename caller-migration is complete (4 files / 366 LOC for ~3h).

---

## 5. Reverse-compatibility / risk assessment

### Low-risk arcs (no behavior change)

- Arc A: pure mechanical retarget; tests verify behavior unchanged.
- Arc D: zero callers in canonical tree.
- Arc E: F401 re-exports almost certainly unused; 3-line deletion behind grep verify.

### Medium-risk arcs (caller migration required)

- Arc B: relies on `TINYASSETS_AUTHOR_RENAME_COMPAT=0` smoke. If a caller still uses the old path, the smoke fails loudly — fix the caller, retry. Iterative.
- Arc C: if external scripts / CI / secrets / runbooks still set `UNIVERSE_SERVER_BASE` or `WIKI_PATH`, they'll silently miss config after deletion. Mitigation: grep + scrub the host's actual environments (not just code) before deleting.

### High-risk arcs (none)

- No data migration. No external API surface change. No public chatbot-surface change.

---

## 6. Decision asks for the lead → host

1. **Approve Arc D as immediate dispatch?** 5-min one-liner; deletes `tinyassets/judges/__init__.py`. Recommend yes — zero risk.
2. **Approve Arc E as a small follow-up to Task #18?** 30 min; bundles cleanly with the universe_server.py retarget sweep since both touch import surface.
3. **Approve Arc B as a separate dev task (after Steps 8 + 11 + Task #18 land)?** Largest win-per-effort. Needs a `TINYASSETS_AUTHOR_RENAME_COMPAT=0 pytest -q` smoke verify first; if green, 4-file deletion is mechanical.
4. **Approve Arc C as an Arc-B follow-up?** Trivial 1h; no functional dependency on B but logical grouping ("rename arc" cleanup).
5. **Item 17 (`.author_server.db` filename)** — defer to a separate "Phase 6 rename data artifacts" arc. Not a code shim. Confirm.
6. **Going-forward enforcement.** The `feedback_no_shims_ever` memory is the policy. Periodic re-audit cadence — every 4-8 weeks? Or only when shim count grows? Recommend: navigator runs this audit at every quarterly arc-end, OR whenever a refactor lands that introduces a new shim.

---

## 7. Cross-references

- `feedback_no_shims_ever` (memory, host directive 2026-04-27) — the policy this audit serves.
- `docs/exec-plans/active/2026-04-15-author-to-daemon-rename.md` — Arc B history (Phases 1-5 of the rename).
- `docs/exec-plans/active/2026-04-19-storage-package-split.md` — Arc E history (R7 storage-package split).
- `docs/exec-plans/active/2026-04-19-rename-end-state.md` — host-decision row in STATUS for the rename end state.
- `docs/exec-plans/active/2026-04-27-step-11plus-retarget-sweep-roi.md` — Arc A history; navigator originally recommended defer, host overrode → Task #18.
- `docs/audits/2026-04-25-universe-server-decomposition.md` — original audit that introduced Arc A.
- `AGENTS.md` §Configuration — documentation of the deprecated env vars (Arc C).
- `STATUS.md` — Concerns curation surface for any shim debt that surfaces after this audit.
