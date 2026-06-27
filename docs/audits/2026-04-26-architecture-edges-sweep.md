---
title: Architecture edges sweep — refactor + retire candidates ("button up the edges")
date: 2026-04-26
author: navigator
status: read-only discovery audit — host curates dispatch
companion:
  - docs/audits/2026-04-26-legacy-branding-comprehensive-sweep.md (sibling sweep — branding vs architecture)
  - docs/audits/2026-04-27-project-wide-shim-audit.md (5-arc shim ledger)
  - docs/audits/2026-04-25-universe-server-decomposition.md (universe_server.py decomp)
  - docs/audits/2026-04-25-engine-domain-api-separation.md (engine/domain seam)
  - docs/design-notes/2026-04-18-full-platform-architecture.md (supersedes phased plan per AGENTS.md)
  - docs/design-notes/2026-04-24-architecture-audit.md (multi-week findings)
  - feedback_no_shims_ever
load-bearing-question: Where are the rough edges — modules with confused responsibility, naming that drifted past its phase, dead branches preserved by no caller, code in the wrong place? Refactor or retire candidates only — host directive: "button up, don't unplug."
audience: lead, host
---

# Architecture edges sweep

## TL;DR

**14 architectural edge findings** across 5 categories. Each is "button up" not "unplug" — the goal is a more legible architecture, not a torn-out one.

| Category | Findings | Total blast radius |
|---|---|---|
| **A. Top-level package layout — engine/domain seam violations** | 3 | LARGE (3) — affects rename arc + decomp arc framing |
| **B. Naming drift — phased identifiers surviving past their phases** | 4 | MEDIUM (2) — visible-but-non-blocking confusion |
| **C. Module-pair naming confusion (tinyassets/X.py vs tinyassets/api/X.py)** | 2 | SMALL (1) — readability hit, low rewrite cost |
| **D. Design-note + spec-doc graveyard** | 4 | MEDIUM (2) — drives §2.3 of branding audit but architecturally relevant |
| **E. Top-level orphan dirs / files** | 1 | SMALL (1) — `fantasy_author_original/` snapshot deletion-pending |

**Headline:** the highest-leverage architectural finding is **A.1 — top-level `fantasy_daemon/` package** carries 122 .py files including `api.py`, `__main__.py`, `branch_registrations.py`, `author_server.py` shim. It violates AGENTS.md "Engine and Domains" principle — engine code (FastAPI HTTP layer, branch registration, CLI entry) should live in `tinyassets/`, not in a domain-named top-level package. The domain package proper is `domains/fantasy_daemon/`. The top-level `fantasy_daemon/` is the rename arc's incomplete state — should be unpacked into `tinyassets/` (engine pieces) + `domains/fantasy_daemon/` (domain pieces).

**Recommendation:** treat A.1 as the next major architectural arc after Arc B/C/Phase 6. Sketch the unpack plan as a design note, then execute over multiple commits.

**The methods-prose evaluator design note (Concern row 2026-04-26 in STATUS) needs reframing per the host directive — that's a doc edit, not architecture-edge per se, but flagged in §D.**

---

## 1. Methodology

Used `code-simplification` + `improve-codebase-architecture` skill rubrics:
- Module boundaries and naming clarity
- Coupling between supposedly-independent surfaces
- Dead paths preserved by no caller
- Helpers / utility / common grab-bags
- Phase-named or version-numbered identifiers surviving past their phase
- Modules whose public surface drifted from their docstring
- Tests whose name no longer matches what they test
- Design notes describing systems that no longer exist
- Top-level packages violating engine/domain seam (per AGENTS.md "Engine and Domains")

Searched: `tinyassets/`, `domains/`, `tests/`, `fantasy_daemon/`, `fantasy_author/`, top-level `*.py`, `docs/specs/`, `docs/planning/`, `docs/design-notes/`. Excluded `.claude/worktrees/`, `__pycache__`, `output/`, `.venv/`, `fantasy_author_original/` (separate housekeeping per branding audit §2.7), `.git/`.

