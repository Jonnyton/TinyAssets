# Author → Daemon Rename: Phase 1+ Status & Dispatch Plan

**Date:** 2026-04-19
**Author:** navigator
**Companion to:** `docs/exec-plans/active/2026-04-15-author-to-daemon-rename.md` (parent plan).
**Status:** Delta audit + dispatch-ready task list. Not implementation.

---

## 1. Where the rename actually stands today

Reading the working tree against the parent plan's phase structure.

### Phase 0 — Preflight: **DONE** (commit `07b75d8` 2026-04-17)

Per activity.log handoff: `_rename_compat` flag landed, 13 tests added, audit completed. Phase 0 conclusion: zero content-authorship `author_id` sites — Phase 3's discriminator becomes additive-no-backfill.

### Phase 1 Part 1 — Module + package physical rename: **DONE** (commit `b395d19` 2026-04-17)

- `fantasy_author/` → `fantasy_daemon/` (`git mv` complete; `fantasy_daemon/` exists, `fantasy_author/` retains only `__init__.py` + `__main__.py` shims).
- `domains/fantasy_author/` → `domains/fantasy_daemon/` (`domains/fantasy_author/` retains only `__init__.py` shim).
- `tinyassets/author_server.py` → `tinyassets/daemon_server.py` (canonical at new path; `tinyassets/author_server.py` is a shim).
- `fantasy_author_original/` deleted.
- `fantasy_author.pyw` → `fantasy_daemon.pyw`.
- 299 internal renames swept.

### Phase 1 Part 2 — Compat shims + import rewrites + packaging mirror sync: **STAGED, NOT COMMITTED**

Per `2026-04-18T00:15:00-07:00 [claude-code/dev]` handoff. Currently in the working tree (uncommitted, 115 dirty files at handoff; mostly stable):

- 4 untracked shim files: `fantasy_author/__init__.py`, `domains/fantasy_author/__init__.py`, `tinyassets/author_server.py`, `packaging/.../runtime/tinyassets/author_server.py`. **Verified by inspection 2026-04-19** — these use `install_module_alias` from `tinyassets/_rename_compat.py` (sys.modules-rebind, NOT snapshot), gated on `TINYASSETS_AUTHOR_RENAME_COMPAT` (default on). Quality is good; matches the design intent in §136 of the parent plan.
- 64 modified files inside `fantasy_daemon/` + `domains/fantasy_daemon/` doing internal `fantasy_author.*` → `fantasy_daemon.*` and `workflow.author_server` → `workflow.daemon_server` rewrites.
- Packaging mirror under `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/` mirrors the shim + rewrites.
- Ruff clean on full rename surface (per dev handoff).
- Smoke OK via shims (per dev handoff): `run_book` is the same object across both alias paths; `workflow.author_server` and `workflow.daemon_server` both expose `propose_author_fork`.
- **NOT verified end-to-end:** dev's `pytest` run had broken Bash output capture (background jobs producing 0-byte output). Full suite never confirmed green from dev's side. **Verifier MUST run full pytest before this commits.**

This is exactly what STATUS.md task #6 is doing right now — "Phase 1 Part 2 audit + commit queued shims."

### Phase 2 — Identifier rename inside new modules: **NOT STARTED**

Verified by grep:
- `class Author` → `class Daemon` rename: NOT done. No `class Daemon` in `tinyassets/` or `fantasy_daemon/` outside of unrelated names (`DaemonControlBody` predates the rename; `DaemonController` is a fantasy controller class, not the renamed Author class).
- No `Author = Daemon` aliases anywhere.
- Function renames (`register_author` → `register_daemon`, etc.) — NOT done.
- Variable renames (`author_id: str` → `daemon_id: str` in signatures) — NOT done.

The parent plan estimates Phase 2 at **3-5 commits, ~2 days** (one commit per subsystem: daemon_server, branches, memory, retrieval, runtime).

### Phase 3 — DB schema rename + content-authorship discriminator: **NOT STARTED**

Verified by grep: no `author_kind` references anywhere in the live tree. Per Phase 0's audit conclusion, the discriminator is additive-no-backfill — but the ALTER TABLE work for `author_definitions` → `daemon_definitions` and the ID-prefix backfill (Option A) are still pending.

Parent-plan estimate: **1-2 commits, ~1-1.5 days.**

