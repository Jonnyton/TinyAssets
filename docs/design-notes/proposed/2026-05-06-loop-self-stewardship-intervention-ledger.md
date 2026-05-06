# Loop Self-Stewardship Intervention Ledger

Status: proposed
Date: 2026-05-06
Request: WIKI-DESIGN / Issue #488
Source wiki path: `pages/patch-requests/pr-051-loop-self-stewardship-intervention-ledger-structured-trainin.md`
Related: `.agents/cheat-log.md`, `docs/design-notes/2026-05-04-operating-model-and-four-agent-topology.md`, `docs/specs/2026-05-04-loop-autonomy-roadmap.md`

## Classification

Project design. The request asks for an architectural substrate so operator
critiques become durable loop learning. It does not ask for runtime code in
this slice.

## Problem

Manual operator interventions are currently useful but too lossy. A reviewer
may correct merge order, refuse a checker key, point out stale branch drift,
clean a PR body, redirect duplicate work, or manually bridge a loop-created
branch into a PR. Today those actions may appear in chat, PR comments,
activity logs, `.agents/cheat-log.md`, or incident notes, but they do not yet
form one typed substrate that the loop can query, measure, and convert into
self-correction work.

The target is not "never let humans critique." Critique remains part of the
system. The target is that repeated critique classes stop requiring operator
labor because the loop learns to catch the same failure before review.

## Existing Substrate

`.agents/cheat-log.md` is already an append-only intervention discipline
ledger. It records justification, what happened, the substrate gap that forced
the intervention, primitive left behind, retire condition, and whether the
strictly-faster-than-alternative bar was met.

The 2026-05-04 operating-model note already names cheat-rate as a project
success metric and treats the ledger as coordination discipline. The autonomy
roadmap already defines PR creation, keyed merge, observation, rollback, and
empty-queue self-seeking as the surrounding loop mechanics.

This proposal does not replace those surfaces. It refines them into a
countable, training-data-shaped layer that can feed future loop behavior.

## Design Goal

Turn every manual intervention into a structured event with enough context to
answer four questions:

1. What failure pattern did the operator catch?
2. What evidence would have let the loop catch it first?
3. What automatic response should the loop try next time?
4. Did later loop behavior prove that the intervention class is retired?

The long-run metric is `self_correction_rate`: among recurring intervention
classes, the percentage where the loop detects and resolves the issue before a
human or operator must intervene. "100%" is the directional stewardship goal;
claims of reaching it require class-by-class evidence, not aggregate optimism.

## Event Shape

The first structured form can be derived from `.agents/cheat-log.md` without
changing runtime code. A later implementation may store this as JSONL, SQLite,
or a daemon wiki page, but the fields should stay stable:

```yaml
schema_version: 1
intervention_id: "intv_YYYYMMDD_slug"
observed_at: "2026-05-06T00:00:00Z"
actor_family: "codex|claude|cowork|cursor|host|user|unknown"
surface: "pr_comment|github_review|activity_log|cheat_log|status|chat|incident"
request_ref: "issue-or-pr-or-commit-or-wiki-page"
intervention_class: "scope_drift|merge_order|checker_refusal|duplicate_lane|stale_branch|test_gap|prompt_gap|runtime_outage|process_slip|other"
severity: "p0|p1|p2|p3"
manual_action: "what the operator did"
critique: "what the operator saw that the loop missed"
missed_evidence:
  - "artifact, log, diff, test, or policy that already contained the signal"
desired_loop_behavior: "detect|revise|reorder|decline|supersede|ask|rollback|open_followup"
substrate_gap: "smallest missing primitive or policy"
retire_condition: "observable condition that makes this class no longer need manual handling"
privacy_scope: "public_commons|repo_internal|host_local|redacted"
self_correction_candidate: true
followup_ref: "optional STATUS row, issue, design note, PR, or none"
```

## Intervention Classes

Initial class taxonomy:

- `scope_drift`: branch, PR, or generated mirror contains unrelated changes.
- `merge_order`: work lands or requests review before dependencies are ready.
- `checker_refusal`: opposite-family checker refuses approval for a reason the
  loop should have known before asking.
- `duplicate_lane`: two lanes solve the same problem without a declared split.
- `stale_branch`: candidate is based on old main or lacks scope proof.
- `test_gap`: missing focused test, lint, diff check, or user-surface proof.
- `prompt_gap`: loop prompt or release gate asks for stale, misleading, or
  incomplete behavior.
- `runtime_outage`: dispatcher, provider, queue, or watcher cannot process
  new work.
- `process_slip`: agent or operator used an unsafe workflow even though the
  substrate existed.

The taxonomy should stay small. New classes require evidence that existing
classes cannot describe the failure without losing useful routing behavior.

## Privacy And Commons Boundary

Intervention events may contain critiques of private user work, provider
tokens, paid-market terms, or host-local runtime details. The ledger must be
public-by-default only for public commons work. Private or sensitive
interventions use redacted summaries with evidence pointers that remain
host-local.

Reusable learning should be extracted as a public pattern only after removing
private payloads. For example, "scope drift caused by generated mirror churn"
is public substrate learning; a user's private branch contents are not.

## Promotion Rules

An intervention event can become loop learning in three stages:

1. **Record:** log the event with the structured fields above.
2. **Cluster:** group repeated events by `intervention_class`, `substrate_gap`,
   and `desired_loop_behavior`.
3. **Promote:** when a cluster has repeated evidence or high severity, create
   the smallest substrate follow-up: a prompt fix, release-gate check,
   branch-scope validator, test fixture, wiki guidance page, or runtime
   primitive.

Promotion must obey the PLAN scoping rules. If the loop can solve the class
with existing primitives plus a wiki pattern, do not add a platform action. If
the failure is structurally impossible to catch without new substrate, propose
the smallest primitive and require opposite-family review before
implementation.

## Metrics

Minimum metrics:

- `intervention_count_by_day`
- `intervention_count_by_class`
- `repeat_class_count`
- `median_time_to_followup_ref`
- `retired_class_count`
- `self_correction_rate`

`self_correction_rate` is computed only over classes with at least one prior
recorded intervention and a declared retire condition:

```text
self_correction_rate =
  recurring_classes_caught_by_loop_before_manual_intervention /
  recurring_classes_observed_again
```

This avoids pretending that one clean day proves the loop is self-correcting.

## First Useful Slice

The minimal project change is documentation-only:

1. Keep `.agents/cheat-log.md` as the narrative append-only ledger.
2. Add the typed event shape and promotion rules in this proposed note.
3. During future cheat-log updates, writers should be able to map each entry to
   the event fields without changing runtime code.
4. After several entries have been mapped, decide whether to add a generated
   `.agents/intervention-ledger.jsonl` mirror or a daemon-wiki page.

No new MCP action is proposed in this slice. A future action is justified only
if manual or chatbot-composed recording proves too fragile.

## Acceptance For This Design Slice

- The request is classified as project design.
- Existing `.agents/cheat-log.md` and loop-autonomy roadmap are treated as
  substrate, not replaced.
- The note defines event fields, intervention classes, privacy boundary,
  promotion rules, and self-correction metrics.
- Runtime code remains unchanged.
- Future implementation is gated on repeated evidence and opposite-family
  review.