Per host directive: **NO REMOVAL** without explicit approval. Findings recommend refactor / retire-with-archive / annotate, not delete.

---

## 2. Findings

### A — Top-level package layout violations

#### A.1 — `fantasy_daemon/` (top-level) is a 122-file package mixing engine + domain code

> **REFRAMED 2026-04-27 (navigator).** Deeper inventory after the audit landed: **118 of 122 files are SHIMS** (`from workflow.X import *` re-exports). Only 4 files have content: `__main__.py` (2295 LOC, daemon CLI), `api.py` (2625 LOC, FastAPI), `branch_registrations.py` (113 LOC), `testing/__main__.py` (3 LOC vestigial). Arc is **~6-9h dev work, not multi-week.** Canonical scope + 4-phase migration plan + 7 host-decision asks live in `docs/design-notes/2026-04-26-fantasy-daemon-unpack-arc.md`. The §A.1 narrative below is preserved as the original audit signal — the scope note is authoritative.

**Location:** `/fantasy_daemon/` (repo root).

**Size:** 122 tracked .py files. Subdirs: `auth/`, `branches/`, `checkpointing/`, `constraints/`, `desktop/`, `evaluation/`, `graphs/`, `ingestion/`, `knowledge/`, `learning/`, `memory/`, `nodes/`, `phases/`, `planning/`, `producers/`, `providers/`, `retrieval/`, `state/`, `tools/`. Plus top-level `api.py` (FastAPI HTTP layer), `__main__.py` (CLI entry), `author_server.py` (shim), `branch_registrations.py`, `branches.py`, etc.

**What's wrong:** Per AGENTS.md "Engine and Domains" principle (PLAN.md §"Engine And Domains"):
- ENGINE code (HTTP API, branch registration, CLI entry, sandbox, retrieval, knowledge) lives in `tinyassets/`
- DOMAIN-SPECIFIC code (story-specific phases, world_state schemas, fantasy nodes) lives in `domains/<domain>/`

