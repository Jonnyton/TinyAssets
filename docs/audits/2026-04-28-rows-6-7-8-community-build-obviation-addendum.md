---
title: STATUS Concerns rows 6/7/8 — community-build obviation pass (addendum to staleness audit)
date: 2026-04-28
author: navigator
status: read-only audit — applies `feedback_obviated_item_check_against_completion_plans` to host-Q lists in 3 design notes
companion:
  - docs/audits/2026-04-28-status-md-concerns-staleness-pass.md (parent — flagged rows 6/7/8 for further analysis)
  - docs/audits/2026-04-28-status-md-coordination-gap.md (sibling — established the methodology)
  - docs/audits/2026-04-28-internal-scoping-threads-abc.md (sibling — same OBVIATED-item-check pattern, different surface)
  - feedback_obviated_item_check_against_completion_plans (navigator memory) — methodology applied here
  - project_privacy_via_community_composition (lead memory 2026-04-26) — the principle obviating most of row 6+7
  - project_community_build_over_platform_build (lead memory 2026-04-26) — parent principle
  - docs/audits/2026-04-28-commons-first-tool-surface-audit.md F3 — the path forward for row 7
load-bearing-question: For each host-Q in the 3 design notes that rows 6/7/8 cite, is the question still platform-decision-bound, or has it been OBVIATED by the 2026-04-26 community-build principles?
audience: lead, host
---

# Rows 6/7/8 community-build obviation pass

## TL;DR

Atomized the host-Q lists in all 3 design notes (per `feedback_obviated_item_check_against_completion_plans`). Per-Q verdict against `project_privacy_via_community_composition` + `project_community_build_over_platform_build`:

| Row | Note | Host-Qs identified | OBVIATED | REFRAMED | STILL-PLATFORM |
|---|---|---|---|---|---|
| **6** | privacy modes | 3 (§6) | 2 | — | 1 |
| **7** | `add_canon_from_path` sensitivity | 3 (§7) | — | 3 | — |
| **8** | claude.ai injection | **0** (no host-Q section exists) | — | — | — |

