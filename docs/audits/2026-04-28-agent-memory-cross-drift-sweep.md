---
title: Agent-memory cross-drift sweep — contradictions, gaps, duplicates, stale refs
date: 2026-04-28
author: dev-2
status: original read-only audit; refreshed 2026-05-01T17:17-07:00 against current Claude team memory
companion:
  - feedback_audits_can_be_already_done (memory) — verify before scoping
  - feedback_status_cites_means_active (memory) — consumption pattern trumps internal status
load-bearing-question: Where does agent memory contradict, miss-mirror, drift stale, duplicate within-agent, or fail to cover important multi-agent rules?
audience: lead, host (selectively)
---

# Agent-memory cross-drift sweep

## TL;DR

Original 2026-04-28 sweep found 5 lead-reviewable findings across 12 agent dirs
(~250 memory files total). Current 2026-05-01 refresh found that the three
actionable team-memory gaps are already closed:

- Finding #1 is closed: verifier no longer has `feedback_stash_diagnostic.md`,
  and `verifier/feedback_isolate_preexisting_failures.md` now says stash is
  destructive and must not be used for diagnostics.
- Finding #3 is closed: dev-2 now has `feedback_no_destructive_git.md` and
  indexes it in `dev-2/MEMORY.md`.
- Finding #4 is closed: navigator now has
  `feedback_send_message_required_for_team_chat.md` and indexes it in
  `navigator/MEMORY.md`.

Finding #2 remains lead-environment-only. Finding #5 remains informational:
the audit-staleness rule is duplicated by role, but the role-specific examples
are useful.

## Per-agent file count

| Agent dir | MEMORY.md | Files (excl. index) | Notes |
|---|---|---|---|
| Lead (`~/.claude/projects/.../memory/`) | yes | 109 (one warns >24KB load-truncated) | Source of truth for cross-cutting principles |
| `developer/` | yes | 38 | Largest of the team-agent dirs; deep code/test patterns |
| `navigator/` | yes | 27 | Strategic + freshness-check patterns |
| `verifier/` | yes | 12 | Test-suite + commit-discipline patterns |
| `planner/` | yes | 9 | Older project artifacts; minimal feedback |
| `dev-2/` | yes | 10 | Floater; this session added 3 new memories |
| `critic/` | yes | 3 | Story/eval-only |
| `reviewer/` | yes | 1 | Single review-patterns doc |
| `tester/` | yes | 1 | pycache-after-rename only |
| `user/` | yes | 3 + personas/ | User-sim patterns |
| `explorer/` | no | 2 | Story context only; no MEMORY.md index |
| `debugger/` | no | 0 | Empty |
| `story-author/` | no | 0 | Empty |

## Findings

| # | Severity | Title | Affected agents | Recommended action | Current disposition |
|---|---|---|---|---|---|
| 1 | **DRIFT (contradiction)** | Original finding: verifier allowed diagnostic stash while dev/navigator/lead forbade it | verifier vs dev + navigator + lead + dev-2 | Original recommendation: retire verifier's `feedback_stash_diagnostic.md` or carve an exception clause into the no-stash rules. Preferred fix was to retire verifier's exception and use `git show HEAD:path` or `git diff HEAD` instead. | **Closed 2026-05-01.** `verifier/feedback_stash_diagnostic.md` is absent; `verifier/feedback_isolate_preexisting_failures.md` says not to stash. |
| 2 | **LEAD-ENV ONLY** | Lead MEMORY.md cites "Universe Server" in 2 index entries (L28, L35) | Lead | The referenced Lead `MEMORY.md` is not present in this checkout as of 2026-04-28 (`.claude/**/MEMORY.md` has no matches). If that memory exists in the lead runtime environment, replace "MCP Universe Server" / "Restart daemon/Universe Server" with "TinyAssets MCP server" / "the daemon"; no repo-local edit remains. | **Still lead-env only.** No side-worktree edit available. |
| 3 | **MISSING-MIRROR** | Original finding: dev-2 had no destructive-git rule | dev-2 | Original recommendation: add the same no-destructive-git rule carried by dev, navigator, and lead to dev-2 memory. | **Closed 2026-05-01.** `dev-2/feedback_no_destructive_git.md` exists and is indexed. |
| 4 | **MISSING-MIRROR** | Original finding: SendMessage rule was missing from navigator memory | navigator | Original recommendation: add the teammate-channel rule already carried by dev and verifier to navigator memory. | **Closed 2026-05-01.** `navigator/feedback_send_message_required_for_team_chat.md` exists and is indexed. |
| 5 | **DUPLICATE / NEAR-DUPLICATE (4 copies of audit-staleness rule)** | Audit-staleness pattern lives in 4 agent memories with different framings | dev (`feedback_audits_often_stale.md`), navigator (`feedback_audit_freshness_check.md`), lead (`feedback_audit_freshness_check.md`), dev-2 (`feedback_audits_can_be_already_done.md`) | Same load-bearing rule across 4 files, 4 framings, 4 examples. Could be: (a) accepted as fine — different agents need different framings of the same rule. (b) consolidated to one canonical file in lead memory with cross-refs. **My take:** keep as-is. Each memory captures the example most relevant to that role (dev hit it on extractions, navigator on prescriptions, dev-2 on classify-from-scratch tasks, lead on dispatch). Consolidating would lose the role-specific examples. Just flag for awareness. | **No action.** Keep role-specific examples. |

