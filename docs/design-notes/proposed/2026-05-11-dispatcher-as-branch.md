---
title: Dispatcher As Branch
date: 2026-05-11
author: codex-wiki-design
status: proposed
request_id: WIKI-PATCH
github_issue: 804
wiki_source: pages/patch-requests/pr-112-pr-112-dispatcher-should-be-a-user-redesignable-branch-dispa.md
scope: design-only; no runtime code in this branch
builds_on:
  - PLAN.md#scoping-rules
  - PLAN.md#daemon-driven
  - PLAN.md#work-targets-and-review-gates
  - PLAN.md#community-evolvable-optimization
  - PLAN.md#multi-user-evolutionary-design
  - workflow/dispatcher.py
---

# Dispatcher As Branch

## Classification

PR-112 is a project-design request, not a bug fix. It asks whether the
dispatcher should become a user-redesignable Branch instead of a hardcoded
platform policy. This branch therefore records the design direction only and
does not change runtime dispatcher behavior.

The referenced wiki page was not present in this checkout at
`pages/patch-requests/pr-112-pr-112-dispatcher-should-be-a-user-redesignable-branch-dispa.md`;
this note is based on the issue title/body plus current `PLAN.md` and
dispatcher code.

## Recommendation

Accept the direction, but split it into two layers:

1. Keep a tiny platform-owned dispatcher kernel in `workflow/dispatcher.py`.
2. Let users and daemons redesign the policy layer as normal Branch content.

The kernel owns invariants that are not community policy:

- reading the durable `BranchTask` queue;
- honoring task status, leases, cancellations, and file locks;
- enforcing tier enablement and host safety gates;
- applying deterministic fallback when no policy Branch is available;
- recording traceable pickup evidence.

The policy Branch owns redesignable judgment:

- candidate ranking and tie-breaks;
- goal affinity;
- requester or bounty preference;
- workload balance;
- model/provider preference;
- local daemon "soul" preferences;
- explanation of why a task was picked or skipped.

This keeps dispatcher intelligence community-evolvable without making the
queue substrate depend on arbitrary user code for its safety properties.

## Shape

Introduce, in a later implementation branch, an optional dispatcher-policy
Branch whose input is a bounded candidate set and whose output is a typed
selection decision.

Conceptual input:

```yaml
daemon_id: local-daemon
now: 2026-05-11T00:00:00Z
config:
  accepted_tiers: [host_request, owner_queued, user_request]
  served_llm_type: claude-sonnet
candidates:
  - branch_task_id: bt-1
    trigger_source: user_request
    request_type: patch
    queued_at: 2026-05-11T00:00:00Z
    priority_weight: 0
    bid: 0
    goal_id: workflow-uptime
```

Conceptual output:

```yaml
selected_branch_task_id: bt-1
confidence: 0.82
reason: Highest aligned eligible patch request; no higher-tier pending task.
rejected:
  - branch_task_id: bt-2
    reason: Requires unavailable LLM type.
```

The kernel validates the output before acting. If the Branch returns an
ineligible, missing, cancelled, or already-claimed task, the kernel rejects the
decision, logs the reason, and falls back to the existing deterministic scoring
path for that cycle.

## Scoping Rules

This should not become a new top-level MCP action such as
`redesign_dispatcher`. The existing Branch design and patch primitives are the
right authoring surface. A user should be able to fork or patch the
dispatcher-policy Branch the same way they patch any other workflow.

This also should not replace the current dispatcher in one step. The first
implementation should be opt-in per universe or daemon, default off, with the
current scoring path preserved as the fallback. That matches the minimal
primitive rule: make dispatcher policy branch-authored, but do not add a new
primitive when Branch authoring already exists.

## Acceptance Criteria For A Future Runtime Patch

A runtime implementation is ready only when it proves all of these:

- With no dispatcher-policy Branch configured, current dispatcher selection is
  unchanged.
- A configured policy Branch can choose among eligible pending tasks.
- The kernel rejects policy output that selects a disabled tier, a non-pending
  task, a cancelled task, or a task requiring an unavailable LLM type.
- Policy Branch failure, timeout, invalid output, or compile failure falls back
  to deterministic scoring for that cycle.
- The pickup trace records whether the decision came from the policy Branch or
  fallback scoring.
- The policy Branch cannot mutate the queue directly; only the kernel claims
  or marks tasks.
- Tests cover the existing deterministic path, the branch-policy path, and all
  fallback cases.

## Non-Goals

- Rewriting community-authored task Branches.
- Adding new MCP primitives or tool names.
- Moving queue locking, lease transitions, cancellation handling, or
  tier-enable gates into user-authored Branch code.
- Changing `workflow/dispatcher.py` in this design-only branch.

## Verification

This note is documentation-only:

- no Python files are touched;
- no runtime tests are required;
- no plugin mirror rebuild is required.
