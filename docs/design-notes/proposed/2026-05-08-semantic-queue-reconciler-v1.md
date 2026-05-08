---
title: Semantic Queue Reconciler V1
date: 2026-05-08
author: codex-wiki-docs
status: proposed
request_id: WIKI-DOCS
github_issue: 636
wiki_source: pages/concepts/semantic-queue-reconciler-v1.md
scope: design-only; no runtime code in this branch
builds_on:
  - PLAN.md#scoping-rules
  - PLAN.md#harness-and-coordination
  - PLAN.md#uptime-and-alarm-path
  - .agents/skills/loop-uptime-maintenance/incidents/2026-05-05-auto-fix-head-of-line-retry.md
---

# Semantic Queue Reconciler V1

## 1. Recommendation Summary

Treat `semantic_queue_reconciler_v1` as a loop-discipline substrate concept,
not ordinary documentation backlog. The useful v1 is a convention for noticing
when the community loop's selected work no longer matches the live meaning of
the queue, then forcing the loop to refactor its own queue state before it
spends more attempts on lower-leverage work.

The recent red-loop evidence gives the target failure shape: BU-001, BU-002,
BU-003, and Phase 4 work stayed pending while recovery selected other work.
That is not just queue depth. It is a semantic mismatch between "what the loop
is doing" and "what would unblock the largest current uptime surface." V1
should make that mismatch visible and reviewable before any runtime scheduler
change is attempted.

Do not add a chatbot-visible MCP action in v1. The first useful artifact is a
shared design convention plus a future implementation path for existing
surfaces: `community_loop_watch.py`, GitHub labels, `STATUS.md` rows, and the
daemon wiki blocked-patterns page.

## 2. Concept

A semantic queue reconciler compares queue items by their effect on the loop's
current ability to operate, not only by age, label, or issue number.

It answers four questions:

1. Which pending items share the same root loop-discipline failure class?
2. Which class blocks the largest current uptime surface?
3. Is the selected next item advancing that class, or is the loop spending a
   scarce writer slot elsewhere?
4. If selection and priority disagree, what queue metadata or work row needs to
   change before the next attempt?

The reconciler is not an auto-planner and not a general priority oracle. It is
a guardrail for witnessed mismatch. It should only fire when there is concrete
evidence that queue selection is bypassing a declared loop-discipline substrate
blocker.

## 3. V1 Data Shape

Each reconciliation event should be expressible as a small record:

```yaml
id: semantic-queue-reconcile-2026-05-08-bu-phase4
observed_at: 2026-05-08T00:00:00Z
trigger:
  kind: loop_discipline_mismatch
  evidence:
    - BU-001 pending
    - BU-002 pending
    - BU-003 pending
    - Phase 4 pending
    - recovery selected unrelated work
semantic_class: loop-discipline-substrate
expected_next_kind: substrate-unblocker
actual_next_kind: unrelated-docs-or-patch
recommended_queue_change:
  - apply priority:loop-discipline to implicated issues
  - create or update a STATUS.md row only if cross-provider work is needed
  - add blocked-patterns evidence before another writer attempt
```

Fields are intentionally plain. The record can start as a GitHub comment,
watch output, or design artifact. A future implementation can persist it as
JSON only after the convention proves stable.

## 4. Routing Rules

V1 routing should use these rules:

1. If a request says it affects queue selection, recovery ordering, stalled
   pending loop items, or repeated same-class writer failures, classify it as
   `priority:loop-discipline` even when the request kind is docs-ops.
2. If multiple pending items share a loop-discipline substrate class, prefer
   the smallest substrate unblocker over unrelated queue cleanup.
3. If the selected next item is unrelated while a substrate class remains red,
   the watch should report a semantic mismatch separately from generic pending
   backlog.
4. If the mismatch requires cross-provider coordination, promote it into
   `STATUS.md` with a narrow Files cell. Otherwise, leave it as issue metadata
   or a wiki/design artifact.
5. If a proposed fix would add a new platform primitive, run the PLAN.md
   scoping rules first. Most queue reconciliation should remain community-loop
   policy over existing primitives.

## 5. Non-Goals

- No new MCP action in v1.
- No automatic reprioritization of all GitHub issues.
- No rewrite of community-authored branches.
- No replacement for the existing gate ladder or opposite-family checker
  requirement.
- No broad scheduler redesign based on one incident.

## 6. Future Implementation Path

Step 1: teach `community_loop_watch.py` to emit a dedicated
`semantic_mismatch` finding when a `priority:loop-discipline` item or grouped
loop-discipline class remains pending while the active writer run selects an
unrelated request.

Step 2: add a focused test fixture with the witnessed shape: BU-001, BU-002,
BU-003, and Phase 4 pending while recovery selects a non-substrate docs item.
The expected output should be a red loop-discipline mismatch, not a generic
old-pending warning.

Step 3: when a mismatch is found, write one concise GitHub comment or watch
artifact that names the semantic class, the skipped items, the selected item,
and the smallest queue metadata change needed.

Step 4: feed repeated mismatch classes into `pages/brain/blocked-patterns.md`
so future daemon claims read the pattern before drafting a coding packet or
release-gate verdict.

Step 5: only after the watch-level convention proves useful, consider a small
queue-selection policy change. That change should remain bounded to the writer
loop and should not become a general project priority engine.

## 7. Fit With PLAN.md

This proposal follows the minimal-primitives rule because it documents a
composition and watch convention before adding tooling. It follows
community-build over platform-build because the first durable behavior is a
wiki/issue/STATUS discipline that the loop can evolve from its own evidence.

It fits the uptime path because the trigger is a witnessed failure class with a
known operational consequence: the loop spends recovery attempts away from the
substrate work needed to make the loop healthy. That belongs with loop uptime
maintenance until the class graduates into an automated watch or repair layer.

It fits harness and coordination because the queue's meaning must be visible
through shared artifacts. Private chat memory is not enough; the reconciled
state needs to be readable from GitHub labels, `STATUS.md`, watch output, or a
daemon wiki page.

## 8. Open Questions

1. What exact watch threshold should distinguish harmless out-of-order work
   from a semantic mismatch? Recommendation: start with explicit
   `priority:loop-discipline` metadata plus at least one older pending item in
   the same class.

2. Should the semantic class be inferred from labels only, or from labels plus
   issue comments? Recommendation: labels for v1 routing, comments for
   evidence. Free-text inference can follow later if test fixtures prove it is
   reliable.

3. Where should durable reconciliation records live? Recommendation: GitHub
   comments or watch artifacts first. Promote to `STATUS.md` only when a human
   or provider needs to claim work across files.

## References

- `PLAN.md` Scoping Rules
- `PLAN.md` Harness And Coordination
- `PLAN.md` Uptime And Alarm Path
- `.agents/skills/loop-uptime-maintenance/incidents/2026-05-05-auto-fix-head-of-line-retry.md`
