---
title: `.author_server.db` filename data-format alias — migration plan
date: 2026-04-27
author: navigator
status: active
status_detail: Phase 6 DECIDED 2026-04-28 — `.workflow.db` filename, `db_path()` fn, Option A migration, 30s restart, plugin minor-bump. Impl pending Arc C ship (STATUS row 40)
companion:
  - docs/audits/2026-04-27-project-wide-shim-audit.md §3 item 17 (deferred from shim audit)
  - feedback_no_shims_ever (memory — host directive 2026-04-27; data-format aliases are shim-shaped at the data layer)
  - docs/exec-plans/active/2026-04-15-author-to-daemon-rename.md (Author→Daemon code rename — Arc B in shim audit)
load-bearing-question: When + how do we rename the on-disk SQLite file from `.author_server.db` to `.workflow.db` (or similar) without losing data or breaking running daemons?
audience: lead, host (final go/defer decision; if go, scheduling)
---

# `.author_server.db` filename migration plan

## TL;DR

The on-disk SQLite database in every `TINYASSETS_DATA_DIR` is named `.author_server.db` — a leftover from the pre-rename "author_server" architecture. The constant `DB_FILENAME = ".author_server.db"` lives at `tinyassets/storage/__init__.py:47`; the resolver `author_server_db_path()` at L289 is the only function that names it. Renaming the constant is a 1-line edit; **renaming the on-disk file** is the actual scope.

**~7 in-tree references + 12 function-call sites + 4 packaging mirrors + 1 deploy-doc reference.** Surface is small. The hard part is data-migration: existing universes have data in the old file; renaming requires a bootstrap-time discovery + rename pass that's safe under daemon-mid-flight, host-machine-off, and partial-failure conditions.

**Recommendation: DEFER until two preconditions are met:**
1. **Arc B (code rename) ships.** No point renaming the on-disk file while the code still has `_rename_compat` shims keeping `workflow.author_server` alive. The data rename should follow the code rename, not lead it.
2. **A single-host-shutdown migration window is acceptable.** Recommended migration shape (Option A below) requires the daemon to be stopped. If the host wants strictly-zero-downtime, only Option C (dual-read) works, and it adds ~80 LOC of code that itself becomes a shim. Per `feedback_no_shims_ever`, that's a worse outcome.

When both preconditions are met, **Option A (atomic rename + boot-time discovery)** is the right migration. ~2-3h dev work + 1 daemon restart. Frame as Phase 6 of the rename arc.

---

## 1. What "lives in" `.author_server.db`

**Schema (sampled from `tinyassets/storage/` bounded-context modules):**

| Bounded context | Tables (approx.) | Volume per universe (typical) |
|---|---|---|
| `accounts` | `accounts`, `sessions`, `capabilities` | dozens of rows |
| `universes_branches` | `branch_definitions`, `branch_versions`, `acls`, `snapshots`, `canonical_bindings` | hundreds-thousands |
| `daemons` | `daemon_definitions`, `daemon_forks`, `runtime_instances` | dozens |
| `requests_votes` | `requests`, `votes`, `vote_windows`, `ballots` | hundreds |
| `notes_work_targets` | `universe_notes`, `work_targets`, `priorities` | hundreds |
| `goals_gates` | `goals`, `gate_claims`, `leaderboard_*` | dozens-hundreds |
| `payments` | `escrow_locks`, `outcome_records` (Phase 6+) | low (post-launch) |

**Approximate file size per universe:** Live host (per `output/` survey 2026-04-26): `.author_server.db` ~454 KB + `-shm` 32 KB + `-wal` 140 KB. Other universes (`allied-ap` etc.) similar order of magnitude. Total ~few MB per universe at current scale; will grow into hundreds of MB at production scale.

**Callers / writers:**
- `tinyassets/daemon_server.py` — top-level orchestration, all write paths.
- `tinyassets/storage/{accounts,universes_branches,daemons,requests_votes,notes_work_targets,goals_gates}.py` — bounded-context CRUD via shared `_connect()` helper.
- `tinyassets/payments/escrow.py` — per docstring: "SQLite table escrow_locks lives in the same .author_server.db as ..."
- `tinyassets/api/branches.py:103,191` — comments only; routes through `_connect()` not direct path.
- `tests/test_outcome_gates.py` — 3 direct `sqlite3.connect(author_server_db_path(base))` sites for white-box verification.

