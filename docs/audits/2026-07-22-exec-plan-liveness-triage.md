---
title: Exec-plan liveness triage — all 38 files in docs/exec-plans/active/
date: 2026-07-22
author: claude-code (triage-exec-plans lane)
status: diagnostic record
scope: docs/exec-plans/active/, docs/exec-plans/completed/, docs/exec-plans/INDEX.md
---

# Exec-plan liveness triage

`docs/exec-plans/active/README.md` says *"Retire completed plans into `../completed/`."*
`active/` held **38 non-README files**; `completed/` held 27. This audit classifies all 38
against code and git history, and records the moves made.

**Verified 2026-07-22 against `origin/main` @ `144eaba7`.** Freshness note: `STATUS.md` moved
during this lane (the session-start snapshot was 4 commits behind). Every STATUS claim below was
re-read from `origin/main`, not from the stale snapshot.

## Headline: the brief's premise was half right, and the half it got wrong matters more

The dispatching brief sampled four April-dated plans, found their only commits were mechanical
rename sweeps, and concluded `active/` is 38 stale plans. Two corrections:

1. **The sample was unrepresentative.** Only 17 of 38 are the old April cohort. **17 were added
   on 2026-07-13** (`4fa897b7`, PR #1440) and are 9 days old. One more landed 2026-07-15, two on
   2026-07-21. Age is not the problem.
2. **"No substantive edit since April" is not evidence of neglect for the July cohort — it is
   *by design*.** Eight of the July files are cited by their matching `openspec/specs/*/spec.md`
   with the exact words:

   > `Historical source of record (untouched): docs/exec-plans/active/2026-07-09-boundary-layer-design.md`

   The spec and the plan landed in the **same commit**. PR #1440 deliberately kept the plan frozen
   as provenance for the spec. "Untouched" is the contract, not the rot.

So the real defect is **not** staleness. It is a **category error**: `active/` is being used as an
archive for historical design provenance, and as a filing cabinet for documents that were never
execution plans at all (9 self-describe as *"Binding design note"*; one is a probe report).

### The strongest single finding: a resurrected duplicate

`2026-04-27-arc-b-phase-3-dispatch-card.md` **exists in both directories.**

| | `completed/` copy | `active/` copy |
|---|---|---|
| Added by | `d16421b2` (2026-05-10) | `d4d279a0` (2026-07-21, PR #1490) |
| Frontmatter | `status: completed`, `completed_on: 2026-05-02`, 3 lines of `completion_evidence` | `status: dispatch-ready (gates on Arc B Phase 2 verifier SHIP)` |
| Pre-rename `workflow/`-era strings | **2** (prose only) | **37** |
| Lines | 316 | 301 |

The `active/` copy is the **older, pre-rename, pre-retirement** version. PR #1490 —
*"recover 32 documents that existed only in one stale checkout"* — resurrected a plan that had
been correctly retired 10 weeks earlier. It was the **only** exec-plan file that PR touched, so
the blast radius inside `docs/exec-plans/` is exactly this one file.

This is the known "stale-checkout recovery is a sweep bypass" class: the recovered file still
contains `workflow/`, `WORKFLOW_AUTHOR_RENAME_COMPAT`, and `workflow._rename_compat` — strings the
rename deleted from the repo. A recovery that reintroduces pre-rename text is restoring a
*checkout artifact*, not a *missing document*.

**Remedy: delete the `active/` copy.** Do not move it — `completed/` already holds the strictly
better version with completion evidence.

### Companion finding: the index is worse than the directory

`docs/exec-plans/INDEX.md` is the discovery surface, and it is broken in both directions:

- It lists **19** active entries; there are **39** files. **21 of 38 plans are missing** —
  including the entire July cohort and every paid-market track.
- It links `active/2026-04-30-live-community-reiteration-loop.md`, which **does not exist** on
  `origin/main`. It was deleted by `5fd09c9d` ("take down the retired cheat-loop CI writer
  cluster"). A reader following the index hits a dead link.

Fixing the directory without fixing the index would have shipped a regression — see
*Scope expansion* below.

## Classification — all 38

Evidence commands are given once per class. Conventions applied:
`docs/conventions.md` five lifecycle values, and its tie-breakers — *"False-shipped is worse than
false-active. When uncertain, classify `active`."*

### A. Deleted — resurrected duplicate (1)

| Plan | Evidence |
|---|---|
| `2026-04-27-arc-b-phase-3-dispatch-card.md` | Table above. `completed/` copy authoritative. |

### B. Moved to `completed/` — landing verified in code (6)

Each was verified against **current code**, not the plan's own prose.

| Plan | What the plan wanted | Verified state |
|---|---|---|
| `2026-04-19-entry-point-discovery.md` | Replace `discovery.py` filesystem scan with `importlib.metadata.entry_points` | **Landed.** `tinyassets/discovery.py:55` calls `importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)`. Its docstring calls the filesystem path *"the editable-dev-install fallback … the shape discovery had **before entry points landed**"*. The plan's R8 gate (alias injection at `discovery.py:65-66`) is satisfied — `_rename_compat` is deleted repo-wide. |
| `2026-04-19-rename-end-state.md` | Author→Daemon rename to end state, shims retired | **Landed.** `tinyassets/_rename_compat.py`, `domains/fantasy_author/`, `fantasy_author/` all absent (`git ls-files \| grep rename_compat` → empty). |
| `2026-06-27-tinyassets-hard-rename.md` | Rename repo + surfaces to TinyAssets | **Landed.** `git remote get-url origin` → `https://github.com/Jonnyton/TinyAssets.git`. |
| `2026-04-26-decomp-arc-c-prep.md` | Delete bare `UNIVERSE_SERVER_BASE` / `WIKI_PATH` env aliases | **Landed.** No bare-alias reader survives repo-wide: `grep -rn 'os.environ.get("WIKI_PATH"\|getenv("UNIVERSE_SERVER_BASE"' --include=*.py .` → empty; `grep -rn '\bUNIVERSE_SERVER_BASE\b' tinyassets/` → empty. Only `TINYASSETS_`-prefixed canonical forms remain. **Checked deliberately for the rename-vs-deletion confound**: this is deletion, not a prefix rename, because no reader for the bare form exists anywhere. Its STATUS row (`#24 Arc C`) has already been deleted from `origin/main`. |
| `2026-04-20-selfhost-uptime-migration.md` | Move MCP + tunnel origin off the host machine | **Landed.** `deploy/compose.yml` + `.github/workflows/deploy-prod.yml` exist; production runs on the DigitalOcean droplet via GHCR (`STATUS.md`, `AGENTS.md` Hard Rule 14). |
| `2026-07-02-universe-intelligence-relay-build.md` | M1 of the relay reshape | **Landed.** Added *by* `b91a6b07` = PR #1437, merged and deployed live 2026-07-15. |

### C. Genuinely active — left in place, stamped (3)

| Plan | Why it stays |
|---|---|
| `2026-07-18-distributed-execution-platform.md` | `openspec/changes/distributed-execution/tasks.md` has **9 unchecked tasks**; PRs **#1505 and #1493 are both OPEN** (classified by `gh pr view`, not by `rev-list` reachability); live handoff at `.agents/handoffs/2026-07-19-distributed-execution-resume/RESUME-SPEC.md`. |
| `2026-04-27-memory-scope-stage-2c-flip-prep.md` | STATUS.md on `origin/main` still carries `Memory-scope Stage 2c flag \| - \| 30d clean \| monitoring`. Conventions tie-breaker: STATUS cites it → `active`. |
| `2026-04-20-track-e-paid-market-wave-1.md` | Wave 1's core surface is **not** built: `request_inbox` appears in no `.py` file (docs/specs only). STATUS carries an in-flight Wave 2 row (`claimed:codex-gpt5-desktop`). |

### D. Historical provenance — MUST NOT MOVE (8)

Each is named by its openspec spec as *"Historical source of record (untouched)"*. Correct
lifecycle value is `historical`, **but moving them breaks the citing spec**, and
`openspec/specs/` is outside this lane's write-set.

| Plan | Citing spec |
|---|---|
| `2026-07-08-token-architecture.md` | `openspec/specs/token-architecture/spec.md:13` |
| `2026-07-08-track-e-price-index-and-capacity-forwards.md` | `paid-market-price-index-and-forwards/spec.md:13` |
| `2026-07-08-track-f-training-market.md` | `paid-market-training/spec.md:13` |
| `2026-07-08-track-g-data-commons.md` | `data-commons/spec.md:11` |
| `2026-07-08-track-h-pooled-training-ownership.md` | `pooled-training-ownership/spec.md:12` |
| `2026-07-08-track-i-hardware-creation.md` | `hardware-creation/spec.md:13` |
| `2026-07-09-boundary-layer-design.md` | `boundary-layer/spec.md:12` |
| `2026-07-09-demand-side-design.md` | `demand-side/spec.md:12` |

**Follow-up lane required:** move these 8 to `completed/` (or a new `historical/`) **and** update
the 8 spec citations **in one commit**. Splitting the two halves leaves dangling references.

### E. Misfiled category — design notes and a probe report, not execution plans (9)

All 9 are referenced by `docs/PAID-MARKET-START-HERE-2026-07-08.md` (outside write-set) except
`self-marketing-archetype`, which has zero inbound references.

`2026-07-09-brain-crawl-format.md`, `-commons-architecture.md`, `-cross-venue-routing.md`,
`-discovery-flows.md`, `-founder-universe-archetype.md`, `-market-data-layer.md`,
`-market-open-dynamics.md`, `-self-marketing-archetype.md` — each self-describes as
**"Binding design note"**. `2026-07-08-production-mcp-sweep.md` is a **probe report** (read-only
production probes), not a plan at all.

These belong under `docs/design-notes/` and `docs/audits/` respectively. Same
move-breaks-citation constraint as class D. Left in place; **not** stamped `active`, because
that would assert a liveness claim this audit does not support.

### F. Unverifiable from the repo — left in place (11)

Honest bucket. For each, the evidence that would settle it is named.

| Plan | Why unverifiable | What would settle it |
|---|---|---|
| `2026-04-09-runtime-fiction-memory-graph.md` | Partially built — `tinyassets/packets.py` exists, but the plan is a multi-month ladder (temporal/promise/epistemic ledgers, narrative debt) with no per-step landing record. | A per-ledger checklist against `tinyassets/packets.py` + `domains/fantasy_daemon/`. |
| `2026-04-27-runtime-fiction-memory-graph-restart-cards.md` | Same ladder, restart-card form. | Same. |
| `2026-04-25-file-bug-wiring.md` | Its headline premise is **contradicted** — it says the forward call site is UNWIRED, but `tinyassets/api/wiki.py:2207` calls `bug_investigation._maybe_enqueue_investigation(`. Triggers 2 (startup-backfill) and 3 (safety-net) are unconfirmed, and the cheat-loop CI retirement (2026-06-25) may have removed their reason to exist. | Confirm whether triggers 2/3 are in scope post-retirement. |
| `2026-04-27-post-18-recency-continue-implementation-cards.md` | Code **is** landed (`extensions.py:288` `resume_from` param, `runs.py:591` reader, documented in `prompts.py:330`); plan says "live MCP verification remains". Its STATUS row is already deleted from `origin/main`. | A live `ui-test` receipt for `run_branch resume_from=`. |
| `2026-04-19-sporemarch-c16-s3-diagnostic-plan.md` | Explicitly conditional: *"dispatch-ready when Sporemarch resumes post-Fix-E migration."* The trigger never fired. | Whether Sporemarch is ever resumed. |
| `2026-04-27-hyperparameter-importance-implementation-cards.md` | Explicitly conditional: *"ready when science-domain lane opens."* Lane never opened. | Whether the science domain is on the roadmap. |
| `2026-04-19-daemon-economy-first-draft.md` | Scoping doc; substantively overtaken by Tracks E–I and `openspec/specs/paid-market-economy/`, but no doc declares the supersession. | Host confirmation that Tracks E–I supersede it. |
| `2026-04-26-engine-domain-coupling-inventory.md` | Self-declared *"read-only inventory"* — an input to a host-review queue, not a plan with a done state. | Whether Task #11/#28/#29 were decided. |
| `2026-04-27-step-11plus-retarget-sweep-roi.md` | Self-declared *"read-only ROI analysis — host decision pending."* Conventions tie-breaker keeps a host-decision-pending doc `active`. | The host's scope decision. |
| `2026-04-27-autonomous-backlog-queue.md` | A Codex working-process doc, not a deliverable plan. | Whether the process is still run. |
| `2026-05-01-host-discoverability-and-onboarding-rollout.md` | Seed plan; STATUS carries related but not identical `host-action` rows (external directory acceptance, ChatGPT connector re-registration). | Mapping each seed item to its STATUS row. |

## Scope expansion — declared, not silent

The brief's write-set was `docs/exec-plans/active/*`, `docs/exec-plans/completed/*`, and this
audit. **`docs/exec-plans/INDEX.md` was added.** Reason: it is the index *of* the two directories
in the write-set, and moving files without updating it converts 7 correct links into dead ones.
It was already broken (21 missing, 1 phantom), so leaving it untouched would have compounded the
defect this lane exists to fix. No open PR touches `docs/exec-plans/` (verified by sweeping all
open PRs' file lists), so the file is uncontended.

`STATUS.md` and `AGENTS.md` were **not** edited, per the scope guard.

## Proposed STATUS.md edit — for a human to land

No edit is required. The Work rows that mapped to these plans (`#24 Arc C`, `run_branch
resume_from`, the Arc B phases) have **already been deleted** from `origin/main`. The one
surviving row is correct as-is and should stay:

```
| Memory-scope Stage 2c flag | - | 30d clean | monitoring |
```

## What this lane did not reach

- The 8 class-D and 9 class-E files were **not** moved. They need a companion write-set
  (`openspec/specs/`, `docs/PAID-MARKET-START-HERE-2026-07-08.md`) to move without breaking
  citations. Named as a follow-up lane above.
- The 11 class-F files were **not** resolved, only bounded. Each names its settling evidence.
- Plan bodies were not edited, per the brief. The only content change is a supersession header
  on moved files.

Net: `active/` goes from 38 → 31. The residual 31 is now *classified* rather than *assumed*.