### Phase 4 — User-facing brand pass: **PARTIALLY DONE, OUT OF ORDER**

This phase was always going to land partly out of sequence with the parent plan because the user-sim live missions surfaced brand-related bugs that required immediate fixes. Already landed:
- `0670131` "vocabulary-hygiene pass on user-facing surfaces (task #89 LIVE-F7)."
- `4ef0769` "relocate behavioral directives from tool descriptions to @mcp.prompt returns (LIVE-F2 yardi fabrication...)" — partial brand-voice work.
- The "Universe Server" → "TinyAssets Server" rebrand (task #1, just landed) is a Layer-2 brand sweep that overlapped Phase 4 territory but was scoped to the platform-name rename, not the daemon rename.

Phase 4's *remaining* scope (per parent plan §4 Phase 4): MCP tool descriptions in `tinyassets/universe_server.py` (every tool's description string), `tinyassets/daemon_server.py`, `packaging/mcpb/manifest.json` daemon-vocabulary copy, error messages, the README "summon a daemon" voice pass.

### Phase 5 — Remove shims + flag flip: **NOT STARTED**

Blocked on Phase 1 Part 2 commit + Phase 2 + Phase 3 + Phase 4 landing. Parent-plan estimate: **1 commit, ~0.5 day**, plus a one-release bake before flag deletion.

---

## 2. What ships in the queued task #6 commit

This is what dev should commit when task #6 verifies green. Treat the commit as the *full* Phase 1 Part 2 landing — no further fragmentation needed.

**Files (collision boundary):**
- 4 shim files (untracked → committed):
  - `fantasy_author/__init__.py`
  - `domains/fantasy_author/__init__.py`
  - `tinyassets/author_server.py`
  - `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/author_server.py`
- 64 modified files inside `fantasy_daemon/` + `domains/fantasy_daemon/` doing the internal import rewrites.
- The packaging mirror entries that mirror the above (already part of the dirty set).
- `tinyassets/_rename_compat.py` modifications (already dirty in tree).
- `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/_rename_compat.py` (mirror).

