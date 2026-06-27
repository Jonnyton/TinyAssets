---
title: STATUS.md coordination gap — how 4 ChatGPT P1s went stale
date: 2026-04-28
author: navigator
status: read-only diagnostic — proposes 3 STATUS curation rule additions
companion:
  - feedback_audit_freshness_check (navigator memory) — apply freshness check to "pending X" qualifiers, not just code-extraction
  - feedback_dont_ask_host_internal_scoping (lead memory) — host time is rate-limit; don't queue internal scoping
load-bearing-question: How did 4 P1 STATUS Concerns from 2026-04-24 (filed during Mara live-user test) end up at 2026-04-28 still listed unchanged, when 3 of 4 were duplicates / not-server / self-resolved?
audience: lead, host
---

# STATUS.md coordination gap

## TL;DR

Four ChatGPT P1 STATUS Concerns dated "2026-04-25" were actually filed 2026-04-24 during a single codex Mara live-user test session. By 2026-04-28 (4 days later):

- **P1.1** (ChatGPT publish blocked) — operational/OpenAI-side, not server bug, not actionable from team
- **P1.2** (Update Node approval errored) — duplicate of BUG-034 (already separately filed P1)
- **P1.3** (Run Branch approval stalled) — duplicate of BUG-034 family
- **P1.4** (name-vs-ID UX) — **self-resolved in same session** per `.agents/activity.log:2026-04-24T20:11:07Z` ("ChatGPT name-ref recovery succeeded: Mara said 'my climate-claims workflow'; ChatGPT resolved branch ID without asking")

Net real action items from Mara session: BUG-029 + BUG-030 (filed correctly as wiki bugs, server-side track active). The 4 STATUS Concern rows were ambient observations during the live-user run, not durable concerns. They drifted without curation.

**Coordination gap, three layers:**
1. **No date-stamp drift detection** — "[2026-04-25]" stayed static while 4 days passed. No freshness gate.
2. **Concerns + BUG pages weren't reconciled** — BUG-034 (filed 2026-04-25 Mark session) covers same root cause as P1.2 + P1.3, but Concerns kept them as separate rows.
3. **Self-resolution wasn't propagated** — codex's "name-ref recovery succeeded" entry in activity.log never made it to STATUS Concern row P1.4.

The "[YYYY-MM-DD]" prefix convention exists per AGENTS.md ("Verification claims must be freshness-stamped"), but it's a date the concern was FILED, not a date it was last verified-still-valid. Without a re-verification cadence, every concern row decays into stale state.

---

## 1. Methodology

Read STATUS.md current state + `.agents/activity.log` from 2026-04-24 onward + wiki BUG-029/030/034 + `git log --since=2026-04-24 --grep=ChatGPT|connector|approval`. Cross-referenced against:
- BUG-034 wiki page (filed 2026-04-25, currently triaged as ChatGPT-side)
- BUG-029 wiki page (filed 2026-04-24, currently open with structured failure_class fix landed in commit 0f5ccc4)
- BUG-030 wiki page (filed 2026-04-24, currently open)

---

## 2. Per-P1 reconciliation

### P1.1 — ChatGPT publish blocked (`TinyAssets DEV` Plus/private app)

**Source:** STATUS.md Concern row 18.
**Origin:** Filed during Mara session 2026-04-24, escalated to P1 2026-04-26 per provider-parity principle.
**Root cause:** OpenAI workspace-policy issue — `TinyAssets DEV` connector was published as Plus-tier private app, not workspace admin. To publish to workspace requires re-registration as admin.
**Wiki bug?** None — operational, not a server bug.
**Actionable from team?** NO — host action (re-register the OpenAI app as workspace admin) OR OpenAI escalation.
**Current state:** UNCHANGED since filing. No team-side fix exists.
**Recommendation:** **RETAIN as host-action concern** but reframe — this isn't a code bug, it's a host operational task. Move from generic "P1" to a `host-action` row in the Work table with a 1-line target ("re-register TinyAssets DEV as workspace admin in OpenAI ChatGPT settings").

### P1.2 — ChatGPT connector approval bug (Update Node errored, retry saved v2)