## Other observations (informational, not action items)

### A. Lead MEMORY.md is overflowing the load budget

L1 of lead's MEMORY.md shows: `> WARNING: MEMORY.md is 24.5KB (limit: 24.4KB) — index entries are too long. Only part of it was loaded. Keep index entries to one line under ~200 chars.`

This means lead memory is being truncated at load time. ~109 files indexed in 1 file at the budget edge. Recommend lead trim entries to ~150 chars or split across themed indexes (e.g. `MEMORY-process.md`, `MEMORY-product.md`).

### B. Coverage map of important rules across agents

Sampled 6 cross-cutting rules:

| Rule | Lead | Dev | Dev-2 | Nav | Verifier | Notes |
|---|---|---|---|---|---|---|
| Run `build_plugin.py` after canonical edits | (project_plugin_mirror_collision via nav) | yes | no | yes | no | dev-2 + verifier could use it |
| Audit freshness / spot-check before classify | yes | yes | yes | yes | no | verifier could use it; dev-2 + nav + lead converge here |
| Daemon default behavior (1 always-on, normal state) | yes | no | no | yes | no | dev/dev-2 don't need it (orthogonal to code work); lead+nav have product axis covered |
| `git stash` is destructive — don't use for diagnostics | yes | yes | yes | yes | yes | 2026-05-01 refresh: gaps from findings #1 + #3 are closed. |
| SendMessage required for teammate-channel reply | (implicit) | yes | (implicit; not flagged) | yes | yes | 2026-05-01 refresh: finding #4 is closed. |
| Commit only on verifier SHIP | yes | yes | (implicit) | yes | yes | well-mirrored |

### C. Personas under user/ memory — not a content issue, structural note

`.claude/agent-memory/user/personas/` exists but contains the live persona files for user-sim missions (Mara, Mark, Devin, etc.). These are state-rich and session-driven — not memory in the lead-cutting-cross-agent-rules sense. Out of scope for this audit; flagging that they exist so a future "memory file count" sweep doesn't lump them together.

### D. Some old planner files are pre-rename relics

`planner/` has `project_phase7_github_canonical.md`, `project_judge_strategy.md`, `project_continuity_gap.md` — all 2026-04-09–14 era artifacts that predate the current daemon-economy + decomp + rename arcs. They're not contradicting current truth; they're just historical decisions that may not be load-bearing for current planner work. Optional cleanup item; not a finding.

### E. `dev-2/MEMORY.md` is small (10 entries) — could absorb more cross-cutting rules

dev-2 is the floater role per `feedback_floating_fifth_teammate` (lead memory). It swaps onto dev tasks regularly. 2026-05-01 refresh: the two highest-value candidates from the original sweep are now present (`feedback_no_destructive_git.md` and `feedback_run_build_plugin_after_canonical_edits.md`). Other possible additions, such as `feedback_three_mirrors_dist_may_diverge` and `feedback_silence_after_ack`, remain situational.

## Suggested fix sequence (lead-driven)

1. **Finding #1 — verifier stash conflict.** Closed as of 2026-05-01 refresh.

2. **Finding #2 — lead MEMORY.md "Universe Server" stale refs.** Lead-environment-only: no `MEMORY.md` file exists in this checkout. If present in the lead runtime environment, apply the 2-line branding edit there.

3. **Findings #3 + #4 — coverage gaps.** Closed as of 2026-05-01 refresh.

4. **Observation A — lead memory budget overflow.** Decide how to split or trim lead's MEMORY.md. Could be 30-min cleanup. Important because the truncation means lead currently isn't loading its full memory at session start.

5. **Finding #5 + Observation E — leave as-is.** No action; flagged for awareness only.

## Verifier handoff

This is now a refreshed recommendation document. No agent memory was edited by this refresh; it only records that current memory state has closed the stale open items.

No code touched. No test files touched. No dev #18 lock-set touched.
