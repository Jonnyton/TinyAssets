---
title: STATUS.md Concerns — 4-day staleness pass (per coordination-gap §5 Rule 1)
date: 2026-04-28
author: dev-2
status: read-only audit — lead reviews + applies; do not auto-edit STATUS.md per `feedback_status_md_host_managed`
companion:
  - docs/audits/2026-04-28-status-md-coordination-gap.md (the rule this pass implements)
  - feedback_status_md_host_managed (memory — host curates Concerns, no auto-trim)
  - feedback_audits_can_be_already_done (memory — verify before classify)
load-bearing-question: After applying the proposed 4-day staleness rule, which Concern rows still belong on STATUS.md and which should be retired/reframed?
audience: lead, host
---

# STATUS.md Concerns staleness pass — 2026-04-28

## Methodology

Today: 2026-04-28. Threshold: any Concern with newest date-stamp ≤2026-04-24 is staleness candidate; checked against git log + design-note frontmatter + audit cross-refs + STATUS Work table.

13 Concern rows reviewed. Date-stamp definition: a row dated `[YYYY-MM-DD]` was filed/updated that day; `[YYYY-MM-DD→YYYY-MM-DD]` shows last-verified date as the second value (the AGENTS.md "verified" convention).

Verdicts use the rubric from §5 Rule 1: **KEEP-AS-IS** / **REFRAME** / **RETIRE** / **NEEDS-HOST-VERIFY**.

## Per-row verdict table

