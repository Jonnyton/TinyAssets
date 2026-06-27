---
title: AGENTS.md rule-addition drafts (4 candidates from cross-check audit)
date: 2026-04-28
author: dev-2
status: draft for lead review — proposed inserts not yet merged into AGENTS.md
companion:
  - docs/audits/2026-04-28-project-instruction-files-cross-check.md (parent audit; findings #4/#5/#6 + soft-suggestion #5 source)
  - docs/audits/2026-04-28-agent-memory-cross-drift-sweep.md (cross-agent coverage matrix)
load-bearing-question: For each of the 3 confirmed coverage gaps + 1 soft suggestion, what's the proposed inserted text + the right placement + the audit-doc citation justifying it?
audience: lead
---

# AGENTS.md rule-addition drafts

Four drafts for review. Each draft = (a) proposed inserted text, (b) proposed location in AGENTS.md, (c) audit citation justifying the addition.

Style: match existing AGENTS.md cadence — bold lead-in, brief explanation, ~1-3 sentences. Don't bloat. Reference agent memory + audit docs for fuller context rather than restating the full rule.

---

## Draft 1 — No-destructive-git rule (Hard Rules section)

**Proposed location:** insert as new Hard Rule #12 (after current #11 public-surface-canary rule).

**Proposed text:**

```
12. **No destructive git ops without explicit approval.** `git stash`, `git reset`, `git checkout --`, `git clean`, `git branch -D`, and similar destructive ops require user approval — even for read-only diagnostic intent (the planned-stash + planned-pop pattern is destructive-by-classification). Use `git diff HEAD` / `git show HEAD:<path>` to inspect committed state without touching the working tree. The 2026-04-18 navigator slip + 2026-04-28 verifier-memory contradiction (audit `docs/audits/2026-04-28-agent-memory-cross-drift-sweep.md` finding #1) confirm this rule needs codification beyond agent memory.
```

**Audit citation:** parent audit §4 + agent-memory cross-drift sweep finding #1. Rule lives in 4 agent memories (lead `feedback_git_destructive`, dev `feedback_no_git_stash_for_diagnostics`, navigator `feedback_no_diagnostic_stash`, dev-2 `feedback_no_destructive_git`) but missing from AGENTS.md proper.

**Why Hard Rules placement (not "How to Work"):** the rule's enforcement is binary (destructive op = approval gate), not procedural. Other Hard Rules (#1 SqliteSaver, #8 fail loudly, #9 user uploads authoritative) follow the same shape — short, binary, no-exception.

---

## Draft 2 — Plugin-mirror-rebuild rule (Hard Rules section)

**Proposed location:** insert as new Hard Rule #13 (after Draft 1's #12).

**Proposed text:**

```
13. **Plugin-mirror rebuild after `tinyassets/*` canonical edits.** `python packaging/claude-plugin/build_plugin.py` re-syncs the canonical → plugin mirror at `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/`. Pre-commit invariant blocks the commit if the mirror is out of sync (it does not auto-rebuild). During in-flight decomp/rename arcs (e.g. Task #18-class work), the plugin mirror is in dev's lock-set — concurrent `tinyassets/*` audit dispatch from dev-2 / navigator / cowork is forbidden. After dev's arc SHIPs, mirror-rebuild is the writer's responsibility before staging.
```

**Audit citation:** parent audit §5 + dev memory `feedback_run_build_plugin_after_canonical_edits` + navigator memory `project_plugin_mirror_collision_with_dev_lockset` + dev-2 memory `feedback_plugin_mirror_collision_during_decomp_arcs` (saved earlier this session).

**Why Hard Rules placement:** the rule has two binary effects — (a) commit gate (pre-commit blocks), (b) collision gate during decomp arcs. Both are hard-stop, not procedural. The collision-during-arcs sub-rule is what made dev-2 stay doc-only this entire session (validated: 79-file lock-set untouched across 50+ doc edits).

**Alternative placement considered:** Testing section (since the trigger is mostly post-edit pre-commit). Rejected because the lock-set-collision sub-rule is the load-bearing one, and that's not "testing" — it's coordination.

---

## Draft 3 — Audit-staleness rule (Truth And Freshness section)

**Proposed location:** add as a new bullet to the existing "Truth And Freshness" subsection of "How to Work" (current bullets at AGENTS.md L106-111). Insert after the existing "Verification claims must be freshness-stamped" bullet.

**Proposed text:**

```
- **Audit docs decay too.** Audits >24 hours old are routinely stale; before dispatching audit prescriptions, run a freshness check (`git log --since=<audit-date> -- <target-files>` + grep symbols + spot-read code) to confirm the target hasn't moved. Treat audit prescriptions as proposals, not specs. After corrected work lands, the navigator updates the audit doc to reflect actual state.
```

**Audit citation:** parent audit §6 + 4 agent memories converge on this rule (lead `feedback_audit_freshness_check`, navigator `feedback_audit_freshness_check`, dev `feedback_audits_often_stale`, dev-2 `feedback_audits_can_be_already_done`). 4 agent memories with different framings = strong signal the rule belongs in shared truth.

**Why Truth-and-Freshness placement:** this is a freshness-stamp rule for audit docs specifically, parallel to the existing freshness-stamp rule for verification claims. The two should sit together so a reader thinking "what counts as fresh in this repo?" finds both.

**Why one bullet, not its own subsection:** existing T&F section is 6 bullets at L106-111; adding a 7th matches the cadence. A new subsection would over-emphasize a rule that's the same shape as its neighbors.

---

## Draft 4 — Evidence-based-retire refinement (STATUS.md deletion rules)

**Proposed location:** add to the existing "STATUS.md deletion is as important as addition" subsection of "Updating the Three Files" (current bullets at AGENTS.md L94-102). Insert as a new clarifying bullet at the end of the bullet list, OR as a one-line italic refinement note immediately before the bullets.

**Proposed text (bullet form, recommended):**

```
- **Evidence-based retire is OK; gut-feel trim is not.** Lead/navigator MAY retire/reframe Concerns or Work rows when they have audit-doc / git-log / activity-log evidence + a one-line citation in the commit or session-log. Without evidence, defer to host. (`feedback_status_md_evidence_based_retire` in lead memory refines `feedback_status_md_host_managed`.)
```

**Proposed text (italic-note form, alternative):**

```
*Refinement:* `feedback_status_md_evidence_based_retire` (lead memory) authorizes evidence-based retire/reframe by lead+navigator with an audit-doc / git / activity-log citation. Gut-feel trim is still forbidden.
```

**Audit citation:** parent audit cross-file consistency check + soft suggestion #5 ("Currently in lead memory only — worth surfacing"). Other providers (Codex / Cowork) reading AGENTS.md don't see the refinement and may either over-defer (block on host) or over-trim (gut-feel, contradicting the host-managed rule).

**Why this refinement is worth surfacing:** it resolves an apparent contradiction. The existing "every reader is a janitor" line (L65) suggests aggressive trim; the host-managed rule per memory says revert auto-trims. The refinement is the resolution: with evidence, trim is OK; without, hands off. Codifying it kills the tension.

**Why bullet form recommended over italic-note:** matches the cadence of the surrounding bullets. The italic-note form is more visually distinct but breaks the rhythm.

---

## Summary table for lead review

| Draft | Severity | Insert location | Lines added | Risk |
|---|---|---|---|---|
| 1 | Hard rule (no destructive git) | New Hard Rule #12 | ~3 | Low — codifies existing 4-memory rule |
| 2 | Hard rule (plugin-mirror rebuild) | New Hard Rule #13 | ~4 | Low — codifies existing 3-memory rule + this-session validation |
| 3 | Procedural (audit staleness) | Truth-and-Freshness new bullet | ~2 | Low — codifies existing 4-memory rule |
| 4 | Procedural (evidence-based retire) | STATUS.md deletion bullet | ~2 | Low — surfaces existing lead-memory refinement to all providers |

**Total addition: ~11 lines to AGENTS.md** if all 4 land. AGENTS.md is currently 382 lines / ~17.6 KB; this would push it to ~393 lines / ~18.5 KB. Within reasonable budget.

## Verifier handoff

Drafts only. Lead reviews + merges approved drafts into AGENTS.md proper. Nothing applied to AGENTS.md by this audit pass beyond the 4 small fixes already authorized in the prior dispatch (Findings #1, #2, #3, #7).

No code touched. No test files touched. No dev #18 lock-set touched.
