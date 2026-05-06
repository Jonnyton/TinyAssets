---
title: Escalation Replay On Substrate Fix
date: 2026-05-06
author: codex-wiki-design
status: proposed
request_id: WIKI-DESIGN
github_issue: 518
wiki_source: pages/patch-requests/pr-053-pr-053-escalation-replay-on-substrate-fix-primitive-auto-cle.md
scope: design-only; no runtime code in this branch
builds_on:
  - docs/ops/auto-fix-runbook.md
  - docs/exec-plans/active/2026-04-30-live-community-reiteration-loop.md
  - PLAN.md#uptime-and-alarm-path
---

# Escalation Replay On Substrate Fix

## 1. Recommendation Summary

Add a small operational primitive for the community loop: when a substrate fix
lands, the loop can replay only the old terminal handoffs whose recorded
root-cause class is now known to be fixed. The primitive should not expose a
new user-facing MCP action in v1. It should be an idempotent GitHub Actions
sweep, backed by a typed blocker registry, that clears stale `needs-human`
labels only immediately before redispatching the affected request.

This generalizes the narrow behavior already described in the auto-fix
runbook: old auth-missing `needs-human` requests may be retried once writer
auth becomes visible. The missing piece is a durable shape for other witnessed
substrate blockers, such as provider exhaustion recovery, workflow permission
repair, or a dispatcher/backfill fix. The design keeps the minimal-primitives
rule intact by shipping the replay substrate, not a pile of per-failure
convenience actions.

## 2. Shape

### Blocker Class Registry

Each replayable terminal handoff gets a typed blocker class. A blocker class is
not a free-text diagnosis. It is a small record that answers four questions:
what label/comment identified the blocker, what evidence proves the substrate
changed, what labels are safe to clear, and what redispatch path should run.

Proposed registry entry shape:

```yaml
id: writer-auth-visible
terminal_labels:
  - needs-human
  - auto-fix-auth-missing
substrate_fixed_when:
  kind: workflow_secret_visible
  any_of:
    - CLAUDE_CODE_OAUTH_TOKEN
    - WORKFLOW_CODEX_AUTH_JSON_B64
clear_labels:
  - needs-human
  - auto-fix-auth-missing
  - auto-fix-claude-subscription-missing
  - auto-fix-codex-subscription-missing
redispatch:
  workflow: auto-fix-bug.yml
  mode: issue_number
max_automatic_replays: 1
requires_no_labels:
  - auto-fix-reviewed
```

Field rationale:

- `id` is the stable blocker class name used in logs, comments, and tests.
- `terminal_labels` define eligibility. A plain `needs-human` label is not
  enough; it must pair with a typed blocker label or typed bot comment marker.
- `substrate_fixed_when` is a deterministic predicate checked at replay time.
  It must be machine-verifiable from workflow context, public GitHub state, or
  a known deployment artifact.
- `clear_labels` is the smallest label set removed right before redispatch.
  The sweep never clears unrelated review, safety, or human-decision labels.
- `redispatch` names the existing workflow path. V1 should reuse
  `workflow_dispatch` with `issue_number` rather than inventing a new queue.
- `max_automatic_replays` prevents churn when the substrate fix was incomplete.
- `requires_no_labels` preserves terminal outcomes that should not be retried
  by schedule, especially reviewed writer failures.

### Replay Ledger

Every automatic replay writes a comment with a machine-readable footer:

```text
Escalation replay: blocker writer-auth-visible is now fixed.
Cleared labels: needs-human, auto-fix-auth-missing.
Redispatched: auto-fix-bug.yml issue_number=518.

workflow-escalation-replay:
  blocker: writer-auth-visible
  replayed_at: 2026-05-06T00:00:00Z
  substrate_evidence: deploy-prod run 12345; HAS_CODEX_AUTH_BUNDLE=true
```

The comment is the public audit trail. A future implementation may also add a
JSON artifact, but the comment is enough for GitHub-native coordination and
for `community_loop_watch.py` to distinguish stale handoffs from replayed
ones.

### Eligibility Rules

A request is eligible only if all are true:

1. It is open and still carries `daemon-request` or a legacy auto-change label.
2. It has `needs-human` plus a typed replayable blocker signal.
3. The blocker class predicate currently evaluates true.
4. It has not exceeded that blocker class's automatic replay cap.
5. It does not carry `auto-fix-reviewed`, `auto-fix-blocked`,
   `host-decision`, or another label that means a human or checker already
   made a terminal judgment.