| # | Date-stamp | Concern (truncated) | Newest date age | Verdict | Reason |
|---|---|---|---|---|---|
| 1 | `[2026-04-23]` | P0 revert-loop: daemon PAUSED. Auto-recovery outran pruner. | 5 days | **KEEP-AS-IS** | Trace doc `docs/audits/2026-04-23-p0-auto-recovery-trace.md` exists; no resolution commit found via grep. Daemon-state-pause is host-observable, not session-resolvable. |
| 2 | `[2026-04-20]` | Canonical public MCP: tinyassets.io/mcp -> 200; mcp.tinyassets.io/mcp -> gated. | 8 days | **KEEP-AS-IS** | Architectural truth (canonical apex vs internal tunnel origin); not time-decaying. Mirrors hard-rule #11 in AGENTS.md. Could move to PLAN.md instead of STATUS Concerns — recommend lead consider migration, but content stays accurate. |
| 3 | `[2026-04-22→25]` | `/etc/tinyassets/env` mode flip — Fix A landed (bc079a0); awaits host review. | 3 days verified | **KEEP-AS-IS** | Fresh (within 4-day threshold). Fix landed; host review pending. Verified-stamp working as intended. |
| 4 | `[2026-04-20→27]` | `test_node_eval::test_record_and_get_stats_roundtrip` flake — Fix B landed (16d4823); watching ≥30d. | 1 day verified | **KEEP-AS-IS** | Fresh. 16d4823 confirmed in git log. ≥30d watch still active. |
| 5 | `[2026-04-26]` | Methods-prose evaluator REFRAMED community-build; design-note header needs reframe. | 2 days | **REFRAME** | Recommended action ("design-note header needs reframe") never landed. Note `docs/design-notes/2026-04-27-methods-prose-evaluator.md` still has `status: superseded` + `status_detail: proposal — awaiting lead approval` — stale, doesn't mention community-build reframe. The Concern itself is correct (header needs reframe); recommend (a) file as a one-line dev-2 task to apply the reframe, (b) retire the Concern when applied. **Action item:** dev-2 (or whoever has time) edits the note's frontmatter status_detail + first paragraph to match host's community-build directive. |
| 6 | `[2026-04-17]` | Privacy mode note has 3 host Qs: `2026-04-18-privacy-modes-for-sensitive-workflows.md`. | 11 days | **REFRAME** to NEEDS-HOST-DECISION | Note still has `status: active` (verified 2026-04-28). 3 host asks unanswered. Lead memory entry `project_privacy_via_community_composition` (2026-04-26) says privacy is community-build, not platform — which may obviate or reshape the host Qs entirely. **Recommend:** lead/navigator review whether the community-build directive resolves the privacy Qs; if so, retire row + retire the design note. If not, reframe row with current state. |
| 7 | `[2026-04-18]` | `add_canon_from_path` sensitivity note has 3 host asks. | 10 days | **NEEDS-HOST-VERIFY** | Note still has `status: active`. Host Qs about sensitivity classification — host-only knowledge (what counts as sensitive in user's threat model). Same caveat as row 6: community-build principle may apply (`feedback_privacy_via_community_composition`). |
| 8 | `[2026-04-18]` | Claude.ai injection mitigation blocked on host-Q batch. | 10 days | **NEEDS-HOST-VERIFY** | Note still has `status: research` (verified 2026-04-28). Genuine host-Q-batch dependency; not session-resolvable. |
| 9 | `[2026-04-18]` | Full-platform architecture supersedes phased plan; migrate candidate. | 10 days | **REFRAME** | Note has `status: active`. Work table row "PLAN.md retirement of phased plan" exists at L47. The Concern is the same intent as the Work row — duplicate. **Recommend:** retire Concern; the Work row tracks. Lead may also want to review whether nav SWEEP 2 finding has landed since (per Work row L47 dependency). |
| 10 | `[2026-04-19]` | Navigator follow-up: modularity audit flags `universe_server`, discovery, `daemon_server` seams. | 9 days | **REFRAME or RETIRE** | universe_server seam: closing now via Task #18 (in flight). daemon_server seam: closed via R7 storage split (per `tinyassets/storage/` package — committed). discovery seam: still open (covered by exec-plan `2026-04-19-entry-point-discovery.md` `status: active`, gated on R8 Phase 5). **Recommend:** RETIRE this row; the 3 sub-issues are tracked elsewhere (Work table #18 + R7 closed + active exec-plan). |
| 11 | `[2026-04-24]` | Task #9 host Qs: are GROQ/GEMINI/XAI in GH Actions secrets? Host validates rotation e2e after deploy step ships. | 4 days | **NEEDS-HOST-VERIFY** | Right at staleness threshold. Grep of `.github/workflows/*.yml` + `deploy/` finds zero references to these key names; can't confirm GH Settings from local repo. Host action required. Deploy step landing not surfaced via grep — also unclear. |
| 12 | `[P1 filed:2026-04-25 verified:2026-04-28]` | BUG-034 ChatGPT connector approval. Status comment landed during 2026-04-28 drain. Rows 19/20/21 retired. | 0 days verified | **KEEP-AS-IS** | Already had the per-coordination-gap §3 surgery applied (rows 19/20/21 retired in-place, this row reframed with verified date). The fix landed; ongoing two-track state (platform mitigation + OpenAI escalation) tracked. |
| 13 | `[2026-04-26]` | NEW PRINCIPLES in lead memory (foundational): minimal-primitives + community-build + privacy-via-community-composition. | 2 days | **REFRAME** | Memory references are correct (verified — 3 .md files exist in lead memory). Doesn't read like a "concern" though — it's a heads-up that 3 new principles are now governing scoping decisions. **Recommend:** demote from Concerns to a new "Foundational Principles" section near top of STATUS.md, OR move to PLAN.md cross-cutting principles section. Concerns is for things needing action; principles are constants. Either works; lead picks. |
| 14 | `[2026-04-26→28]` | `.codex/skills/` deleted 2026-04-28 (was declared dead 2026-04-16; gitignored). | 0 days | **RETIRE** | Action complete (executed by dev-2 earlier 2026-04-28 with lead approval). Resolution stamp `→28` indicates done. **Recommend:** delete row outright per AGENTS.md "Don't mark concerns DONE — delete them." |
| 15 | `[2026-04-28]` | F2 ACCEPTED: drop Recency, fold continue_branch into `run_branch resume_from`. | 0 days | **REFRAME** | Decision is recorded; the corresponding Work row L44 already captures it as dev-ready. Concern + Work duplicate. **Recommend:** retire Concern; Work row tracks. |
| 16 | `[2026-04-28]` | Commons-first audit landed: 5 findings. F1 UNGATED. | 0 days | **KEEP-AS-IS short-term** | Recent (today). Will become stale over time but currently captures live audit state. Recommend re-verify next session. |
| 17 | `[2026-04-28]` | Internal-scoping items moved off host queue per `feedback_dont_ask_host_internal_scoping`. | 0 days | **REFRAME** | Process-change announcement, not a concern. Belongs in AGENTS.md or a session changelog, not Concerns. **Recommend:** move text to `.agents/activity.log` 2026-04-28 entry, retire row. |

## Summary

| Verdict | Count | Rows |
|---|---|---|
| KEEP-AS-IS | 6 | 1, 2, 3, 4, 12, 16 |
| REFRAME | 6 | 5, 6, 9, 10, 13, 15, 17 (note: 7 actual; 6 distinct because row 6 is REFRAME → NEEDS-HOST-DECISION subtype) |
| NEEDS-HOST-VERIFY | 3 | 7, 8, 11 |
| RETIRE | 1 | 14 |

(Counts add to 16 because row 6 has dual classification; total rows reviewed = 17.)

## Net STATUS.md effect (if all recommendations applied)

- **Delete: 1 row** (#14: `.codex/skills/` deletion done — pure resolution-stamp).
- **Reframe + relocate: 5 rows** (#9 PLAN.md retire → already in Work table; #10 modularity audit → 3 sub-issues tracked elsewhere; #13 new principles → move to PLAN.md or a Principles section; #15 F2 → already in Work table; #17 internal-scoping process-change → activity.log).
- **Reframe in place: 2 rows** (#5 methods-prose reframe action item; #6 privacy-mode under community-build review).
- **Keep verbatim: 6 rows** (#1, #2, #3, #4, #12, #16).
- **Wait for host: 3 rows** (#7, #8, #11).

Net Concerns size after edit: 17 → 11 rows (35% reduction).

## Lateral observations (not action items)

1. **Row 6 + 7 + 8 share a pattern:** all 3 are "design-note has N host Qs" with dates 2026-04-17/18 (10-11 days old). All 3 may be partially obviated by the 2026-04-26 community-build principle. Worth a single navigator pass to triage them as a batch ("does community-build resolve / reshape / leave-untouched these?").

2. **Row 13 calls out 3 NEW PRINCIPLES.** Suggests STATUS.md needs a `## Principles` section between Concerns and Approved Specs, OR these need to land in PLAN.md proper. Currently they're announced in Concerns but live in lead's per-agent memory only. Codifying them once in shared truth (PLAN.md) makes the Concern row redundant.

3. **The §5 Rule 2 (test-session tagging) and Rule 3 (Concern↔BUG cross-reference) didn't trigger** during this audit because the only test-session-derived concerns have already been retired (rows 19/20/21 from the coordination gap audit). Future test-session concern entries should follow Rule 2 from the start.

## Verifier handoff

This is a recommendation document, not an applied edit. Per `feedback_status_md_host_managed`, lead reviews the table and applies edits to STATUS.md.

No code touched. No test files touched. No dev #18 lock-set touched.