**No external script reads the file directly.** No deploy-time tooling references it by name (only `deploy/RESTORE.md` documents the path for human-restore procedures).

---

## 2. Why the rename is wanted

**Per `feedback_no_shims_ever`:** "`Author = Daemon` aliases are forbidden." The on-disk filename is the same anti-pattern at the data layer — it perpetuates the old name, forces every new contributor to learn that "this is the daemon-server data, despite the name," and indicates the rename arc is unfinished.

**Specific frictions:**
- New contributors grep for `daemon_server.db` and find nothing; no clue the file exists.
- Restore runbooks at `deploy/RESTORE.md` document the old filename — onboarding pressure.
- Plugin packaging mirrors carry the same alias (4 files); every plugin rebuild perpetuates it.
- `author_server_db_path()` function name itself is alias-shaped — public symbol leaks the legacy name into API docs.

**Per host directive 2026-04-27 ("clean shippable builds"):** the data-layer alias is no different from a code-layer shim in spirit. Same anti-pattern.

---

## 3. Migration path candidates

### Option A — Atomic rename + boot-time discovery (RECOMMENDED)

**Mechanism:** On daemon boot, the storage layer's path resolver does:
1. Check if `<TINYASSETS_DATA_DIR>/<universe>/.workflow.db` exists. If yes, use it.
2. Else, check if `<TINYASSETS_DATA_DIR>/<universe>/.author_server.db` exists. If yes, atomically rename to `.workflow.db` (also rename `-shm` and `-wal` siblings if present), log the rename, then proceed.
3. Else, the universe has no DB yet (fresh universe) — create as `.workflow.db`.

**Atomicity:** Use `os.replace()` (atomic on POSIX + Windows for same-filesystem renames). Done before any connection is opened — daemon must NOT be running when boot happens (standard pre-boot expectation).