**Headlines:**
1. **Row 8 is mis-framed in STATUS.** The note has NO `Open questions for host` section. STATUS row says "blocked on host-Q batch" but the actual content is §5 dev-actionable text edits to tool descriptions. The block is on dev capacity (queued behind #18), not host input. **Reframe row** to point at dev work.
2. **Row 6 has 1 genuine STILL-PLATFORM question** (third-party providers in fallback chain — provider-router config). The other 2 (threat-model scope + metadata-acceptable) are OBVIATED — chatbot decides per-conversation per the new principles.
3. **Row 7 is fully REFRAMED, not OBVIATED.** Commons-first audit F3 (`add_canon_from_path` self-auditing-tools annotation, 2026-04-28) is the canonical path forward. The original §5 recommendation (extract to its own tool) is superseded.

**Net STATUS impact:** retire 0, reframe 3. All 3 rows shrink in scope; one row (8) was straight-up wrong about its blocker class.

---

## 1. Row 6 — Privacy mode note

**Source:** `docs/design-notes/2026-04-18-privacy-modes-for-sensitive-workflows.md` §6 ("Open questions for host").

### Per-Q verdict

| Q | Question | Verdict | Reason |
|---|---|---|---|
| Q6.1 | Threat model scope: defending against (a) Anthropic-as-honest-operator, (b) Anthropic-as-adversary, or (c) arbitrary observers? | **OBVIATED** | `project_privacy_via_community_composition` (2026-04-26): "chatbot reads the user's stated threat model from chat context and applies appropriate composition." Threat model is per-conversation, not platform-fixed. The Q presupposed a platform-wide answer; principle says no platform-wide answer is needed. |
| Q6.2 | Metadata acceptable? Is "host runs an Allied AP workflow" itself sensitive? | **OBVIATED** | Same principle: chatbot decides per-piece per `project_privacy_per_piece_chatbot_judged`. Metadata sensitivity is community-build composition, not platform-tier flag. The §7.5 universe-aliasing primitive becomes a community-composition recipe, not a mandatory platform feature. |
| Q6.3 | Third-party providers in daemon fallback chain — ever? | **STILL-PLATFORM** | Provider router config (`tinyassets/providers/router.py`) is platform code; community can't compose around it via existing primitives. The Q remains a real platform decision: should the fallback chain accept third-party providers when local is unavailable, or pause-and-wait? Per principle, this is platform-policy because it's structurally not chatbot-composable. |

### Reframe recommendation

Row 6 currently:
> [2026-04-17] Privacy mode note has 3 host Qs: `docs/design-notes/2026-04-18-privacy-modes-for-sensitive-workflows.md`.

Reframe to:
> [2026-04-17→28] Privacy mode note: 2 of 3 host-Qs OBVIATED by community-build principle (per audit `docs/audits/2026-04-28-rows-6-7-8-community-build-obviation-addendum.md`). 1 remaining: third-party providers in fallback chain (Q6.3) — STILL-PLATFORM. Note also needs reframe header to match community-build direction.

### Note action

Same pattern as the methods-prose evaluator REFRAME (Concern row 5, audit-applied 2026-04-26): the design note's framing pre-dates the community-build directive. Recommend a one-line dev-2 task to:
1. Add a frontmatter `status: superseded-by-principle` + `superseded_detail: <pointer to project_privacy_via_community_composition>` to the design note.
2. Prepend a HEADER block: "**HISTORICAL FRAMING — superseded.** Per host directive 2026-04-26, privacy modes are community-build, not platform primitives. The §7 private-universe flag + §8 redactor surface are NOT shipping as platform; they may inform community-composed patterns."
3. Leave §6 Q6.3 explicitly tagged as the only remaining platform question.

---

## 2. Row 7 — `add_canon_from_path` sensitivity note

**Source:** `docs/design-notes/2026-04-18-add-canon-from-path-sensitivity.md` §7 (2026-04-19 follow-up).

### Per-Q verdict

| Q | Question | Verdict | Reason |
|---|---|---|---|
| Q7.1 | Has MCP shipped `sensitiveHint` / `secretHint` / `neverAutoApprove`? Is FastMCP per-call-confirm possible? | **REFRAMED** | Original Q presupposed extracting `add_canon_from_path` to its own tool was the target. Commons-first audit F3 (2026-04-28) reframes: instead of tool extraction, annotate with self-auditing-tools structured-caveats response shape (`commons_visibility`, `host_path_recorded`, `whitelist_check`). Chatbot composes the user-facing approval narrative on top. The MCP-spec sensitiveHint question is moot — F3 doesn't need protocol features that don't exist. |
| Q7.2 | Is option-b viable standalone (without #11 M1)? | **REFRAMED** | F3 supersedes option-b — no tool extraction needed; instead the verb stays on `universe` but its response shape adds structured commons-vs-host-resident metadata. F3 is independent of M1 timing entirely. |
| Q7.3 | Recommendation: ship now or wait? | **REFRAMED** | F3 is "ship the structured caveat now"; M1 question becomes moot. |

### Plus: principle-level reframe

Per `project_privacy_via_community_composition`: SENSITIVITY classification is community-build (chatbot decides per-piece what's sensitive). Platform owns ENFORCEMENT primitives only — `TINYASSETS_UPLOAD_WHITELIST` (live), F3 self-auditing structured caveats (proposed). The note's §1 question framing ("can the server mark `add_canon_from_path` as never-auto-approve?") is the wrong question under the new principle; the right question is "does the chatbot have the structured evidence to compose its own per-piece approval narrative?" — which F3 answers.

### Reframe recommendation

Row 7 currently:
> [2026-04-18] `add_canon_from_path` sensitivity note has 3 host asks: `docs/design-notes/2026-04-18-add-canon-from-path-sensitivity.md`.

Reframe to:
> [2026-04-18→28] `add_canon_from_path` sensitivity: 3 host-Qs all REFRAMED by commons-first audit F3 (self-auditing-tools annotation per `docs/audits/2026-04-28-commons-first-tool-surface-audit.md`). Path forward = structured-caveat response shape, not tool extraction or new MCP-spec primitives. Note needs reframe header.

### Note action

Same one-line reframe pattern as row 6. Frontmatter `status: superseded-by-F3` + cross-link to commons-first audit.

---

## 3. Row 8 — Claude.ai injection mitigation

**Source:** `docs/design-notes/2026-04-18-claude-ai-injection-hallucination.md`.

### Per-Q verdict

**No `Open questions for host` section exists in the design note.** I greped for `host[- ]Q`, `host[- ]ask`, `open question`, `TODO.*host` — zero matches.

The note's content:
- §1-4: trace + root-cause hypothesis (analysis)
- §5: mitigations on the TinyAssets Server side — text edits to tool `description` fields, prompt-text moves
- §5.5: 2026-04-19 Maya-evidence additions (control_station prompt directives)
- §6: out-of-scope items
- §7: recommendation for STATUS.md
- §8: sources

**§5 + §5.5 are dev-actionable text edits.** No host input is required for any of them. The work is:
- Move "NO SIMULATION / AFFIRMATIVE CONSENT / INTENT DISAMBIGUATION / CROSS-UNIVERSE" prose out of `extensions` tool docstring into `_EXTENSION_GUIDE_PROMPT` (already exists at L1003).
- De-dup "NO SIMULATION" phrase across server-instructions + 2 prompts + extensions docstring → keep one canonical occurrence in `control_station`.
- Avoid all-caps directive clusters in tool descriptions.
- Keep tool descriptions short (~3-5 lines).
- Add 2 Maya-evidence directives to `control_station` prompt.

### Verdict: STATUS row mis-framed

Row 8 says "Claude.ai injection mitigation blocked on host-Q batch." There is no host-Q batch. The block is on **dev capacity sequenced after #18** (universe_server.py is the file the edits touch — plugin-mirror-collision rule applies).

### Reframe recommendation

Row 8 currently:
> [2026-04-18] Claude.ai injection mitigation blocked on host-Q batch: `docs/design-notes/2026-04-18-claude-ai-injection-hallucination.md`.

Reframe to (and move out of Concerns into Work table):
> Work table: `Claude.ai injection mitigation — §5 + §5.5 dev-actionable text edits (move directives out of tool descriptions, de-dup phrases, add Maya control_station directives). Sequenced after #18 per plugin-mirror-collision rule. | tinyassets/universe_server.py + prompt files | #18 | dev-ready |`

Also retire the Concern row entirely once the Work row lands — the row was a mis-classification.

### Note action

No reframe header needed; the note is a research/recommendation doc and §5/§5.5 are correctly scoped. Just dispatch the work to dev.

---

## 4. Net STATUS impact

| Row | Current state | Recommended action |
|---|---|---|
| 6 | "3 host Qs" | Reframe to "2 OBVIATED, 1 STILL-PLATFORM (Q6.3 fallback policy)" + note header reframe task |
| 7 | "3 host asks" | Reframe to "all REFRAMED by commons-first F3" + note header reframe task |
| 8 | "blocked on host-Q batch" | RETIRE Concern + add Work-table row for dev-actionable §5/§5.5 edits sequenced after #18 |

**Net Concern lines:** 3 reframed (1 retire + 2 reword); -3 to 0 in net line count (Work table picks up row 8's content).

**Host-Q load reduction:** 6 host Qs → 1 host Q (Q6.3 fallback policy). 5 of 6 obviated/reframed.

**New work surfaced:**
- 2 lightweight dev-2 frontmatter+header reframe tasks (rows 6 + 7 design notes).
- 1 dev task: row 8's §5 + §5.5 prompt-discipline edits (sequenced after #18; ~1-2h effort).

---

## 5. Decision asks

For lead (apply autonomous per `feedback_dont_ask_host_internal_scoping` + `feedback_status_md_evidence_based_retire`):
1. Approve row 6 reframe + design-note header reframe task?
2. Approve row 7 reframe + design-note header reframe task?
3. Approve row 8 retire (Concern) + Work-table-row addition for §5/§5.5 dev edits?
4. Approve standalone host-Q tracking row for Q6.3 (third-party providers in fallback chain)? — this is the only genuinely host-bound item from the 3 notes.

I lean YES on all four. Together they shrink the host-Q surface from 6 questions to 1, retire 1 mis-framed Concern, and surface 1 new dev-ready task that was hiding inside the wrong classification.

---

## 6. Cross-references

- `docs/audits/2026-04-28-status-md-concerns-staleness-pass.md` — parent audit (dev-2)
- `docs/audits/2026-04-28-status-md-coordination-gap.md` — sibling, same methodology applied to ChatGPT P1s
- `docs/audits/2026-04-28-internal-scoping-threads-abc.md` — sibling, same OBVIATED-item-check applied to R7
- `docs/audits/2026-04-28-commons-first-tool-surface-audit.md` F3 — the path forward for row 7
- `feedback_obviated_item_check_against_completion_plans` (navigator memory) — methodology
- `project_privacy_via_community_composition` (lead memory) — the principle obviating row 6 Q6.1/Q6.2
- `project_community_build_over_platform_build` (lead memory) — parent principle
- `feedback_dont_ask_host_internal_scoping` (lead memory) — autonomy authority