**Source:** STATUS.md Concern row 19.
**Origin:** Filed 2026-04-24T19:57Z by codex during Mara test.
**Root cause:** ChatGPT connector approval-prompt bug — same as BUG-034.
**Wiki bug?** Subsumed by BUG-034 ("All extensions actions return 'No approval received'").
**Current state:** Status comment landed on BUG-034 wiki page 2026-04-28 (during Thread #15 drain) noting ChatGPT-side track + platform mitigation via `goals action=get`.
**Recommendation:** **RETIRE as DUPLICATE.** P1.2 is the "Update Node" specific-case symptom of the BUG-034-class issue. Concern row already cross-references BUG-034 in row 22. Delete row 19; keep row 22 (BUG-034) as the canonical concern.

### P1.3 — ChatGPT Run Branch approval stalled

**Source:** STATUS.md Concern row 20.
**Origin:** Filed 2026-04-24T20:03Z by codex during Mara test.
**Root cause:** Same connector approval-prompt bug — same as BUG-034.
**Wiki bug?** Subsumed by BUG-034.
**Current state:** Same as P1.2.
**Recommendation:** **RETIRE as DUPLICATE.** Same disposition as P1.2. Delete row 20; row 22 (BUG-034) is canonical.

### P1.4 — name-vs-ID UX

**Source:** STATUS.md Concern row 21.
**Origin:** Filed 2026-04-24T20:09Z by codex (host UX steering during Mara test).
**Root cause:** Initially flagged as "normal users shouldn't have to say raw branch IDs."
**Self-resolution:** `.agents/activity.log:2026-04-24T20:11:07Z` — codex's NEXT log entry: *"ChatGPT name-ref recovery succeeded: Mara said 'my climate-claims workflow'; ChatGPT resolved `mara_adaptation_claims_2step` without asking for ID."* The behavior the concern flagged works correctly; the test confirmed it 2 minutes after the concern was filed.
**Wiki bug?** None.
**Current state:** STALE; was already resolved at filing time +2 minutes. The concern row never got the resolution propagated.
**Recommendation:** **DELETE.** Already resolved by observation; never a real issue. The original ambiguity ("STATUS concern added for poor provider/credentials surfacing") refers to BUG-029, which IS open and tracked separately.

### Bonus: P1.5 (BUG-034)

**Source:** STATUS.md Concern row 22.
**Status:** Wiki status comment landed 2026-04-28 (Thread #15 drain). Triage = ChatGPT-side, not server. Two parallel tracks: platform mitigation (live in chatbot-builder-behaviors.md) + OpenAI escalation (host).
**Recommendation:** **RETAIN as canonical row** for the family of ChatGPT-approval bugs. Update timestamp to "[2026-04-25→28]" to reflect last-verified date.

---

## 3. Net STATUS.md edit

**Concerns to retire:**
- Row 19 (P1.2 Update Node): DUPLICATE of row 22.
- Row 20 (P1.3 Run Branch): DUPLICATE of row 22.
- Row 21 (P1.4 name-vs-ID): SELF-RESOLVED 2026-04-24T20:11Z; never a real issue.

**Concerns to keep with reframe:**
- Row 18 (P1.1 publish blocked): reframe as `host-action` Work-table row, not free-form P1 Concern.
- Row 22 (BUG-034): retain; bump date to "[2026-04-25→28]".

**Net effect:** STATUS.md Concerns shrinks by 3 rows. Concerns budget recovers ~6 lines.

---

## 4. The coordination-gap pattern

The 4 P1s drifting unchanged is one instance of a recurring pattern:

**Pattern: filed-during-test concerns become persistent without re-verification.**

A live-user test session generates real-time observations ("ChatGPT errored on approval"). These get filed as STATUS Concerns to capture the signal. After the session ends, no agent revisits them — they become persistent without re-verification. The original session's NEXT log entry often resolves them, but the resolution stays in `.agents/activity.log` and never propagates to STATUS.

**Existing rule that catches this:** AGENTS.md says "Contradictions must be downgraded immediately. If current code, runtime artifacts, or verification output contradict an older claim, rewrite the STATUS.md claim or add a Concern before responding."

The rule is correct; the FAILURE MODE is that no one re-reads STATUS Concerns proactively. They're a write-only surface in practice.

---

## 5. Proposed STATUS.md curation rule additions

### Rule 1: **Concern rows decay; force re-verification at N=4 days idle.**

Every Concern row gets:
- `[filed: YYYY-MM-DD]` (when added)
- `[verified: YYYY-MM-DD]` (last time someone re-checked the concern is still valid)

If `verified` is more than 4 days behind `today`, the row is "stale." Stale concerns get a header-level callout: "**STALE** — re-verify or retire on next session start."

The 4-day threshold is calibrated against this gap: the 4 P1s went stale at exactly the 4-day mark. Faster threshold would be noisy; slower threshold misses the repair window.

**Implementation:** session-start ritual for whichever agent reads STATUS first (lead, navigator) — scan Concern rows, mark stale, and either re-verify or retire one stale row per session-start.

### Rule 2: **Live-user test concerns get a `[test-session: <id>]` tag.**

Concerns filed during a live-user test session (Mara, Mark, Devin, Tomás, etc.) are inherently ephemeral — they're observations during a specific session. Tag them so they're easy to batch-retire after the session log gets written.

After the session-log is written and findings propagated, ALL test-session-tagged concerns get reviewed: keep (real bug found), retire (transient observation), or convert (filed as wiki bug + retired from STATUS).

**Implementation:** add `[test-session: mara-2026-04-24]` etc. to STATUS Concern rows. After session-log lands in activity.log, batch-retire/convert.

### Rule 3: **Concern + Wiki BUG mutual cross-reference required.**

If a Concern row describes a server-side bug, it MUST link to a wiki BUG-NNN page. If a wiki BUG-NNN page is severity P0/P1, it MUST have a STATUS Concern row OR a Work-table row. The two surfaces are coupled; they shouldn't drift.

When BUG-034 was filed but P1.2 + P1.3 stayed as separate Concern rows, the duplication was invisible because there was no cross-reference convention.

**Implementation:** mandate `(see BUG-NNN)` suffix on every server-bug Concern row. Mandate `STATUS row: <quoted concern text>` in every P0/P1 wiki BUG page header.

---

## 6. Why this audit matters beyond this incident

The "host time is rate-limit" memory rule (`feedback_dont_ask_host_internal_scoping`) only works if STATUS doesn't accumulate noise that demands host attention. Stale Concerns are a bigger noise tax on host than missing Concerns.

If host opens STATUS.md once a week and sees 4 P1s that are duplicates / stale / not-actionable, the trust signal degrades — host has to investigate "is anything real here?" That's exactly the time-on-team-internal-scoping the rule is trying to prevent.

The 3 curation rules above are designed to keep STATUS.md as a HIGH-SIGNAL surface that earns host attention, not a JOURNAL that accumulates everything ever observed.

---

## 7. Decision asks

For lead (apply autonomous per the new rule):
1. Approve §3 net edit (retire 3 rows, reframe 1, retain 1)?
2. Approve §5 Rule 1 (4-day staleness threshold)?
3. Approve §5 Rule 2 (test-session tagging)?
4. Approve §5 Rule 3 (Concern↔BUG cross-reference mandate)?

I recommend YES on all four. None require host input — these are internal STATUS curation discipline.
