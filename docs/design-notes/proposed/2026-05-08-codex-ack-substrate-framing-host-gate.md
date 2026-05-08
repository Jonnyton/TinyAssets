---
title: Codex Ack Substrate Framing Host Gate
date: 2026-05-08
author: codex-wiki-design
status: proposed
request_id: WIKI-DESIGN
github_issue: 450
wiki_source: pages/notes/codex-ack-substrate-framing-host-gate-2026-05-06.md
scope: design-only; no runtime code in this branch
builds_on:
  - PLAN.md#harness-and-coordination
  - PLAN.md#uptime-and-alarm-path
  - docs/specs/2026-05-04-loop-autonomy-roadmap.md
---

# Codex Ack Substrate Framing Host Gate

## 1. Classification

Issue #450 is a project-design filing. The linked wiki page is not present in
this checkout, and the GitHub issue has no additional comments as of
2026-05-08. This note therefore records the smallest useful project change
that follows from the issue title and the current coordination context, without
inventing runtime behavior from an unavailable source page.

## 2. Locked Framing

Codex/Cowork/host intervention on loop-produced work is not the target
governance model. It is current clinical evidence about where the community
loop substrate still fails.

Manual comments such as duplicate-lane catches, stale-branch refusals,
same-family checker refusals, permission blockers, unclear release gates, and
operator reordering should be treated as training data for the loop. The
success metric is not "operators keep making better manual calls." The success
metric is that repeated manual objection classes become small substrate
improvements, and the same intervention class trends toward zero.

This matches `PLAN.md` in two places:

- Harness and Coordination: development harnesses and role coordination are
  part of the cognition stack, not clerical overhead.
- Uptime And Alarm Path: self-heal classes graduate only after witnessed
  failures have known remedies.

## 3. Narrow Host Gate

The host gate should not ask for a broad autonomy platform, a new MCP action,
or a general reviewer brain. The narrow gate is:

> Approve recording manual loop interventions as structured substrate evidence
> and using repeated evidence classes to justify small, testable loop
> substrate fixes.

Approval of this gate authorizes only the following implementation slice:

1. Add an intervention ledger artifact owned by the community loop docs or
   operations surface.
2. Define a small intervention-class vocabulary.
3. Require every loop-facing manual intervention to record one class, the
   affected issue or PR, the substrate gap, and the expected future prevention
   layer.
4. Add a lightweight summary check that reports intervention counts by class.
5. Promote a repeated class into a separate patch/design request only after it
   has evidence from more than one incident or one severe uptime incident.

Everything else remains out of scope for this gate.

## 4. Proposed Ledger Shape

The first ledger can be Markdown to keep it reviewable and GitHub-native:

```markdown
| Date | Surface | Class | Evidence | Substrate gap | Proposed prevention | Status |
|------|---------|-------|----------|---------------|---------------------|--------|
| 2026-05-05 | PR #354/#359 | duplicate-lane | Codex comment | loop did not supersede overlapping branches | pre-claim related-branch check | observed |
```

Required fields:

- `Date`: UTC date the intervention happened.
- `Surface`: issue, PR, workflow run, wiki page, or STATUS row.
- `Class`: one of the controlled classes below.
- `Evidence`: link or terse pointer to the manual intervention.
- `Substrate gap`: the system behavior that made intervention necessary.
- `Proposed prevention`: the smallest future guard, prompt, script, check, or
  workflow change that could prevent recurrence.
- `Status`: `observed`, `promoted`, `fixed`, or `retired`.

Initial classes:

- `duplicate-lane`: two active branches or PRs attempt the same work.
- `stale-branch`: a branch carries unrelated or obsolete changes that should
  have been rebuilt from main.
- `checker-family`: a same-family review or missing opposite-family checker
  blocks trust.
- `permission-substrate`: repository, workflow, or token permissions prevent
  the intended loop action.
- `release-gate-unclear`: the packet or PR cannot state what evidence would
  make it shippable.
- `priority-order`: the loop selected lower-impact work while an equal-severity
  uptime surface stayed broken.
- `host-decision-needed`: the loop correctly reached a human policy boundary.

## 5. Promotion Rule

An intervention class is promotable into substrate work only when one of these
is true:

- two or more ledger entries share the same class and prevention shape;
- one entry corresponds to a P0/P1 uptime or data-loss risk;
- a host explicitly marks the entry promotable.

Promotion creates a normal issue, proposed design note, patch request, or
STATUS work row with its own file boundary and verification gate. The ledger is
evidence, not build authority.

## 6. Non-Goals

- Do not add a chatbot-visible MCP action for intervention tracking in the
  first implementation.
- Do not let the loop reinterpret host decisions as automatically fixable.
- Do not auto-merge, auto-close, or auto-reorder branches based only on ledger
  counts.
- Do not treat operator intervention as permanent governance.
- Do not create a large taxonomy before the first ledger has real entries.

## 7. Verification For The Future Implementation

The narrow implementation should be considered complete only when:

1. A sample intervention can be recorded without touching runtime code.
2. The summary check reports counts by class and flags repeated classes.
3. At least one existing manual intervention from activity history is captured
   as a seed row.
4. The docs state that promotion from ledger evidence still requires normal
   claim, review, and opposite-family checker rules for code changes.

No public MCP/chatbot verification is required for this design-only branch,
because it changes no runtime behavior or connector surface.

## References

- GitHub issue #450
- `PLAN.md` Scoping Rules
- `PLAN.md` Harness And Coordination
- `PLAN.md` Uptime And Alarm Path
- `docs/specs/2026-05-04-loop-autonomy-roadmap.md`
