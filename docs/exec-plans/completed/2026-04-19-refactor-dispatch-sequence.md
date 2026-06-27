# Refactor Dispatch Sequence

**Date:** 2026-04-19
**Author:** navigator
**Purpose:** One document the lead reads the moment host approves PLAN.md.draft. Tells you which refactor hotspot is the first dev-claimable commit, with file collision boundary + dependencies + cost.
**Source:** `docs/audits/2026-04-19-project-folder-spaghetti.md` (Part B). Hotspot numbering matches that doc.
**Gating:** All entries below assume PLAN.md.draft is approved (host Q4). If host rejects the Module Layout commitment (Q4 option (c)), this whole sequence dissolves into ad-hoc cleanup work without architectural anchoring.

---

## 1. The dispatch ladder, ordered

Each row is a single dev-claimable commit. Top of the ladder is "ready right now (post-Q4 approval)"; bottom is "wait for upstream."

| # | Refactor | Files (collision boundary) | Hard dependencies | Soft dependencies | Cost | Suggested commit prefix |
|---|---|---|---|---|---|---|
| **R1** | Hotspot #8 — drop `STEERING.md` docstring + delete file | `tinyassets/notes.py`, `packaging/.../runtime/tinyassets/notes.py`, `STEERING.md`, `INDEX.md` | None | None — already proven safe per `docs/exec-plans/active/2026-04-19-steering-md-removal.md` | ~30-45 min | `docs:` (2 atomic commits per Part A plan) |
| **R2** | Hotspot #3a — promote bid cluster to `tinyassets/bid/` package | `tinyassets/node_bid.py`, `tinyassets/bid_execution_log.py`, `tinyassets/bid_ledger.py`, `tinyassets/settlements.py` → `tinyassets/bid/{__init__.py, node_bid.py, execution_log.py, ledger.py, settlements.py}`. Plus 11 import call sites across `tinyassets/` (verified ~11 fan-in via grep at audit time). Plus packaging mirror. | Q4 approval | None — bid surface has zero overlap with rename, layer-3, Stage 2c, or engine/domain | ~0.5 dev-day | `refactor: promote bid surface to tinyassets/bid/ package` |
| **R3** | Hotspot #5 — investigate + resolve `compat.py` vs `_rename_compat.py` naming | `tinyassets/compat.py` (90 LOC, 2026-04-05) — read scope, then either merge to `tinyassets/compat/` package or rename for clarity | Q4 approval | Author→Daemon Phase 5 (R8 below) — easier post-Phase 5 because `_rename_compat.py` will be deleted then anyway. Recommend **defer until R8 lands** unless dev wants a quick-win between blocks | ~0.5 dev-day | `refactor: clarify compat.py vs _rename_compat.py naming` |
| **R4** | Layer-3 rename (host Q10-Q12) — universe→workflow server module + env vars + plugin dir | Per `docs/design-notes/2026-04-19-universe-to-workflow-server-rename.md` §6 task list | Q4 + Q10-Q12 approvals | Author→Daemon Phase 1 Part 2.5 (STATUS task #17) — both touch `_rename_compat.py` | ~3-4 dev-days (6 sub-tasks #26-#31) | per layer-3 design note §6 |
| **R5** | Hotspot #1 phase 1 — extract `universe_server.py` sub-dispatch tables to `tinyassets/api/` mounted submodules | `tinyassets/universe_server.py` (current 9,895 LOC) → split: `tinyassets/api/branches.py`, `tinyassets/api/runs.py`, `tinyassets/api/judgments.py`, `tinyassets/api/goals.py`, `tinyassets/api/wiki.py`, `tinyassets/api/extensions.py`, plus integration shell stays. ~23 import-fan-in into `workflow.universe_server` need updating. | Q4 + R4 (layer-3 rename complete — file is being renamed `workflow_server.py`) | None on the engine side; #11 engine/domain separation is a **soft prerequisite** but R5 is purely about file shape, not engine/domain semantics — they can land in either order | ~3-4 dev-days (split across 5-6 sub-commits, one per submodule) | `refactor: extract <area> from workflow_server to tinyassets/api/<area>.py` |
| **R6** | Hotspot #1 phase 2 — move fantasy-only actions out to `domains/fantasy_daemon/api/` per #11 design note | Per `docs/design-notes/2026-04-17-engine-domain-api-separation.md` §6 task list | Q4 + R5 + #11 host-asks resolved | Author→Daemon Phase 2-4 lands (so the daemon-side API is in its final shape before extracting domain-specific actions) | ~2 dev-days | per #11 design note |
| **R7** | Hotspot #2 — split `daemon_server.py` by storage context | `tinyassets/daemon_server.py` (3,575 LOC) → `tinyassets/storage/{accounts.py, universes_branches.py, requests_votes.py, notes_work_targets.py, goals_gates.py}`. Shared `_connect()` + migrations stay in `tinyassets/storage/__init__.py`. | Q4 + uptime/rename quieter (codex's recommendation; honored) | R5 (similar contributor headspace; bundle in same refactor wave) | ~2 dev-days | `refactor: split daemon_server by storage context` |
| **R8** | Author→Daemon Phase 5 — delete shims + flip flag | Per `docs/exec-plans/active/2026-04-19-author-to-daemon-rename-status.md` D2 | Phase 4 brand pass complete + one-release bake | None | ~0.5 dev-day | `rename Phase 5: delete compat shims + flip TINYASSETS_AUTHOR_RENAME_COMPAT default` |
| **R9** | Hotspot #4 — NodeScope dedup (`memory/node_scope.py` vs `memory/scoping.py`) | Pick canonical (likely `scoping.py`); migrate consumers; delete `node_scope.py`. Per memory `project_node_scope_dedup_post_2c.md`. | Stage 2c flag flip (STATUS task #19) — clock started 2026-04-16, fires after 30 days clean | None | ~0.5 dev-day | `memory: dedup NodeScope (scoping.py canonical, node_scope.py deleted)` |
| **R10** | Hotspot #6 — domain discovery via entry points | `tinyassets/discovery.py` rewrite to `importlib.metadata.entry_points(group="workflow.domains")`. Filesystem scan stays as dev-mode fallback. Pull rename-compat alias out of discovery. New `pyproject.toml` entry-point declaration. Pre-staging this needs the codex §4 ask #2 exec-plan that's still residual — see §3 below. | R8 (Phase 5 — so the alias-injection branch can disappear simultaneously) | None | ~1 dev-day | `discovery: switch to importlib.metadata entry-point group "workflow.domains"` |
| **R11** | Hotspot #3b — promote runtime cluster to `tinyassets/runtime/` package | `tinyassets/runs.py`, `tinyassets/work_targets.py`, `tinyassets/dispatcher.py`, `tinyassets/branch_tasks.py`, `tinyassets/branches.py`, `tinyassets/subscriptions.py` → `tinyassets/runtime/{...}`. Existing `producers/` + `executors/` move under `runtime/`. `runtime.py` becomes `runtime/__init__.py` or `runtime/core.py`. | Q4 + R5 (avoid alias-shim layering on top of in-flight god-module split) | None | ~1 dev-day | `refactor: promote runtime cluster to tinyassets/runtime/ package` |
| **R12** | Hotspot #3c — promote server shells to `tinyassets/servers/` package | `tinyassets/universe_server.py` (post-rename: `workflow_server.py`) → `tinyassets/servers/workflow.py`. `daemon_server.py` → `tinyassets/servers/daemon.py`. `mcp_server.py` → `tinyassets/servers/mcp.py`. `author_server.py` shim auto-disappears at R8. | R5 + R7 + R8 (servers are the integration shell — wait until their internal layout is final before re-pathing them) | None | ~0.5 dev-day | `refactor: promote server shells to tinyassets/servers/ package` |
| **R13** | Hotspot #7 — author_server shim cleanup (auto-resolves at R8) | None — auto-resolves | R8 | — | 0 | (no commit; deletion absorbed into R8) |

---

## 2. The first claimable commit, post-Q4 approval

**R1 (STEERING.md removal) and R2 (bid cluster promotion) are both first-claimable** the moment Q4 lands. They have no shared files and zero dependencies on anything else in flight. R1 is faster (~30-45 min); R2 is the first real architectural commitment to the new Module Layout (sets the precedent that future bid work goes into `tinyassets/bid/`).

**Recommendation:** ship R1 first as a low-risk warm-up that lets dev/verifier confirm the post-PLAN.md-approval workflow, then immediately R2 as the canonical first Module Layout commit.

---

## 3. The residual exec-plan from codex's §4 ask #2

Codex's modularity audit §4 recommended an exec-plan for entry-point-based domain discovery (R10 above). Currently absorbed as a Part B hotspot but lacks a per-step exec-plan with the entry-point group declaration, fallback semantics, and migration path for editable worktrees. Worth pre-staging as a small follow-up (~30 min) so R10 is dispatch-ready when R8 lands. Filed as a TODO under task #40; can land any time before R8 sequences.

---

## 4. Critical-path read

The dispatch ladder makes one thing visible that wasn't obvious before: **R5 (universe_server god-module split) is the real critical path** for the refactor. It blocks R6, R11, and R12; it depends on R4 (layer-3 rename) which itself depends on host Q10-Q12; and it's the single largest dev-day commitment (~3-4 days). If host approves Q4 alone but defers Q10-Q12, R5 can't begin and ~7 dev-days of downstream refactor work sits idle.

**Implication for host check-in:** Q4 + Q10 (module rename name) are the minimum subset that unblocks the refactor critical path. Q11 + Q12 (compat-flag scheme + plugin dir migration) are tactical and can pick defaults. Worth surfacing this nuance in the next host conversation: "answering Q4 alone unblocks R1+R2; answering Q4 + Q10 unblocks the path to R5."

---

## 5. Estimated total refactor dev-days (excluding gated/auto items)

| Block | Cost |
|---|---|
| R1 (STEERING) | 0.5 |
| R2 (bid cluster) | 0.5 |
| R4 (layer-3 rename, 6 sub-tasks) | 3-4 |
| R5 (universe_server split phase 1) | 3-4 |
| R6 (engine/domain phase 2) | 2 |
| R7 (daemon_server split) | 2 |
| R10 (entry-point discovery) | 1 |
| R11 (runtime cluster) | 1 |
| R12 (servers package) | 0.5 |
| **Total dispatchable** | **~13.5-15.5 dev-days** |

Add R3 (compat naming) = +0.5; R8 (Phase 5 finalization) = +0.5; R9 (NodeScope dedup) = +0.5 once Stage 2c fires.

**Realistic delivery window with 2 devs in parallel:** ~7-9 calendar days of refactor work, threaded between feature work that doesn't collide with the current refactor block. Sequencing per the ladder above keeps collision risk near zero.

---

## 6. What this doc does NOT decide

- **Which refactors get test-rewrites vs alias-only back-compat.** Each commit row decides at execution time based on the file's test-coverage picture. Default: ship with alias-shim back-compat (per `_rename_compat.py` precedent), retire shim one release later.
- **Whether R5/R6/R7 ship as one big PR or as N small commits.** Recommend the latter (sub-commit per submodule, per the parent rename plan's discipline). Final call by lead at dispatch time.
- **Which dev claims which row.** Lead's dispatch call. The dependency graph above doesn't encode "dev A vs dev B," only file-collision boundaries.

---

## 7. TL;DR for lead

- **R1 + R2 = post-Q4 first-up** (low-risk + first-canonical-commit).
- **R5 is the critical path** — needs Q4 + Q10 + R4 to unblock.
- **R7 + R10 + R11 + R12 are the heavy follow-ups** (~6.5 dev-days combined).
- **R9 is calendar-gated** (Stage 2c flag flip clock).
- **R3 + R8 + R13 auto-resolve or near-trivial** at their gate.
- Total dispatchable: ~13.5-15.5 dev-days, ~7-9 calendar-days with 2 devs.