This avoids the dangerous interpretation of the request as "clear all old
`needs-human` labels after any fix." The primitive is replay-by-root-cause,
not label cleanup.

## 3. Tradeoffs

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Do nothing beyond current auth retry | Lowest implementation cost; no new surface | Every new substrate fix needs bespoke cleanup or leaves stale `needs-human` items | Reject; repeats the same uptime failure class |
| Clear all `needs-human` after deploy | Simple and visibly reduces red queue count | Unsafe; reopens real writer failures, host decisions, and intentionally blocked work | Reject; destroys signal integrity |
| Typed blocker registry + replay sweep | Idempotent, auditable, additive, and extends current auth behavior | Requires careful tests for each blocker class | Recommend |
| New MCP action for replay | Chatbot-visible and manually composable | Adds tool-surface weight for an operator-only maintenance path | Reject for v1; reconsider only if human operators need ad hoc replay from chat |

## 4. Implementation Sketch

Step 0: encode the registry in the auto-fix workflow or a small script used by
that workflow. Start with the classes already visible in code and docs:
`writer-auth-visible`, `workflow-push-token-visible`, and
`provider-capacity-restored` if provider exhaustion can be checked
deterministically.

Step 1: add focused workflow tests that prove each blocker class:

- selects an eligible issue with the matching labels;
- skips plain `needs-human` without a typed blocker;
- skips reviewed or blocked outcomes;
- removes only its configured labels;
- emits the replay ledger comment;
- redispatches the existing issue-number workflow path once.

Step 2: wire the sweep into the existing schedule, deploy-completion wakeup, and
manual dispatch path. It should run before pending issue discovery so replayed
items re-enter the normal queue in the same workflow run where possible.

Step 3: teach `community_loop_watch.py` to report stale replayable blockers
separately from durable human-required outcomes. The watch should stay red if a
replayable class is fixed but eligible issues remain unreplayed after one
schedule interval.

Step 4: after two or three blocker classes stabilize, consider moving the
registry out of workflow YAML and into a repository-local data file so other
daemon claimants can reuse the same root-cause vocabulary.

## 5. Composition With Sibling Work

- `docs/ops/auto-fix-runbook.md`: already documents the first special case:
  auth-missing `needs-human` requests can retry once writer auth appears. This
  proposal turns that special case into a reusable pattern.
- `docs/exec-plans/active/2026-04-30-live-community-reiteration-loop.md`:
  supports the plan's observation gap by making stale terminal handoffs
  observable as a specific loop state instead of generic queue redness.
- `PLAN.md` Uptime And Alarm Path: matches the "witnessed failure with known
  remedy" rule. Each blocker class must come from a witnessed substrate
  failure, not from speculative general recovery.
- `docs/specs/2026-05-03-dual-key-auto-ship-acceptance.md`: no conflict. The
  replay sweep redispatches work; it does not approve, merge, deploy, or satisfy
  checker keys.
- `docs/specs/2026-05-04-loop-autonomy-roadmap.md`: this is a narrow substrate
  increment toward loop self-stewardship. It reduces manual intervention
  without allowing the loop to reinterpret a human blocker as solved.

## 6. Open Questions

1. Should the first implementation live entirely inside
   `.github/workflows/auto-fix-bug.yml`, or should the registry begin as a
   Python helper with tests? Recommendation: keep v1 in the workflow if only
   one or two classes exist; move to a helper once the third class lands.

2. How should provider-capacity recovery be proven? Recommendation: do not
   implement `provider-capacity-restored` until the workflow can prove a fresh
   successful provider probe or successful writer run from the same provider
   family. Time passing is not sufficient.

3. Should `needs-human` itself eventually split into typed terminal labels?
   Recommendation: yes, but later. V1 can keep `needs-human` as the shared
   human-readable handoff and require typed companion labels for automation.

4. Should a chatbot-visible operator command exist? Recommendation: no for v1.
   The operator path can be manual `workflow_dispatch`; the public MCP surface
   should not grow for a maintenance convenience unless repeated operations
   prove humans need it from chat.

## References

- `docs/ops/auto-fix-runbook.md`
- `docs/exec-plans/active/2026-04-30-live-community-reiteration-loop.md`
- `PLAN.md` Scoping Rules
- `PLAN.md` Uptime And Alarm Path