**Files explicitly NOT in this commit** (these are the "pre-existing dirt" that lives in the same `git status`):
- `AGENTS.md`, `CLAUDE_LEAD_OPS.md`, `LAUNCH_PROMPT.md`, `PLAN.md`, `STATUS.md` (lead-curated; not Phase 1 Part 2).
- `.agents/activity.log`, `.agents/skills/team-iterate/SKILL.md`, `.claude/agents/*.md` deletions/additions, `.claude/skills/team-iterate/SKILL.md` (agent-roster work).
- `docs/design-notes/INDEX.md`, `docs/exec-plans/INDEX.md`, `docs/launch-prompt-audit.md`, `docs/reality_audit.md` (separate doc work).
- `prototype/full-platform-v0/Dockerfile`, `prototype/full-platform-v0/requirements.txt` (prototype, separate).
- `tests/test_author_server_api.py`, `tests/test_graph_topology.py`, `tests/test_synthesis_skip_fix.py` (test fixes; merit own commit per "test_files require reviewer's whole-file pass" rule).
- `scripts/sync-skills.ps1` (mirror tooling change).
- `packaging/conway/panel-metadata.json`, `packaging/mcpb/*`, `packaging/registry/*`, `packaging/claude-plugin/build_plugin.py` (Layer-2 rebrand follow-throughs already covered by tasks #1/#5).
- The `?? docs/design-notes/2026-04-1*.md` untracked design notes (navigator-curated, separate landings).

**Commit message (suggested):**

```
rename Phase 1 Part 2: compat shims + import rewrites + packaging mirror sync

- 4 sys.modules-rebind shims gated on TINYASSETS_AUTHOR_RENAME_COMPAT
  (fantasy_author, domains/fantasy_author, tinyassets/author_server,
  + plugin-runtime mirror).
- 64 internal rewrites: fantasy_author.* -> fantasy_daemon.*,
  workflow.author_server -> workflow.daemon_server inside the renamed
  packages.
- Packaging mirror byte-equal to canonical tinyassets/ tree.
- Ruff clean. Full pytest verified by verifier (NEW — dev's prior run
  had broken Bash capture).

Phase 1 Part 2 of docs/exec-plans/active/2026-04-15-author-to-daemon-rename.md.
Phase 2 (identifier rename) is the next dispatchable phase.
```

**Verifier gate:**
- Full `pytest` (NOT targeted) — Phase 1 Part 2 has never been confirmed green end-to-end.
- `ruff check` on the full diff.
- Sanity: `import fantasy_author` and `import fantasy_daemon` resolve to the same module object (existing test in `tests/test_import_compatibility.py` should cover this — confirm it exercises the new shim, not just historical compatibility).
- Cross-alias module-state test: writing through `workflow.author_server` is visible through `workflow.daemon_server` (per the design intent — sys.modules-rebind, not snapshot).

---

## 3. What's pending for Phase 3 (and the §1.5 audit conclusion)

Phase 3 is **simpler than the parent plan estimated** because Phase 0's audit found zero content-authorship `author_id` sites. That collapses the Phase 3 work to:

1. **DB schema rename** of agent-runtime tables only:
   - `ALTER TABLE author_definitions` → `daemon_definitions`.
   - `ALTER TABLE author_votes` → `daemon_votes`.
   - SQLite ALTER COLUMN workaround (create new table + INSERT SELECT + drop old + rename) for `author_id`, `parent_author_id`, `child_author_id`, `preferred_author_id` columns on tables that hold them. Phase 0 audit already enumerated these.
   - Idempotent migration; backup `.author_server.db` before running (file copy).

2. **ID-prefix backfill** (Option A, recommended in parent plan):
   - UPDATE all rows with `id LIKE 'author::%'` to `id LIKE 'daemon::%'`.
   - Single SQL statement; same migration as the schema ALTER.

3. **Add `author_kind` discriminator column** ONLY to content-authorship tables:
   - Per Phase 0 audit, the count is zero. **This step may be a no-op today.** Recommend dev verify Phase 0 audit's enumeration is still correct (no new content-authorship sites added since 2026-04-17), and if so, skip the discriminator column addition entirely. If new sites exist, add `author_kind TEXT NOT NULL DEFAULT 'daemon'` to each.

4. **Update SQL strings** in Python that reference renamed columns.

5. **Test gate:** fresh-DB test creates new schema; upgrade test verifies migration from a fixture old-schema DB.

**Estimate:** 1-1.5 commits, ~1 day (lighter than parent-plan estimate because of the audit shortcut).

---

## 4. Whether Phase 4 (old-path deletion) is ready

Phase 4 in the parent plan is the **brand pass**, not deletion. Phase 5 is deletion. Re-reading the question with that mapping:

**Phase 5 readiness check** — old-path deletion is NOT ready. Blockers:

- Phase 1 Part 2 must commit (task #6).
- Phase 2 must land (identifier renames + class renames + aliases).
- Phase 3 must land (DB schema + author_kind audit).
- Phase 4 brand pass must complete (MCP tool descriptions, error strings, README "summon a daemon" voice).
- One release-cycle bake of the compat flag in `default=on` mode.
- Then Phase 5 = delete shims + flip `TINYASSETS_AUTHOR_RENAME_COMPAT=off` default + remove `Author = Daemon` aliases + delete the flag entirely.

**Phase 4 brand pass readiness** — partially done (per §1 above). Remaining work is dispatch-ready as a discrete task: MCP tool descriptions in the new `tinyassets/daemon_server.py` + `tinyassets/universe_server.py`, error strings, README pitch.

---

## 5. Dispatch-ready task list — **OBSOLETE 2026-04-19** ⚠️

> **⚠️ OBSOLETE per host's "Foundation End-State" standing rule (CLAUDE_LEAD_OPS.md §"Foundation End-State vs Feature Iteration", commit `557b051`).** The A1 → A2 → A3 → A4 → A5 → B1 → C1 → C2 → D1 → D2 ladder below is **abandoned**. Rename = foundation work, and foundation builds to end-state in one commit, not phased.
>
> **Current spec for remaining rename work:** `docs/exec-plans/active/2026-04-19-rename-end-state.md`. Two paths there:
> - **Path A** — one end-state commit (~3-4 dev-days serial atomic). Recommended.
> - **Path B** — freeze current aliases as permanent feature (~0.5 dev-day brand pass standalone).
>
> Already-shipped work stays landed: `72e696e` (Phase 1 Part 1) + `7dde417` (Phase 1 Part 2.5). They can't be un-shipped, but no further phases follow — collapse to end-state OR skip per host directive.
>
> **Sequencing per `2026-04-19-rename-end-state.md` §3:** ships AFTER daemon-economy first-draft (per "Daemon Economy is Foundation" rule — cleanup doesn't block product shipping).
>
> The original §5 task list is preserved below for historical context only; **do NOT dispatch from it**.

### Historical §5 (preserved for context — DO NOT DISPATCH)

> **2026-04-19 reclassification (post task #7 audit).** Task #6 marked completed-as-no-op — the actual Phase 1 Part 2 commit was `72e696e`, landed before this session. The dirty-tree cluster dev's audit *deferred* (`tinyassets/_rename_compat.py` extensions + `tinyassets/discovery.py` rename_compat branch + `domains/fantasy_author/__init__.py` + `fantasy_author/__init__.py` + `fantasy_author/__main__.py` shim + `domains/fantasy_author/phases/` + their packaging mirrors) is **Phase 1 Part 2.5**, not Phase 2. Verdict + reasoning in §5.5 below. Renumbered the queue so STATUS dispatch is unambiguous.

> **A0 (Phase 1 Part 2.5)** is now the dependency root for A1-C2; not a Phase 2 task.

| Proposed # | Task | Files (collision boundary) | Depends | Notes |
|---|---|---|---|---|
| **(landed) #6** | Phase 1 Part 2 audit + commit queued shims | — | — | Completed-as-no-op 2026-04-19; the actual commit was `72e696e`, pre-this-session. |
| **A0** | Phase 1 Part 2.5 — deep-submodule alias loader + missing shim surfaces (STATUS task #17) | `tinyassets/_rename_compat.py` (+ mirror); `tinyassets/discovery.py` (+ mirror); `domains/fantasy_author/__init__.py`; `fantasy_author/__init__.py`; `fantasy_author/__main__.py` (untracked); `domains/fantasy_author/phases/` (untracked dir) | — | Dev's deferred cluster from `docs/audits/2026-04-19-dirty-tree-audit.md`. Closes Phase 1 robustness gap (sys.modules-rebind alone misses deep-submodule imports done lazily). Required *before* A1 — A1's `Author = Daemon` aliases will be exported through this loader. Verdict reasoning in §5.5. |
| **A1** | Phase 2 commit 1 — `Daemon` class + `register_daemon` family + module-level aliases | `tinyassets/daemon_server.py` class definitions; `Author = Daemon` alias guarded by `rename_compat_enabled()`; equivalent for `register_author`/`list_authors`/`get_author` → new names + alias | A0 | Smallest atomic commit; gets the public API rename in. Old names keep working via aliases. |
| **A2** | Phase 2 commit 2 — daemon_server internal find-replace | `tinyassets/daemon_server.py` (parameter/variable names: `author_id` → `daemon_id` inside Python; SQL strings UNCHANGED) | A1 | Subsystem-scoped per parent plan §142. Awkward `daemon_id = row["author_id"]` reads are EXPECTED and temporary. |
| **A3** | Phase 2 commit 3 — branches + memory subsystems internal find-replace | `tinyassets/branches/`, `tinyassets/memory/`, `tinyassets/retrieval/`, `tinyassets/runtime.py` parameter/variable names | A1 | Parallel-safe with A2 (different files). Same SQL-string discipline. |
| **A4** | Phase 2 commit 4 — fantasy_daemon + domains internal find-replace | `fantasy_daemon/`, `domains/fantasy_daemon/` parameter/variable names | A1 | Parallel-safe with A2 + A3. |
| **A5** | Phase 2 commit 5 — packaging mirror sync after A1-A4 land | `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/**` | A1, A2, A3, A4 | Mechanical sync via `python packaging/claude-plugin/build_plugin.py` (or the project's mirror tool). |
| **B1** | Phase 3 commit — DB schema rename + ID-prefix backfill + author_kind audit | DB migration in `tinyassets/storage/` (SQLite ALTER pattern); SQL strings in Python that reference renamed columns; fresh-DB and upgrade-DB tests | A5 | Audit step: re-confirm Phase 0's "zero content-authorship sites" enumeration. If holds, skip `author_kind` column. Otherwise add it to enumerated tables. |
| **C1** | Phase 4 brand-pass commit 1 — MCP tool descriptions in new modules | `tinyassets/universe_server.py` + `tinyassets/daemon_server.py` tool description strings, parameter descriptions, response copy. Use parent plan §169-204 verb/noun guidance. | B1 | Highest-priority brand surface (visible inside Claude.ai). |
| **C2** | Phase 4 brand-pass commit 2 — packaging + error strings + README | `packaging/mcpb/manifest.json`, `packaging/registry/server.json`, `packaging/claude-plugin/.claude-plugin/marketplace.json`, all `raise ValueError/RuntimeError` strings in `tinyassets/universe_server.py` + `tinyassets/daemon_server.py`, `README.md`, `INDEX.md`, `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/bootstrap.py` first-launch messages | B1 | Parallel-safe with C1. README is the viral-hook surface — voice matters. |
| **D1** | One-release compat bake | — | C1, C2 | Time-gated. Clock starts when C2 lands. Recommend ~1 release cycle (~2 weeks per current cadence). No work, just hold. |
| **D2** | Phase 5 final — delete shims + flip flag + remove aliases | Delete `fantasy_author/__init__.py`, `domains/fantasy_author/__init__.py`, `tinyassets/author_server.py`; remove `Author = Daemon` aliases; flip `TINYASSETS_AUTHOR_RENAME_COMPAT` default to `off`; delete the flag a release later | D1 | Final commit. Grep audit per parent plan §256-257 for stragglers. |

**Sequencing notes for dispatcher:**
- A2, A3, A4 can run in parallel (different file sets, all depend only on A1).
- C1, C2 can run in parallel (different file sets, both depend only on B1).
- B1 is the serial bottleneck — DB migration must land alone.
- A5 is mechanical and gates B1 (mirror needs to reflect canonical state before DB migration tests run cleanly in mirrored environment).

**Estimate (with parallelism, 2 devs):** ~3-4 dev-days from A1 through D2 (excluding the D1 bake). Without parallelism: ~5-6 dev-days serial.

---

## 5.5. Reclassification verdict — Phase 1 Part 2.5 vs Phase 2 A1

**Date:** 2026-04-19
**Trigger:** Dev's `docs/audits/2026-04-19-dirty-tree-audit.md` deferred a cluster ("Rename Phase 1 compat extensions") pending navigator classification. Reading the actual file diffs vs the parent rename plan + Phase 1 Part 2 commit (`72e696e`):

**The deferred cluster IS Phase 1 Part 2.5 — not Phase 2.** Reasoning:

1. **`tinyassets/_rename_compat.py` diff** adds `_RenameAliasLoader` + `_RenameAliasFinder` + `_AliasModuleProxy` + `install_module_alias()`. This is a **deep-submodule meta-path finder** — it intercepts lazy imports of `fantasy_author.X.Y.Z` after parent `fantasy_author` is already loaded and rebinds them to `fantasy_daemon.X.Y.Z`. The `72e696e` Phase 1 Part 2 commit shipped a `sys.modules`-rebind-only shim, which catches eager imports but misses lazy / late-bound submodule imports. The new loader closes that gap. **Diagnosis: this is a Phase 1 robustness fix that should have been part of Phase 1 Part 2 originally**, not a Phase 2 forward step.

2. **`fantasy_author/__init__.py` + `domains/fantasy_author/__init__.py` diffs** add `install_module_alias(__name__, "fantasy_daemon")` calls. Without (1) above, these calls don't compile. They are paired changes that cannot be separated. Phase 1 territory.

3. **`fantasy_author/__main__.py` (untracked)** is a one-liner `from fantasy_daemon.__main__ import *` shim. Pure CLI surface preservation — exactly the Phase 1 contract ("old import paths keep working"). Phase 1 territory.

4. **`domains/fantasy_author/phases/` (untracked dir)** contains `__init__.py` only — a phases sub-package shim that preserves `from domains.fantasy_author.phases.X import Y` import paths. Same reasoning. Phase 1 territory.

5. **`tinyassets/discovery.py` diff** adds a `rename_compat_enabled()` branch that appends `fantasy_author` to the discovered domain list. This is the ONLY runtime-behavior change in the cluster, and it is also Phase 1 in spirit — it ensures the `discover_domains()` API surface still returns `fantasy_author` while the alias is live, so any test or consumer that does `assert "fantasy_author" in domains` keeps passing. Without it, Phase 1's "old paths keep working" contract leaks at the discovery surface.

**Conclusion: ship the cluster as Phase 1 Part 2.5 (task #17), not as Phase 2 A1.** Rationale:

- It closes a Phase 1 robustness gap that `72e696e` did not.
- It contains zero Phase 2 work (no `class Daemon`, no `Author = Daemon` alias, no internal `daemon_id` parameter renames).
- A1 (Phase 2 commit 1) *depends on* this loader existing, because A1's `Author = Daemon` aliases will need to flow through the alias surface to be transparent to old call sites.
- Treating it as Phase 1 Part 2.5 keeps the parent plan's phase boundaries clean — Phase 1 = paths preserved; Phase 2 = identifiers renamed.

**Suggested commit message for task #17:**
```
rename Phase 1 Part 2.5: deep-submodule alias loader + missing shim surfaces

- tinyassets/_rename_compat.py: add _RenameAliasLoader + meta-path finder
  + install_module_alias() helper. Closes deep-submodule import gap left
  by Phase 1 Part 2 sys.modules-rebind-only shim.
- fantasy_author/__init__.py + domains/fantasy_author/__init__.py: route
  through install_module_alias for transparent submodule aliasing.
- fantasy_author/__main__.py + domains/fantasy_author/phases/__init__.py:
  CLI + phases sub-package shims (Phase 1 contract).
- tinyassets/discovery.py: rename_compat_enabled() branch appends
  fantasy_author to discovered domain list while alias live.
- Mirror byte-equal to canonical tinyassets/.

Phase 1 Part 2.5 of docs/exec-plans/active/2026-04-15-author-to-daemon-rename.md.
Closes the Phase 1 robustness contract before Phase 2 A1 begins.
```

**KG-hardness aside (dev's other ask).** Dev's audit asks for navigator confirmation that `tinyassets/knowledge/models.py`'s `FactHardness` + `FactHorizon` enums are independent of the in-flight #17 follow-up. **Confirmed independent.** Diff is pure additive (two new enums + 3 back-compat aliases at end of file); not entangled with #17 (synthesis-skip / scene-scoped KG cleanup) or memory-scope work. Safe to ship as the standalone `[KG-HARDNESS]` commit.

---

## 6. Higher-priority flags surfaced during this audit

None directly higher than #6/#7. But two adjacent observations the lead should weigh:

**(i) Layer-3 rename design note (`docs/design-notes/2026-04-19-universe-to-workflow-server-rename.md`, awaiting host §5 answers) sequences AFTER Phase 1 Part 2 lands.** Specifically, layer-3 task #28 (module rename `tinyassets/universe_server.py` → `tinyassets/workflow_server.py`) registers a new alias in `tinyassets/_rename_compat.py` — and #6 is touching that file right now. Dispatch order: #6 → host §5 answers → layer-3 tasks. No collision risk if sequenced correctly, but a *parallel* claim of layer-3 #28 against #6 would race on `_rename_compat.py`.

**(ii) "Pre-existing dirt" task #7 partially overlaps with the rename surface.** Files like `tests/test_author_server_api.py`, `tests/test_graph_topology.py`, `tests/test_synthesis_skip_fix.py` are dirty in the working tree but explicitly not part of #6. They likely test the new `daemon_server` shape and need their own commit *after* #6. Dev should grep them against the new module surface before committing — if they import `workflow.author_server`, they may be testing legacy behavior or may already be migrated. Worth a quick audit pass as part of #7 resolution.

---

## 7. Summary for the lead

- **Phase 0:** done.
- **Phase 1 Part 1:** done.
- **Phase 1 Part 2:** STAGED; task #6 in flight. Verifier full-pytest is the gate.
- **Phase 2-4:** NOT started; fully dispatchable as 8 atomic commits (A1-A5, B1, C1, C2) per §5.
- **Phase 5:** blocked on D1 release-cycle bake.
- **Total remaining commits:** 8 (excluding #6 and the time-gated D1).
- **Total remaining dev-days:** ~3-4 with 2 devs in parallel; ~5-6 serial.
- **Sequencing flag:** layer-3 design-note tasks must wait for #6 to commit before claiming `_rename_compat.py`.