The top-level `fantasy_daemon/` violates this seam:
- `fantasy_daemon/api.py` is a FastAPI HTTP layer ("Multi-universe file-based adapter") — that's ENGINE, should be in `tinyassets/api/` or `tinyassets/http/`.
- `fantasy_daemon/auth/`, `fantasy_daemon/checkpointing/`, `fantasy_daemon/constraints/`, `fantasy_daemon/ingestion/`, `fantasy_daemon/knowledge/`, `fantasy_daemon/memory/`, `fantasy_daemon/retrieval/` — all ENGINE concerns. `tinyassets/` already has `tinyassets/checkpointing/`, `tinyassets/auth/`, `tinyassets/ingestion/`, `tinyassets/knowledge/`, `tinyassets/memory/`, `tinyassets/retrieval/` — the duplication is real (rename arc moved `fantasy_author/X` → `fantasy_daemon/X` but didn't merge into `tinyassets/X` where the canonical lives).
- `fantasy_daemon/graphs/`, `fantasy_daemon/phases/`, `fantasy_daemon/state/`, `fantasy_daemon/nodes/` — DOMAIN concerns. Should be in `domains/fantasy_daemon/` (some already are).
- `fantasy_daemon/__main__.py` — CLI entry. This IS legitimately a top-level module per Python conventions (`python -m fantasy_daemon`). Probably stays at top-level but should re-export from `workflow.daemon_server.__main__` once that exists.

**Tests using top-level path** (separate from `domains.fantasy_daemon.*` imports):
- `tests/test_api.py`, `tests/test_api_edge_cases.py`, `tests/test_author_server_api.py` — use `fantasy_daemon.api`
- `tests/test_unified_execution.py` — uses `fantasy_daemon.__main__` + `fantasy_daemon.branch_registrations`
- `tests/test_integration.py` — uses `fantasy_daemon.__main__`
- ~56 test sites total.

**Recommendation:** REFACTOR over multiple commits.
1. Inventory the 122 .py files: which are engine, which are domain, which are duplicates of `tinyassets/`-tree counterparts.
2. For each engine-flavored subdir (`auth/`, `checkpointing/`, etc.), confirm `tinyassets/` has the canonical and `fantasy_daemon/` is a duplicate or older snapshot.
3. Migrate `fantasy_daemon/api.py` → `tinyassets/http/api.py` (or `tinyassets/api/http.py`). Update imports.
4. Migrate domain pieces (`graphs/`, `phases/`, `state/`, `nodes/`) → `domains/fantasy_daemon/` if not already there. Reconcile content.
5. Final state: top-level `fantasy_daemon/` collapses to `__init__.py` + `__main__.py` (CLI entry only), or dies entirely if `python -m tinyassets` becomes the canonical entrypoint.

**Blast radius: 3 (LARGE).** Touches 122 .py files + ~56 test sites + AGENTS.md/PLAN.md doc updates + CLI entry-point change. Multi-week arc; sketch as a design note before dispatch.

**Priority rationale:** highest-leverage finding. The rename arc (Arc B) is closing the `fantasy_author` → `fantasy_daemon` MODULE-NAME rename, but didn't address the `fantasy_daemon` top-level package's CONTENT-VS-LAYOUT violation. Closing the rename without closing this leaves a confused architecture where future contributors can't tell which `branches/` / `auth/` / `checkpointing/` is canonical.

---

#### A.2 — `fantasy_author/` (top-level) — 2-file alias module pending Arc B Phase 3 deletion

**Location:** `/fantasy_author/` (repo root).

**Size:** 2 .py files (`__init__.py` 50 LOC, `__main__.py` ~3 LOC). Per `fantasy_author/__init__.py` docstring: "Fantasy Author — backward compatibility shim. This package re-exports from tinyassets/ and domains/fantasy_author/."

**What's wrong:** Already scheduled for Arc B Phase 3 deletion per `docs/exec-plans/active/2026-04-26-decomp-arc-b-prep.md`. NOT a new finding — flagging here for completeness.

**Recommendation:** RETIRE (with rest of Arc B).

**Blast radius: 1 (SMALL).** Already scoped.

---

#### A.3 — `fantasy_author_original/` (top-level) — pre-rename snapshot

**Location:** `/fantasy_author_original/` (repo root).

**What's wrong:** Pre-rename snapshot of the original `fantasy_author/` package. Referenced by `pyproject.toml:98 extend-exclude` so ruff/mypy skip it. Per `docs/audits/2026-04-19-project-folder-spaghetti.md`, this was kept during the rename for reference + rollback. The rename is complete; the rollback window has long closed.

**Recommendation:** RETIRE — `git rm -r fantasy_author_original/` + delete the `extend-exclude` line. Not in scope for this audit (separate housekeeping per branding audit §2.7), but flagging.

**Blast radius: 1 (SMALL).** No callers in canonical tree.

---

### B — Naming drift / phased identifiers surviving past their phases

Per AGENTS.md "Full-platform architecture supersedes phased plan; migrate candidate" (STATUS Concern 2026-04-18 — `docs/design-notes/2026-04-18-full-platform-architecture.md`). Phase-named identifiers were a useful organizing tool DURING those phases but become confusing AFTER ship.

#### B.1 — phase-named tests for shipped phases

**Location:**
- `tests/test_phase7.py`, `test_phase7_h2_goals_cutover.py`, `test_phase7_h3_branch_cutover.py` (Phase 7 — storage-package split, shipped)
- `tests/test_unified_execution.py` (was `test_phase_d_unified_execution.py`)
- `tests/test_dispatcher_queue.py` (was `test_phase_e_dispatcher.py`)
- `tests/test_goal_pool.py` (was `test_phase_f_goal_pool.py`)
- `tests/test_node_bid.py` (was `test_phase_g_node_bid.py`)
- `tests/test_activity_log_parity.py`, `test_node_bid_claim_stress.py`, `test_daemon_dashboard.py`, `test_dashboard_panes.py` (were `test_phase_h_*`)

**Status 2026-05-02:** Phase D-H shipped-phase test filenames are behavior-named. Phase 7 / Phase 6.2+ filenames remain separate because their closure gates are tracked elsewhere.

**Recommendation:** DONE for Phase D-H; do not reopen unless a stale filename reference breaks tooling.

**Blast radius: 2 (MEDIUM).** 11 test files renamed. Risk: if any task tracker / runbook still refers to "phase E tests," those references break — find/replace them too.

**Priority rationale:** Each rename is small. The collective drift is real — 11 phase-named tests in `tests/` is a smell.

---

#### B.2 — `docs/specs/phase_*_preflight.md` — pre-flight specs for shipped phases

**Location:** `docs/specs/phase_d_preflight.md` (20 fantasy_author refs), `phase_e_preflight.md` (62 phase refs), `phase_f_preflight.md` (42), `phase_g_preflight.md` (19), `phase_h_preflight.md` (71).

**What's wrong:** Pre-flight specs are by definition pre-implementation. Once the phase ships, the spec is either:
- A historical artifact (record of what was planned) — belongs in `docs/historical/specs/`, OR
- A living spec describing the surface (probably duplicated in PLAN.md or actual module docstrings)

Today they sit in `docs/specs/` alongside active specs. New contributor can't tell which are live design vs historical.

**Recommendation:** MOVE to `docs/historical/specs/` with archive header, OR consolidate non-superseded sections into PLAN.md. ~1-2h, gated on confirmation that each phase actually shipped (per STATUS — Phases D-H have shipped; R7/Phase 7 close-out is host-decision-pending).

**Blast radius: 2 (MEDIUM).** 5 doc files; contributors reading specs/ get a clearer surface.

---

#### B.3 — `docs/specs/phase7_github_as_catalog.md` — shipped phase 7 spec

**Location:** `docs/specs/phase7_github_as_catalog.md`.

**What's wrong:** Phase 7 (storage-package split) is host-decision-pending close-out per STATUS. Once R7 confirms, this spec moves to `docs/historical/`.

**Recommendation:** WAIT for R7 close, then move with §2.4 of branding audit.

**Blast radius: 1 (SMALL).**

---

#### B.4 — `tests/test_phase7.py` and similar — same as B.1

Already covered in B.1. Folds into the same rename pass.

---

### C — Module-pair naming confusion

#### C.1 — `tinyassets/branches.py` (1137 LOC, data models) vs `tinyassets/api/branches.py` (2821 LOC, MCP dispatcher)

**Location:**
- `tinyassets/branches.py` — "Community Branches — data models for community-designed LangGraph topologies." Defines `BranchDefinition`, `EdgeDefinition`, etc.
- `tinyassets/api/branches.py` — "Branch authoring + node CRUD subsystem — extracted from `tinyassets/universe_server.py` (Task #15 — decomp Step 8)." 17 `_ext_branch_*` handlers, dispatch tables.

**What's wrong:** Two modules named `branches.py` with different responsibilities. `tinyassets/api/branches.py` imports `from workflow.branches import BranchDefinition` 5+ times, which is fine — but a contributor opening the wrong `branches.py` first will be confused.

**Recommendation:** RENAME `tinyassets/branches.py` → `tinyassets/branch_models.py` (or `tinyassets/branch_schema.py`). Mechanical: ~5 import sites + module file rename. ~20 min.

Alternative: move `tinyassets/branches.py` content into `tinyassets/api/branches.py` if it's only used by the API module — verify with `git grep "from workflow.branches import"`. Likely cleaner if there's no non-API caller.

**Blast radius: 1 (SMALL).** Internal rename, test pass green if imports update.

**Priority rationale:** small but real readability win.

---

#### C.2 — `tinyassets/runs.py` (2884 LOC, run orchestration) vs `tinyassets/api/runs.py` (1485 LOC, MCP dispatcher)

**Location:**
- `tinyassets/runs.py` — "Run orchestration for community-designed branches. Stores run metadata and per-step events..."
- `tinyassets/api/runs.py` — "Run-execution subsystem — extracted from tinyassets/universe_server.py (Task #11 — decomp Step 4)."

**What's wrong:** Same shape as C.1. Two modules named `runs.py` — the MCP-API shell (`tinyassets/api/runs.py`) imports from the orchestration backend (`tinyassets/runs.py`) at multiple sites.

**Recommendation:** RENAME `tinyassets/runs.py` → `tinyassets/run_orchestrator.py` (or `tinyassets/run_execution.py`). Same as C.1.

**Blast radius: 1 (SMALL).**

---

### D — Design-note + spec-doc graveyard

#### D.1 — Methods-prose evaluator design note needs REFRAME

**Location:** `docs/design-notes/2026-04-27-methods-prose-evaluator.md`.

**What's wrong:** Per STATUS Concern 2026-04-26 (host directive): "Methods-prose evaluator REFRAMED community-build (host directive 2026-04-26): platform won't ship as primitive; chatbot composes from existing evaluator surface + wiki rubrics. Design-note header needs reframe."

The note currently scopes a platform-shipped Evaluator subtype. Host has redirected to community-build (chatbot composes from existing primitives). The note is stale architecture.

**Recommendation:** REWRITE header + rationale to match the new direction. Effort: ~30 min. Lead-blocking for host re-review of the reframed scope.

**Blast radius: 1 (SMALL).** Doc edit only.

**Note:** I'm not editing this note autonomously per your instruction (Phase 6 lesson: "Don't edit the design note yet — let host approve scope first"). Flagging for explicit lead/host approval first.

---

#### D.2 — `docs/design-notes/2026-04-09-runtime-fiction-memory-graph.md` and friends — research notes for shipped or de-prioritized work

**Location:** Many `2026-04-09-*.md` and `2026-04-1*-*.md` design notes describe work that has either shipped (memory-scope Stage 2a/2b/2b3 — see STATUS) or been de-prioritized (some early-April research notes never converted to specs).

**What's wrong:** The `docs/design-notes/` directory has ~50 notes. Some are active design proposals; some are research artifacts; some describe shipped work; some describe pivoted-away approaches. No date-stamp / status-marker per note.

**Recommendation:** AUDIT-AND-CLASSIFY pass — each note gets a single-line front-matter status:
- `status: active` — current design proposal
- `status: shipped <date>` — describes work that landed
- `status: superseded by <doc>` — replaced by a later approach
- `status: research` — exploratory note that never became spec

Effort: 2-3h. Surface dispatch shape: dev-2 reads each note, drafts status classification, navigator/lead reviews.

**Blast radius: 2 (MEDIUM).** ~50 notes; each gets a 1-line front-matter edit.

**Priority rationale:** Keeps design-notes/ surface useful for new contributors. AGENTS.md treats it as an active-design surface; right now it's mixed.

---

#### D.3 — `docs/specs/` directory has ~30 specs without clear active/shipped/historical status

Same shape as D.2 but for `docs/specs/`. Folds into the branding audit's §2.3 dispatch.

**Recommendation:** classify each as ACTIVE / SHIPPED-MOVE-TO-HISTORICAL / SUPERSEDED. Same shape as D.2.

**Blast radius: 2 (MEDIUM).**

---

#### D.4 — `docs/exec-plans/` — many "active/" entries that are actually closed

**Location:** `docs/exec-plans/active/`.

**What's wrong:** Ls shows ~36 files in `docs/exec-plans/active/`. By definition an exec-plan is active until it lands. Some that are clearly closed (Phases D, E, F, G, H all shipped per STATUS):
- `2026-04-19-r7a-phase7-to-catalog.md` — Phase 7 close-out pending
- `2026-04-19-storage-package-split.md` — shipped
- `2026-04-19-bid-package-promotion.md` — Phase G shipped
- `2026-04-09-runtime-fiction-memory-graph.md` — large multi-month plan
- `2026-04-15-author-to-daemon-rename.md` — partial-active (Arc B Phase 1 LANDED 0cbdea9; Phases 2/3 active)

**Recommendation:** AUDIT each `docs/exec-plans/active/*.md` for landing status. Move shipped/closed plans to `docs/exec-plans/landed/<YYYY-MM>/`. Effort: ~1-2h.

**Blast radius: 2 (MEDIUM).** ~36 plan files; clearer "what's active right now" surface.

---

### E — Top-level orphan dirs / files

#### E.1 — Pre-rename snapshot tree `fantasy_author_original/`

Already covered in A.3. Folds into housekeeping.

---

## 3. Per-finding summary table

| ID | Title | Category | Blast | Effort | Dispatch-ready |
|---|---|---|---|---|---|
| A.1 | `fantasy_daemon/` top-level layout violation | Engine/domain seam | 3 | Multi-week arc | NO — sketch design note first |
| A.2 | `fantasy_author/` shim | Already-scoped | 1 | (folded into Arc B Phase 3) | NO — Arc B handles |
| A.3 | `fantasy_author_original/` snapshot | Housekeeping | 1 | 5 min | YES (after host approval) |
| B.1 | Phase-named tests rename | Naming drift | 2 | 30 min | DONE for Phase D-H; Phase 7 deferred |
| B.2 | `docs/specs/phase_*_preflight.md` archive | Doc graveyard | 2 | 1-2h | PARTIAL — gated on R7 for phase7 |
| B.3 | `docs/specs/phase7_github_as_catalog.md` | Doc graveyard | 1 | 5 min | NO — gated on R7 close |
| C.1 | `tinyassets/branches.py` rename | Naming clarity | 1 | 20 min | YES, dev-2 |
| C.2 | `tinyassets/runs.py` rename | Naming clarity | 1 | 20 min | YES, dev-2 |
| D.1 | Methods-prose evaluator note REFRAME | Stale architecture doc | 1 | 30 min | NO — host approval first |
| D.2 | `docs/design-notes/` status classification | Doc graveyard | 2 | 2-3h | YES, dev-2 |
| D.3 | `docs/specs/` status classification | Doc graveyard | 2 | (folds into branding §2.3) | PARTIAL |
| D.4 | `docs/exec-plans/active/` audit | Doc graveyard | 2 | 1-2h | YES, dev-2 |
| E.1 | `fantasy_author_original/` deletion | Housekeeping | 1 | 5 min | (same as A.3) |

**Total dispatch-ready effort: ~5-7h** spread across 4-5 dispatchable tasks.

**Total gated/multi-week effort: A.1 alone is multi-week.**

---

## 4. Recommended dispatch sequence

**Phase 1 — quick wins (current dispatch window):**
1. **C.1 + C.2** — rename `tinyassets/branches.py` → `tinyassets/branch_models.py` and `tinyassets/runs.py` → `tinyassets/run_orchestrator.py`. 2 small mechanical tasks; 40 min. Bundle if dev-2 picks up both.
2. **B.1** — rename phase-named tests. 30 min mechanical.
3. **D.2** — `docs/design-notes/` status classification. 2-3h. Per-note status front-matter.
4. **D.4** — `docs/exec-plans/active/` audit + move-to-landed. 1-2h.

**Phase 2 — gated (post-current-arcs):**
5. **B.2 + B.3** — phase preflight specs to historical. 1-2h, gated on R7.
6. **D.1** — methods-prose evaluator REFRAME after host approves new direction. 30 min.
7. **A.3 + E.1** — `fantasy_author_original/` deletion. 5 min, gated on host approval.

**Phase 3 — major arc:**
8. **A.1** — `fantasy_daemon/` top-level unpack. Multi-week. Sketch design note first; dispatch after Arc B/C/Phase 6 closes.

---

## 5. Priority rationale

**A.1** is the only "structural" finding — it changes how a future contributor reads the architecture. Every other finding is "tidying up." But the others combined make the architecture LOOK tidier without doing the structural work, which can be misleading. **Recommend dispatching the small tidying first** (Phase 1) to clear cosmetic noise, then doing A.1's design-note as a deliberate architectural arc.

The reason A.1 hasn't been done already: the rename arc was scoped as MODULE-NAME rename (`fantasy_author` → `fantasy_daemon`), not LAYOUT rename. The layout violation predates the rename — `fantasy_author/` always had this engine/domain mixing — and the rename moved the violation rather than fixing it. Fixing it requires deciding what the engine/domain seam looks like in canonical form (per AGENTS.md) and doing the move with care.

---

## 6. Decision asks for the lead → host

1. **Approve C.1 + C.2 dispatch** (rename `tinyassets/branches.py` + `tinyassets/runs.py` to disambiguating names)? Recommend yes — small mechanical wins.
2. **Approve B.1 dispatch** (rename phase-named tests to behavior-named)? Recommend yes — readability win.
3. **Approve D.2 + D.4 dispatch** (design-note status classification + exec-plan active audit)? Recommend yes — keeps planning surfaces useful.
4. **D.1 (methods-prose evaluator REFRAME)** — host-approved direction is "community-build" per STATUS Concern 2026-04-26. Confirm reframe-only, no platform shipping. Then I edit the note (or dispatch).
5. **A.1 (`fantasy_daemon/` layout) — sketch design note?** This is the multi-week structural finding. Recommend navigator drafts a design note `docs/design-notes/2026-04-27-fantasy-daemon-top-level-unpack.md` proposing the engine/domain split for that tree, then host decides scope/timing. NOT a dispatch — a planning step.
6. **A.3 / E.1 — `fantasy_author_original/` deletion timing.** Per branding audit §9 ask 6. Recommend post-Arc-B-Phase-3 (when shim infrastructure is fully gone, the snapshot is irrelevant).
7. **B.2 / B.3 — phase preflight + phase 7 spec archive timing.** Bundle with R7 close-out. Confirm.

---

## 7. What's NOT in this audit

- **Code-internal complexity** (e.g., is `tinyassets/daemon_server.py` at 3551 LOC too large? Is `tinyassets/graph_compiler.py` at 2126 LOC structured well?). Module-size profiling is a separate concern; covered partially by `docs/design-notes/2026-04-24-architecture-audit.md` and the universe_server.py decomp arc.
- **Test redundancy or coverage gaps.** Test-suite-quality audit is a separate workstream.
- **Provider-router logic, retrieval router, scheduler internals.** Domain-deep audits are out of scope; this sweep is structural/edges only.
- **Performance / cost.** Out of scope.
- **AGENTIC_SEARCH_RESEARCH.md content review.** Branding audit handles the doc-archive question; the research content is a separate read.

---

## 8. Cross-references

- `docs/audits/2026-04-26-legacy-branding-comprehensive-sweep.md` (sibling sweep)
- `docs/audits/2026-04-27-project-wide-shim-audit.md` (5-arc shim ledger)
- `docs/audits/2026-04-25-engine-domain-api-separation.md` (engine/domain seam — A.1 ratifies this work)
- `docs/audits/2026-04-25-universe-server-decomposition.md` (decomp arc — proves naming-pair clarity matters per C.1+C.2)
- `docs/design-notes/2026-04-18-full-platform-architecture.md` (supersedes phased plan per AGENTS.md — drives B.1+B.2)
- `docs/design-notes/2026-04-24-architecture-audit.md` (multi-week findings; this audit complements)
- `docs/exec-plans/active/2026-04-26-decomp-arc-b-prep.md` (Arc B; A.2 folds in)
- `docs/exec-plans/active/2026-04-19-rename-end-state.md` (R7 close-out — gates B.2/B.3)
- AGENTS.md "Engine and Domains" section
- PLAN.md §"Engine And Domains" section
- STATUS.md Concern row 2026-04-26 (methods-prose evaluator reframe — D.1)
- `feedback_no_shims_ever` (host directive driving the rename arcs)

---

## Addendum 2026-04-26 — extra heuristics (per lead directive)

After the audit landed, lead added two SWEEP 2 heuristics. Re-ran. **Both findings reinforce existing recommendations; no new structural concerns.**

### Heuristic 1: Module docstrings starting "Phase X..." where the phase has shipped

**5 modules found in canonical tinyassets/.** All 5 have docstrings that lead with a project phase identifier:

| Module | Docstring opener | Phase status | Recommendation |
|---|---|---|---|
| `tinyassets/bid/settlements.py` | "Phase G cross-host immutable settlement ledger." | Phase G shipped | REWRITE — "Cross-host immutable settlement ledger for the paid-market node-bid surface." |
| `tinyassets/branch_tasks.py` | "Phase E durable BranchTask queue." | Phase E shipped | REWRITE — "Durable BranchTask queue." |
| `tinyassets/catalog/__init__.py` | "Phase 7 — git-native storage backend." | Phase 7 close-pending | REWRITE — "Git-native catalog backend (branch / node / goal / bid YAML)." |
| `tinyassets/dispatcher.py` | "Phase E tier-aware BranchTask dispatcher." | Phase E shipped | REWRITE — "Tier-aware BranchTask dispatcher." |
| `tinyassets/identity.py` | "Phase 7.4 v1 — git author identity for commits." | Phase 7.4 shipped | REWRITE — "Git-author identity for commits authored by daemons + users." |

**Two false positives** (look like Phase X but actually describe a behavior pattern, not project phase):
- `tinyassets/retrieval/agentic_search.py` "Phase-aware agentic search policy." — "Phase-aware" describes the behavior. KEEP.
- `tinyassets/retrieval/phase_context.py` "Phase-aware retrieval configuration." — module name + docstring both describe behavior. KEEP.

**New finding — F.1 (5 sub-items): module-docstring rewrites, ~25 min dev-2 dispatch.**

This reinforces B.1 (phase-named tests rename) and B.2 (phase preflight specs to historical) — phase-as-organizational-unit has stuck around in module docstrings the same way it stuck around in test/spec names. Bundle B.1 + F.1 into one "phase-naming-cleanup" dispatch if convenient.

### Heuristic 2: util/helpers/common grab-bags with `from X import *` callers

**Canonical tinyassets/ + domains/ trees have ZERO `from X import *` patterns.** Checked. No grab-bags depending on glob imports.

`tinyassets/api/helpers.py` (142 LOC) is the closest "helpers" module. Inspected:
- Has explicit `Public surface (stable contract)` docstring listing 9 named helpers
- 15 callers, all in `tinyassets/api/*.py` siblings (legitimate API-tier shared code)
- Narrow purpose: path resolvers + safe I/O readers
- **NOT a grab-bag** by structure — it's a deliberately-designed leaf module per the universe_server.py decomp Bundle 1 plan

`tinyassets/utils/__init__.py` (1 LOC) and `tinyassets/utils/json_parsing.py` (70 LOC) — minimal namespace, clean.

**No new finding on this axis.** The codebase is structurally clean of glob-import grab-bags.

---

### Net additions to dispatch from addendum

**1 new finding (5 sub-items):**
- **F.1.1** — `tinyassets/bid/settlements.py` docstring rewrite
- **F.1.2** — `tinyassets/branch_tasks.py` docstring rewrite
- **F.1.3** — `tinyassets/catalog/__init__.py` docstring rewrite
- **F.1.4** — `tinyassets/dispatcher.py` docstring rewrite
- **F.1.5** — `tinyassets/identity.py` docstring rewrite

All bundle into one ~25-min dev-2 dispatch — mechanical sed-style docstring edits.

### Verdict

Extra heuristics didn't surface any new STRUCTURAL findings. The architecture is structurally clean of `from X import *` grab-bag patterns (good!) and the 5 phase-named module docstrings are cosmetic — they bundle naturally with the existing B.1 dispatch.

**Confidence in the original audit's recommendations: HIGH.** A.1 (`fantasy_daemon/` top-level layout) remains the only multi-week structural concern. The other 14 findings remain dispatchable as quick-wins.
