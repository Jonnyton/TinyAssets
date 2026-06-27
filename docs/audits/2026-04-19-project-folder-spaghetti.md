# Project-Folder Spaghetti Audit

**Date:** 2026-04-19
**Author:** navigator
**Scope:** Top-level layout of `tinyassets/` package — flat modules, subpackages, coupling, duplication.
**Method:** Walked file inventory + LOC + import fan-in/out + grep for known patterns. Cross-ref `docs/design-notes/2026-04-19-modularity-audit.md` (codex's earlier hotspot list) and incorporated its 3 findings; expanded with 7 more.
**Verification:** All file paths + line counts as of 2026-04-19. No code modified during audit.

---

## Top-line picture

- 35 flat `.py` modules at `tinyassets/` root + 16 subpackages.
- The 5 largest modules account for 16,470 LOC total (≈75% of `tinyassets/` non-subpackage code):
  - `universe_server.py` — **9,895 LOC, 198 def's, 23 import-fan-in** (this is the spaghetti).
  - `daemon_server.py` — 3,575 LOC, 113 functions/classes, schema + repo + service + query layer mixed.
  - `runs.py` — 1,496 LOC.
  - `work_targets.py` — 820 LOC.
  - `graph_compiler.py` — 684 LOC.
- Half the flat-modules (≥17) average <300 LOC and could collapse into 4-5 cohesive subpackages.
- Three known duplications: NodeScope (memory subpackage), compat naming, server-shim/canonical pair.

The dominant pattern is *file-as-namespace*: a new concept gets a new top-level `tinyassets/foo.py`, regardless of whether it's a library function (50 lines), a domain primitive (300 lines), or a god-module (10k lines). The result is 35 unrelated names competing in `tinyassets/`.

---

## Hotspots, ranked by clarity-uplift

Ranking: how much does untangling this make the repo *easier to reason about for a fresh contributor reading PLAN.md and trying to find where a given concept lives*. #1 has the largest uplift; #10 the smallest.

### #1 — `tinyassets/universe_server.py` is a 10k-line god-module (carry-over from codex modularity audit §3.1)

**Symptom.** Single file mixes engine operations, domain-facing world queries, branch authoring, run control, judging, rollback/versioning, goals, gates, and wiki behavior. 198 function definitions in one namespace.

**Evidence.**
- `tinyassets/universe_server.py` — 9,895 LOC, 357 KB.
- `universe()` action dispatch table at `:1154` — 26 actions in one if/elif tree.
- `extensions()` at `:3644` — multiple sub-dispatch tables (`_BRANCH_ACTIONS:5883`, `_RUN_ACTIONS:6598`, `_JUDGMENT_ACTIONS:7367`).
- 23 files import from `workflow.universe_server` (high fan-in into a god-module = high blast radius for any change).

**Why it's debt.** Tool shape is architecture (PLAN.md cross-cutting principle); the actual shape today is "one file + many action strings." Any change in any sub-domain (judging logic, branch authoring, wiki) touches the same file. Engine/domain separation (the §11 task #11 design note) is materially harder because domain-specific behavior (`query_world`, canon flows) sits inside the engine shell.

**Refactor shape.** Two-phase. (1) Extract sub-dispatch tables into mounted submodules — `tinyassets/api/branches.py`, `tinyassets/api/runs.py`, `tinyassets/api/judgments.py`, `tinyassets/api/goals.py`, `tinyassets/api/wiki.py`. Each registers its actions with a shared FastMCP `mount()` in the integration shell. (2) Move domain-specific actions out to `domains/fantasy_daemon/api/` once the engine/domain separation note (#11) lands. The integration shell stays as a routing surface, not the place action logic lives. Per FastMCP's `mount()` pattern (referenced in codex's audit).

**Cost.** ~3-4 dev-days for phase 1 (extraction without behavior change); phase 2 dovetails with #11 dispatch sequence.

**Sequencing.** This is the *single largest* clarity uplift in the repo. But it must wait for layer-3 universe→workflow server rename (`docs/design-notes/2026-04-19-universe-to-workflow-server-rename.md` + STATUS task #25 + the layer-3 §5 design note Qs) AND for engine/domain separation note (#11) to settle. Fragmenting the file before either of those lands creates merge-conflict pain.

---

### #2 — `tinyassets/daemon_server.py` mixes 5+ bounded contexts (carry-over from codex §3.3)

**Symptom.** Same anti-pattern as #1, smaller scale: schema + repository + service + query layer in one file.

**Evidence.**
- `tinyassets/daemon_server.py` — 3,575 LOC, 113 functions/classes.
- `:106-392` defines host DB schema inline.
- Same file: account/auth, requests/votes, notes/work-targets, branch definitions, goals/gate claims, search/read models (`goal_leaderboard:3102`, `search_nodes:3311`).

**Why it's debt.** Storage equivalent of #1. Cross-context helper reuse via direct calls instead of explicit service seams.

**Refactor shape.** Split by storage context (per codex's recommendation):
- `tinyassets/storage/accounts.py` (or `tinyassets/accounts/`)
- `tinyassets/storage/universes_branches.py`
- `tinyassets/storage/requests_votes.py`
- `tinyassets/storage/notes_work_targets.py`
- `tinyassets/storage/goals_gates.py`
- Keep `_connect()` + migration bootstrap shared in `tinyassets/storage/__init__.py`.

**Cost.** ~2 dev-days. Less risky than #1 because read API is more stable.

**Sequencing.** Codex flagged this as defer-until-uptime/rename-blockers-quieter; agree. Touch after #1 phase 1 lands — same contributor headspace.

---

### #3 — 35 flat modules at `tinyassets/` root with no thematic grouping

**Symptom.** The package root is 35 unrelated `.py` files. Three thematic clusters could collapse most of them, but none exists today as a subpackage.

**Evidence.** Top-level non-subpackage files include:
- *Bid market cluster:* `node_bid.py` (386 LOC), `bid_execution_log.py` (139 LOC), `bid_ledger.py` (32 LOC), `settlements.py` (120 LOC). Four files, ~677 LOC, all about per-node paid-market mechanics. **Should be `tinyassets/bid/`** (or `tinyassets/market/`).
- *Identity / actor cluster:* `identity.py` (?), `auth/` (subpackage), `singleton_lock.py` (200 LOC). Auth+identity already partially packaged.
- *Server shells cluster:* `universe_server.py`, `daemon_server.py`, `mcp_server.py`, `author_server.py` (shim), `__main__.py`. Four/five entry points + shims at root with no `tinyassets/servers/` namespace.
- *Workflow runtime cluster:* `dispatcher.py`, `runtime.py`, `runs.py`, `work_targets.py`, `branches.py`, `branch_tasks.py`, `producers/` (subpackage), `executors/` (subpackage), `subscriptions.py`. Could collapse to `tinyassets/runtime/` package with current `runtime.py` becoming `tinyassets/runtime/__init__.py` or `core.py`.
- *Knowledge model cluster:* `notes.py`, `packets.py`, `protocols.py`, `registry.py`, `domain_registry.py`, `preferences.py`. These are all "small typed surfaces" — could be `tinyassets/types/` or stay flat if sufficiently distinct.

**Why it's debt.** A new contributor reading PLAN.md and trying to find "where do node bids live?" has to grep — there's no `tinyassets/bid/` to look at. Worse: the four bid files are sized 32 / 120 / 139 / 386 LOC, none individually big enough to deserve top-level visibility, but together they're a subsystem.

**Refactor shape.** Introduce 3-4 thematic subpackages:
- `tinyassets/bid/` (consolidate 4 bid files)
- `tinyassets/servers/` (move `universe_server.py`, `daemon_server.py`, `mcp_server.py`, `author_server.py`)
- `tinyassets/runtime/` (consolidate dispatcher/runtime/runs/work_targets/branches/branch_tasks/subscriptions)

Mechanical work; well-supported by an alias-shim pattern for one-release back-compat.

**Cost.** ~1.5 dev-days for the three subpackage moves with shim back-compat.

**Sequencing.** Defer until after layer-3 rename (which is *also* a top-level module move). Bundling rearrangements minimizes alias-shim debt.

---

### #4 — Two NodeScope hierarchies in `tinyassets/memory/` (known via memory note `project_node_scope_dedup_post_2c.md`)

**Symptom.** `tinyassets/memory/node_scope.py` (277 LOC, tuple-based SliceSpec/ExternalSource) and `tinyassets/memory/scoping.py` (356 LOC, list-based equivalents). Two parallel implementations of the same primitive.

**Evidence.**
- `tinyassets/memory/node_scope.py:277`
- `tinyassets/memory/scoping.py:356`
- Memory `project_node_scope_dedup_post_2c.md` already tracks the dedup as "after flag flip."

**Why it's debt.** Active drift risk — patches to one don't propagate to the other; consumers must know which to import. Documented technical debt that hasn't been retired.

**Refactor shape.** Pick the canonical shape (likely `scoping.py` — list-based aligns with the post-2c reshape). Migrate consumers; delete `node_scope.py`. Per memory note, gated on STATUS task #19 (Stage 2c flag flip).

**Cost.** ~0.5 dev-day once Stage 2c flag flips.

**Sequencing.** Already gated correctly. No new action needed; flag the urgency once #19 fires.

---

### #5 — `compat.py` + `_rename_compat.py` at the same level (naming collision risk)

**Symptom.** Two files with `compat` in the name at `tinyassets/` root, with overlapping conceptual purpose but different scopes.

**Evidence.**
- `tinyassets/compat.py` (90 LOC, last modified 2026-04-05) — purpose unverified during this audit.
- `tinyassets/_rename_compat.py` (188 LOC, last modified 2026-04-19) — author/daemon rename compat infra.

**Why it's debt.** Two `compat`-named files invite confusion about which is canonical. The `_` prefix on one signals "internal" but doesn't clarify scope vs the unprefixed one. A future contributor adding a new compat shim won't know which file to extend.

**Refactor shape.** Read `compat.py` to confirm scope, then either (a) merge into a single `tinyassets/compat/` package with submodules per domain (`compat/imports.py`, `compat/rename.py`, etc.), or (b) rename one to make the scope distinction explicit (`tinyassets/_rename_compat.py` → `tinyassets/_alias_loader.py` if its real role is alias-loading).

**Cost.** ~0.5 dev-day investigation + rename. Mechanical.

**Sequencing.** Defer until after Phase 5 of author-daemon rename — `_rename_compat.py` will be deleted then anyway, and the question dissolves.

---

### #6 — `tinyassets/discovery.py` couples to repo layout instead of installed runtime (carry-over from codex §3.2)

**Symptom.** Domain discovery scans the source tree for `domains/*/skill.py`. Now also injects rename-compat alias `fantasy_author` into discovery results.

**Evidence.**
- `tinyassets/discovery.py:29-66` — filesystem scan.
- `tinyassets/discovery.py:66` — rename-compat alias injection.
- `tinyassets/discovery.py:101+` — import-path construction from directory names.

**Why it's debt.** Couples discovery to checked-out layout; leaks rename-compat policy into plugin discovery; makes installed-extension distribution second-class.

**Refactor shape.** Move to `importlib.metadata.entry_points(group="workflow.domains")` per PyPA spec (codex's audit cites this). Keep filesystem scan as a dev-mode fallback for editable worktrees. Pull rename-compat alias out of discovery — compat belongs in import shims, not in the registry contract.

**Cost.** ~1 dev-day. New entry-point group declaration in `pyproject.toml`; installed-domain test coverage.

**Sequencing.** Defer until after rename Phase 5 (so the alias-injection branch can disappear at the same time discovery is rewritten).

---

### #7 — `tinyassets/author_server.py` is a 1.2 KB shim at the same level as `tinyassets/daemon_server.py` (3.5k LOC)

**Symptom.** A 30-line back-compat shim and a 3500-line canonical module at the same package level, both named `*_server.py`. The shim only exists during the rename window.

**Evidence.**
- `tinyassets/author_server.py` — 1,199 bytes, sys.modules-rebind shim.
- `tinyassets/daemon_server.py` — 121,414 bytes (3575 LOC), canonical.

**Why it's debt (mild).** Visual noise that suggests two separate modules when they're aliases. Mostly self-resolving — the shim deletes at Phase 5 of the rename.

**Refactor shape.** No action; resolves at Phase 5 (D2 in rename-status §5 dispatch list).

**Cost.** Zero — already on the dispatch path.

**Sequencing.** Auto-resolves.

---

### #8 — `tinyassets/notes.py` (259 LOC) carries vestigial language about "STEERING.md" (cross-ref to Part A)

**Symptom.** Module docstring says "Notes replace STEERING.md, editorial output, and verdict routing" — historical context line that's no longer load-bearing.

**Evidence.** `tinyassets/notes.py:3-4`.

**Why it's debt (mild).** A reader of `notes.py` for the first time encounters an obsolete cross-reference. Confusing for new contributors.

**Refactor shape.** Per Part A removal plan (`docs/exec-plans/active/2026-04-19-steering-md-removal.md`), trim the historical reference in Commit 1 of that plan.

**Cost.** ~5 min, already scoped in Part A.

**Sequencing.** Ship with Part A.

---

### #9 — `tinyassets/runs.py` (1,496 LOC) and `tinyassets/work_targets.py` (820 LOC) operate on the same domain (run scheduling) but live as flat siblings

**Symptom.** Two adjacent large modules with overlapping conceptual surface (run lifecycle + work-target management).

**Evidence.**
- `tinyassets/runs.py` — 1,496 LOC, 8 import-fan-in.
- `tinyassets/work_targets.py` — 820 LOC.
- Both touch dispatcher (`tinyassets/dispatcher.py`, 313 LOC) + branch_tasks (`tinyassets/branch_tasks.py`, 444 LOC).

**Why it's debt.** Run scheduling is a coherent subsystem — runs + work-targets + dispatcher + branch-tasks + producers + executors. Today it's spread across 4 flat files + 2 subpackages.

**Refactor shape.** Consolidate as `tinyassets/runtime/` package per #3 above. Specific layout:
- `tinyassets/runtime/__init__.py` (re-exports current `runtime.py` API)
- `tinyassets/runtime/runs.py`
- `tinyassets/runtime/work_targets.py`
- `tinyassets/runtime/dispatcher.py`
- `tinyassets/runtime/branch_tasks.py`
- `tinyassets/runtime/producers/` (move from current `producers/`)
- `tinyassets/runtime/executors/` (move from current `executors/`)

**Cost.** Bundled with #3; ~0.5 dev-day attributable.

**Sequencing.** Same as #3.

---

### #10 — `tinyassets/api/__init__.py` exists but `api/` is mostly empty

**Symptom.** A `tinyassets/api/` subpackage exists but doesn't host the actual API surfaces (those live in the god-modules `universe_server.py` and `daemon_server.py`).

**Evidence.** `tinyassets/api/` directory has `__init__.py` + small modules; the actual MCP tool definitions live in `tinyassets/universe_server.py:1079` etc.

**Why it's debt (low priority).** Orphan-shaped subpackage that suggests where API surfaces *should* live but doesn't actually host them.

**Refactor shape.** Use `tinyassets/api/` as the destination for the #1 hotspot's submodule extraction (`tinyassets/api/branches.py`, `tinyassets/api/runs.py`, etc.). Doesn't need its own task — it dovetails into #1.

**Cost.** Zero attributable; absorbed into #1.

**Sequencing.** Absorbed into #1.

---

## Cross-cutting observations

**Five hotspots are *gated* on existing in-flight work**, not blocked-by-design:

| Hotspot | Gated on |
|---|---|
| #1 universe_server god-module | layer-3 rename (STATUS #25) + engine/domain separation (#11) |
| #2 daemon_server context mixing | uptime/rename quieter |
| #3 flat-modules → subpackages | layer-3 rename (avoid alias-shim layering) |
| #4 NodeScope dedup | Stage 2c flag flip (STATUS #19) |
| #6 discovery entry-points | rename Phase 5 |

Two are ship-anytime: **#5 compat naming** (resolves at Phase 5 anyway) and **#7 author_server shim** (auto-resolves at Phase 5).

One is **shipping with Part A** (#8 STEERING.md docstring trim).

Two need **dedicated dispatch** post-gate: #1 and #2 are the real work; everything else is mechanical or auto-resolving.

**Total dev-day estimate for the full untangling sweep:** ~7-8 dev-days, sequenced over the next ~3 phase boundaries. The biggest single uplift (#1) is also the biggest single block of work (~3-4 days).

---

## Out of scope for this audit

- **Tests/ sprawl.** 128 test files at `tests/` root. Same flat-namespace anti-pattern as `tinyassets/`, but tests have weaker coupling and the cost of moving them is higher than the uplift. Defer to its own audit if a contributor surfaces friction.
- **`fantasy_daemon/` package layout.** Domain-specific; should follow whatever pattern engine/domain separation (#11) establishes.
- **Packaging mirror.** The mirror is byte-equal to canonical by construction; refactor-when-canonical-refactors. No standalone mirror cleanup.
- **Test coverage gaps.** Outside this audit's brief.

---

## Summary for Part C (PLAN.md.draft)

The PLAN.md revision should articulate the **target module layout** as a first-class architectural commitment, not just describe the current state. Specifically:

1. **`tinyassets/api/`** as the canonical home for MCP tool surfaces (mounted submodules, not god-modules).
2. **`tinyassets/storage/`** as the canonical home for schema + bounded-context storage layers (no more god-`daemon_server.py`).
3. **`tinyassets/runtime/`** as the canonical home for run scheduling primitives (runs / work-targets / dispatcher / branch-tasks / producers / executors).
4. **`tinyassets/bid/`** as the canonical home for paid-market mechanics (consolidates 4 flat files).
5. **`tinyassets/servers/`** as the canonical home for entry-point shells (the integration layer that mounts api submodules).

These five subpackages absorb ~22 of the 35 flat modules. The remaining 13 (auth/, checkpointing/, constraints/, context/, evaluation/, judges/, knowledge/, learning/, memory/, planning/, providers/, retrieval/, ingestion/) are already correctly subpackaged or correctly flat (small typed surfaces like `protocols.py`, `exceptions.py`, `notes.py`).

Part C will codify this as the target layout + sequence the migration.