**Code change scope:**
- `tinyassets/storage/__init__.py:47` — `DB_FILENAME = ".workflow.db"`.
- `tinyassets/storage/__init__.py:289` — rename `author_server_db_path` → `workflow_db_path` (or just `db_path`); preserve the function but with new name; update `__all__` at L544.
- `tinyassets/storage/__init__.py` — add `_migrate_legacy_db_filename()` helper called once per universe at first `_connect()` invocation; idempotent (only renames if old exists + new doesn't).
- Update 12 call sites to use the new function name.
- Update 4 docstring/comment references (`.author_server.db` → `.workflow.db`).
- Update `deploy/RESTORE.md`.
- Update plugin-mirror via `python packaging/claude-plugin/build_plugin.py`.

**Operational steps:**
1. Daemon stopped (host-driven; ~30s restart window).
2. Deploy the new code.
3. Daemon starts; storage layer auto-migrates each universe's DB on first connect.
4. Verify: `ls -la $TINYASSETS_DATA_DIR/<universe>/` shows `.workflow.db` (no `.author_server.db`).
5. After 1-2 stable days, delete the `_migrate_legacy_db_filename()` helper (it'll have nothing to migrate). The code is then shim-free at both layers.

**Effort:** ~2h dev (code change + tests + plugin mirror) + 1 daemon restart window for host.

**Pros:**
- Single-name end-state — no dual-read shim. Compliant with `feedback_no_shims_ever`.
- Minimal code change (~30 LOC including the migrator + 12 call-site renames).
- Migrator is one-shot — deletes itself after run.
- Works offline (host's machine off doesn't matter — migration happens on next boot).

**Cons:**
- Requires daemon restart. Brief downtime.
- Migrator needs careful test coverage (rename + sibling files + no-op when new exists + handle both-exist edge case).

**Risks + mitigations:**
- **Both files exist at boot** (e.g. partial failure of prior migration): migrator detects, logs warning, prefers `.workflow.db` (assume the new one is canonical), backs up `.author_server.db` to `.author_server.db.legacy-<timestamp>` for host inspection.
- **Sibling `-shm`/`-wal` files** must rename together (SQLite WAL mode requires them). Migrator handles all three.
- **Cross-filesystem rename** (data dir on a network mount where `os.replace()` isn't atomic): unlikely on host's setup; document as a known limitation.

### Option B — New name + dual-read with deprecation period

**Mechanism:** Storage layer reads from `.workflow.db` if present, falls back to `.author_server.db`. New writes go to `.workflow.db` only. Existing universes keep using `.author_server.db` until manually migrated.

**Why rejected:** This IS a shim. Per `feedback_no_shims_ever`, dual-read paths are forbidden — they perpetuate two names for one thing, force new contributors to understand both, and become load-bearing infrastructure. ~80 LOC of "transitional" code that won't ever get cleaned up.

### Option C — In-place schema-version bump with NO rename

**Mechanism:** Keep the file named `.author_server.db` forever. Add a `schema_version` row that says "this is workflow daemon data, not legacy author-server data." Document in PLAN.md that the filename is historical.

**Why partially-acceptable:** Zero migration effort. Zero downtime. Zero risk.

**Why ultimately rejected:** Makes the filename a permanent aliasing artifact. Every new contributor sees `.author_server.db`, asks "what's an author server?" Documentation has to perpetually explain the legacy name. Fails the `feedback_no_shims_ever` spirit even though it's not a literal code shim. Better to do the rename right.

### Option D — Defer indefinitely (current state)

Do nothing. Wait for an unrelated migration to bundle this into.

**Why partially-acceptable:** No urgency. No user-visible impact. No data-loss risk.

**Why ultimately rejected:** Per the audit's quarterly-cadence rule, this will surface again in Q3 2026. Better to plan it now and execute when Arc B lands than to keep flagging it indefinitely.

---

## 4. Rollback-safety story

**Failure mode 1: Migrator partially renames.** Migration is rename-then-verify per universe. If the rename succeeds but the verify fails, the next boot sees `.workflow.db` exists and uses it — no rollback needed (the rename was successful).

**Failure mode 2: Daemon writes to new file, host wants to roll back to old code.** New code wrote schema-compatible data to `.workflow.db`. Old code expects `.author_server.db`. Rollback procedure:
1. Stop daemon.
2. `mv .workflow.db .author_server.db` (and `-shm`, `-wal` siblings).
3. Deploy old code. Boot.
4. Old code reads as if nothing happened.

**Failure mode 3: Host loses power mid-rename.** `os.replace()` is atomic — either the rename happened or it didn't. No half-state. On next boot, migrator runs again from whichever state it left off (new file exists → use it; old file still exists → migrate now).

**Failure mode 4: Plugin package shipping with old DB_FILENAME constant** (e.g. user runs old plugin against new server data). Plugin's `_connect()` looks for `.author_server.db`; finds nothing; treats as fresh universe. No data loss but plugin is non-functional. Mitigation: bump plugin minor-version; user re-installs.

**Net rollback safety: HIGH.** No data loss in any failure mode. Worst case is "user runs incompatible plugin → plugin doesn't work → user updates plugin."

---

## 5. Sequencing dependencies

### Hard dependencies (must ship first)

- **Arc B (code rename ships).** Per `2026-04-27-project-wide-shim-audit.md` Arc B: 4 files / ~366 LOC of `_rename_compat.py` infrastructure + alias modules need to die first. While `workflow.author_server` is still a live import path (gated on `TINYASSETS_AUTHOR_RENAME_COMPAT=1`), renaming the on-disk file would create a confusing intermediate state where the code is named one thing and the DB is named the new thing.
- **Tests for migrator.** New unit tests in `tests/test_storage_db_filename_migration.py` covering: fresh universe, legacy-only, new-only, both-exist (recovery), sibling-files-present, idempotent re-run.

### Soft dependencies (nice-to-have)

- **Step 11 + Task #18 retarget sweep.** Not a hard dep (the data rename is independent of the code-import retarget) but bundling clean-up phases reduces total daemon-restart count.

### Cannot block

- Methods-prose evaluator v1 (different domain).
- Cloud daemon redeploy (independent surface).
- Any user-facing chain-break work.

### Suggested sequencing

```
... (current arcs) ...
  → Step 11 (#13) SHIP
  → Task #18 retarget sweep SHIP (Arc A + Arc E)
  → Arc B SHIP (rename infra deletion)
  → Arc C SHIP (env-var aliases)
  → THIS work (Phase 6: data-rename)
```

This work is Phase 6 of the rename arc — completes the rename at every layer.

---

## 6. Effort + risk profile

| Phase | Effort | Risk |
|---|---|---|
| Code change (`DB_FILENAME` constant + function rename + migrator helper) | ~30 min | LOW |
| Test coverage (5-7 unit tests for migrator) | ~45 min | LOW |
| Update 12 call sites + 4 docstrings + `deploy/RESTORE.md` | ~30 min | LOW |
| Plugin mirror sync via `build_plugin.py` | ~5 min | LOW |
| Verify on test universe (rename round-trip + WAL siblings + rollback drill) | ~30 min | MEDIUM |
| Production deploy + daemon restart + verify | ~30 min host time | LOW (rollback path well-understood) |
| Delete migrator helper after 1-2 stable days | ~5 min | LOW |
| **TOTAL** | **~2-3h dev + 1h host** | **LOW** |

**Blast radius:** All universes in every `TINYASSETS_DATA_DIR` rooted at the host. ~5-10 universes today (per `output/` survey 2026-04-26: `default-universe`, `allied-ap`, plus auxiliaries). Production-scale will be similar order of magnitude (single-host MVP per `project_daemon_default_behavior`). Each universe migrates independently in the migrator's per-universe loop — failure in one doesn't block others.

**Discovery:** Migrator iterates `Path(TINYASSETS_DATA_DIR).iterdir()` for universe subdirs; per-universe rename. No central registry needed.

---

## 7. Recommendation

**SCHEDULE as Phase 6 of rename arc, after Arc B + Arc C land.**

Rationale:
1. Arc B + Arc C eliminate the code-side `author` references first; the data rename then closes the rename arc completely.
2. Effort is small (~2-3h dev + 1h host) and risk is well-bounded.
3. Per `feedback_no_shims_ever` enforcement, this would surface at every quarterly audit until done. Better to schedule than to keep flagging.
4. Option A is the only path consistent with "no shims" — Option B (dual-read) is a shim; Option C (no-rename) leaves a permanent alias artifact.

**Alternative: defer indefinitely** is acceptable if the host wants to focus on user-facing chain-break work and accepts the recurring quarterly audit flag. No urgency.

---

## 8. Decision asks for the lead → host

1. **Approve scheduling as Phase 6 of rename arc?** Or defer indefinitely? Recommend schedule.
2. **Confirm Option A** (atomic-rename + boot-time discovery + one-shot migrator that deletes itself after stable run)? Recommended; alternatives B and C both fail the no-shims rule in spirit.
3. **Pick the new filename:** `.workflow.db` (recommended — matches the project name + canonical brand) or `.daemon.db` (matches the daemon-server module name) or other. Recommend `.workflow.db`.
4. **Pick the new function name:** `workflow_db_path()` (matches `.workflow.db`) or just `db_path()` (terser, no naming-coordination needed if filename ever changes again). Recommend `db_path()` — it's the only DB the storage package owns; the qualifier is redundant.
5. **Approve daemon-restart window** for the deploy (~30s downtime)? Production single-host MVP — restart is routine.
6. **Plugin minor-version bump** to invalidate old plugins reading the legacy filename. Confirm.

---

## 9. Cross-references

- `docs/audits/2026-04-27-project-wide-shim-audit.md` §3 item 17 — original deferral.
- `feedback_no_shims_ever` — policy this work serves at the data layer.
- `docs/exec-plans/active/2026-04-15-author-to-daemon-rename.md` — code-rename arc; this is its Phase 6.
- `tinyassets/storage/__init__.py:47` — `DB_FILENAME` constant (single point of truth).
- `tinyassets/storage/__init__.py:289` — `author_server_db_path()` resolver.
- `tinyassets/storage/__init__.py:508` — `_connect()` factory (only consumer of `author_server_db_path()` internally).
- `deploy/RESTORE.md` — operator documentation that names the legacy file.
- `tests/test_outcome_gates.py:228,250,266` — 3 test sites that import + call `author_server_db_path()` directly; these become the migrator's white-box test fixtures.
