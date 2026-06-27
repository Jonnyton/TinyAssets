---
title: Internal-scoping Threads A/B/C — Phase 6 + fantasy_author_original deletion + R7 closure
date: 2026-04-28
author: navigator
status: closure analysis; refreshed 2026-05-01 after Thread B cleanup landed in 98abd3a
companion:
  - feedback_dont_ask_host_internal_scoping (lead memory) — these 3 threads were the first batch run under the new autonomy rule
  - feedback_status_md_evidence_based_retire (lead memory) — this audit IS the evidence citation for the retire/reframe
  - feedback_obviated_item_check_against_completion_plans (navigator memory) — the methodology used in Thread C
  - feedback_check_dependents_before_retiring_status_rows (navigator memory) — caught the dev-2 exec-plan-INDEX anchor in Thread C
load-bearing-question: For each of the 3 internal-scoping threads kicked back from the host queue 2026-04-28, what is the autonomous decision + the supporting evidence, and what STATUS-surface change does it produce?
audience: lead, host (review only — not a host-decision queue item)
---

# Internal-scoping Threads A/B/C — closure analysis

## TL;DR

Host kicked 3 of 6 items back from the 2026-04-28 decision batch as navigator+lead autonomous (per the new `feedback_dont_ask_host_internal_scoping` rule). All three decided + applied to STATUS this turn. Net result: 6 host-asks dispatched, 1 STATUS row retired, 1 reframed, 2 dev-tasks queued for post-#18.

**2026-05-01 refresh:** Thread B is now complete. Current repo evidence shows
`fantasy_author_original/` is absent, and commit `98abd3a` removed the stale
`pyproject.toml` Ruff `extend-exclude` entry. Do not re-queue
`fantasy_author_original/` deletion from this audit.

| Thread | Subject | Decision | STATUS impact |
|---|---|---|---|
| **A** | Phase 6 `.author_server.db` rename, 6 sub-decisions | All 6 decided per §1 below | Work row reworded with decisions; TaskList #25 filed |
| **B** | `fantasy_author_original/` deletion timing | COMPLETED 2026-05-01 | Closed by `98abd3a`; no remaining STATUS row |
| **C** | R7 storage-split state | ACTIVE-with-OBVIATED-items; dependents must be preserved | Row reframed (not retired); dev-2 exec-plan-INDEX anchor preserved |

---

## 1. Thread A — Phase 6 `.author_server.db` → `.workflow.db` rename, 6 decisions

**Source design note:** `docs/design-notes/2026-04-27-author-server-db-filename-migration.md` §8.

### Decision matrix

| # | Sub-question | Decision | Reasoning |
|---|---|---|---|
| 1 | Filename: `.workflow.db` vs `.daemon.db` vs other | **`.workflow.db`** | Matches project name + canonical brand voice (`project_daemon_product_voice`). The daemon is the agent identity, not the storage shape. |
| 2 | Function name: `workflow_db_path()` vs `db_path()` | **`db_path()`** | Storage package owns one DB; `workflow_` qualifier is redundant. |
| 3 | Migration option (A/B/C/D) | **Option A** — atomic-rename + boot-time discovery + one-shot self-deleting migrator | Only path consistent with `feedback_no_shims_ever`. B is dual-read shim; C is permanent alias artifact; D defers indefinitely. |
| 4 | Scope | Per design-note §3 Option A — ~30 LOC code + ~5 unit tests + plugin mirror sync | Effort scoped at ~2-3h dev. |
| 5 | Restart window | **30s scheduled** | Single-host MVP; restart is routine for production-current scale (1-10 universes per `output/` survey 2026-04-26). |
| 6 | Plugin minor-version bump | **YES** | Standard semver discipline; old plugins reading legacy filename get clean rejection rather than silent fresh-universe behavior. |

### Sequencing

Phase 6 of rename arc, AFTER Arc B + Arc C land (per design-note §5). Effort: ~2-3h dev + 1h host. Risk: LOW (rollback path well-understood per design-note §4).

### TaskList action

Task #25 filed with full description capturing all 6 decisions. blockedBy #1 (plugin-mirror collision per `project_plugin_mirror_collision_with_dev_lockset`); also gated on Arc B + Arc C per sequencing.

### STATUS Work row replacement (already applied by lead)

Old: `Phase 6 .author_server.db → .workflow.db migration | per design note 2026-04-27; 6 host asks: ... | Arc C | host-decision`

New: `**Phase 6 DECIDED 2026-04-28** (nav): \`.workflow.db\` filename, \`db_path()\` fn, Option A migration, 30s restart, plugin minor-bump. ~2-3h dev + 1h host. | tinyassets/storage/__init__.py + plugin mirror + tests | Arc C | dev-ready (post-Arc-C)`

---

## 2. Thread B — `fantasy_author_original/` deletion: COMPLETED 2026-05-01

### Evidence

| Check | Result |
|---|---|
| Directory contents | 36 KB, 1 file: `work_targets.py.truncated` |
| File contents | Pre-rename snapshot of original `work_targets.py`. First lines: `"""Work target and review persistence helpers. The daemon's universe-level scheduling..."""` + `from fantasy_author import author_server`. Useless reference material; git history preserves it. |
| Live imports of `fantasy_author_original` | **ZERO** in canonical tree (`grep -r` returns only audit-doc + exec-plan refs) |
| Original Phase 1 plan §9-B | Host-confirmed DELETE 2026-04-15; never executed |
| `pyproject.toml:98` | Historical: `extend-exclude = ["fantasy_author_original"]` also required removal in same commit. Current: removed by `98abd3a`. |

### Decision

COMPLETED. No dependency on Arc B Phase 3 / Phase 6 remained. Current
verification from 2026-05-01: `Test-Path fantasy_author_original` is false,
`git ls-files fantasy_author_original` returns zero files, `pyproject.toml`
has no `fantasy_author_original` / `extend-exclude` hit, TOML parse passes, and
`python -m ruff check pyproject.toml` passes. Full `python -m ruff check`
still reports unrelated pre-existing issues in `scripts/site_apex_cutover.py`
and test files; those are outside this cleanup and tests are #18-owned.

### TaskList action

Historical: Task #27 filed. Current: closed by `98abd3a`; no follow-up work
remains for `fantasy_author_original/` itself.

---

## 3. Thread C — R7 storage-split state: ACTIVE-with-OBVIATED-items, REFRAMED (not retired)

### Methodology: OBVIATED-item check (per `feedback_obviated_item_check_against_completion_plans`)

Path A end-state spec (`docs/exec-plans/active/2026-04-19-rename-end-state.md`) lists 8 atomic items. Atomized + greped each load-bearing keyword:

| # | Path A item | Keyword | Result | Status |
|---|---|---|---|---|
| 1 | Identifier renames Author→Daemon | `_rename_compat.py` (188 LOC) + 3 alias modules | exists | partial — Arc B Phase 3 deletes |
| 2 | Test fixtures updated | `from domains.fantasy_author` in tests/ | ~50 sites | partial — Arc B Phase 2 |
| 3 | Compat aliases removed | `_rename_compat.py` | exists | pending Arc B Phase 3 |
| 4 | `_rename_compat.py` + alias modules deleted | path exists | exists | pending Arc B Phase 3 |
| 5 | `TINYASSETS_AUTHOR_RENAME_COMPAT` flag removed | flag-name grep | extant | pending Arc B Phase 3 |
| 6 | DB schema rename `author_definitions` → `daemon_definitions` | `author_definitions` in tinyassets/storage/ | **0 matches** | **OBVIATED** |
| 7 | ID-prefix backfill `"author::"` → `"daemon::"` | `"author::"` in tinyassets/ | **0 matches** | **OBVIATED** |
| 8 | Brand-pass copy | `Universe Server` in canonical user-facing | partial | partial — skill scrub LANDED 6ce641f, doc rewrite #14 LANDED, Phase 6 = data-layer brand-pass |

### Risk-register satisfaction (Path A §risk-register)

Path A's required pre-flight gates ("post-sweep grep MUST return zero results"):
- `monkeypatch.setattr("workflow.author_server`: 0 matches in tests/
- `monkeypatch.setattr("fantasy_author`: 0 matches in tests/

Both gates already SATISFIED today.

### Verdict

ACTIVE-with-OBVIATED-items. Items 6 + 7 are OBVIATED (zero grep matches; either retired silently in pre-decomp era or never shipped under that name). Remaining 6 items are ALL covered by other in-flight Work-table rows (Arcs B/C/Phase 6).

### Why REFRAME (not retire) — dependents check

Per `feedback_check_dependents_before_retiring_status_rows`: ran `grep -rEn "rename-end-state" docs/ .claude/agent-memory/`. Found dev-2's memory `.claude/agent-memory/dev-2/feedback_status_cites_means_active.md:14`:

> "lead validated the call: 'keeping rename-end-state.md in ACTIVE because STATUS still cites it as host-decision-pending is exactly right.'"

Retiring the STATUS row would orphan dev-2's exec-plan-INDEX classification anchor. Cleaner action: REFRAME the row from `host-decision` to `nav-then-dev (closure pass)`, paired with `dev-2 moves the exec-plan to landed/ when Phase 6 ships`. Same coordination value, no orphans.

### STATUS Work row replacement

Old (deleted in lead's prior pass): `R7 storage-split status confirmation | exec-plan: docs/exec-plans/active/2026-04-19-rename-end-state.md | host | host-decision`

New (this audit applies): `R7 closure pass — Path A items 6+7 OBVIATED 2026-04-28 (nav Thread C, this audit §3); items 1-5 covered by #23/#24; item 8 covered by #25. Exec-plan moves to landed/ when #25 (Phase 6) ships. | exec-plan: docs/exec-plans/active/2026-04-19-rename-end-state.md | #25 | nav-then-dev |`

---

## 4. Decision asks

NONE — this audit is closure documentation, not a host-decision queue item. Per `feedback_dont_ask_host_internal_scoping`, all three decisions are navigator+lead autonomous. The audit exists to satisfy `feedback_status_md_evidence_based_retire`'s "audit-doc citation mandatory" clause for the STATUS Work-row reframes.

If host wants to rubber-stamp a posteriori, that's welcome but not required.

---

## 5. Cross-references

- `docs/design-notes/2026-04-27-author-server-db-filename-migration.md` — Thread A source
- `docs/exec-plans/active/2026-04-19-rename-end-state.md` — Thread C source
- `docs/exec-plans/completed/2026-04-15-author-to-daemon-rename.md` §9-B — Thread B host-confirmation history
- `docs/audits/2026-04-26-architecture-edges-sweep.md` §A.3 — Thread B sibling audit
- `feedback_dont_ask_host_internal_scoping.md` (lead) — the rule that produced these threads
- `feedback_status_md_evidence_based_retire.md` (lead) — the rule this audit satisfies
- `feedback_obviated_item_check_against_completion_plans.md` (navigator) — the methodology Thread C used
- `feedback_check_dependents_before_retiring_status_rows.md` (navigator) — the rule that caught the dev-2 anchor in Thread C
- `.claude/agent-memory/dev-2/feedback_status_cites_means_active.md` — dev-2's mirror rule for exec-plan classification
