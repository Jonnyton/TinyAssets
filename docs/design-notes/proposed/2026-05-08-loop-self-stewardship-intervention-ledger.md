---
title: Loop Self-Stewardship Intervention Ledger
date: 2026-05-08
author: codex-wiki-design
status: proposed
request_id: WIKI-DESIGN
github_issue: 488
wiki_source: pages/patch-requests/pr-051-loop-self-stewardship-intervention-ledger-structured-trainin.md
scope: design-only; no runtime code in this branch
builds_on:
  - ideas/INBOX.md#loop-self-stewardship-trend-manual-checker-intervention-to-zero
  - docs/design-notes/proposed/2026-05-06-escalation-replay-on-substrate-fix.md
  - docs/exec-plans/active/2026-04-30-live-community-reiteration-loop.md
  - PLAN.md#community-evolvable-optimization
  - PLAN.md#uptime-and-alarm-path
---

# Loop Self-Stewardship Intervention Ledger

## 1. Recommendation Summary

Add a structured intervention ledger for the community loop. Every operator,
checker, or human critique that changes loop behavior should become a typed
event with enough context for the loop to learn the same correction later:
what went wrong, what evidence exposed it, what the operator changed, what the
loop should have done instead, and whether a later run self-corrected before
operator intervention.

This is a project-design substrate, not a request for immediate runtime code.
The first useful change is to standardize the ledger contract and promotion
rules so future loop work can produce comparable data instead of scattered
comments, chat notes, and ad hoc memories. The target is self-correction-rate
approaching 100% for repeated intervention classes. The ledger should measure
that rate honestly; it must not let the loop claim success by hiding, ignoring,
or relabeling critiques.

## 2. Problem

The community loop currently improves when operators notice failures and
manually steer around them: ordering mistakes, duplicate lanes, checker-key
refusals, review blockers, stale labels, missing acceptance evidence, unsafe
merge attempts, and branch notes that fail to update after reality changes.
Those interventions are valuable training data, but they are mostly untyped.

Unstructured intervention history causes three failures:

1. The same critique can reappear in later branches because no durable signal
   says "the loop should catch this class before review."
2. Operators cannot distinguish one-off judgment calls from repeated substrate
   gaps that deserve automation, prompt changes, gates, or tests.
3. The loop cannot prove its self-stewardship is improving because there is no
   denominator for intervention opportunities or numerator for pre-review
   self-corrections.

## 3. Ledger Object

Each event should be append-only and small enough to live in a repository
artifact, GitHub issue comment footer, or workflow artifact. The canonical
shape should be stable across storage backends:

```yaml
schema: workflow.intervention.v1
event_id: intervention_2026_05_08_0001
recorded_at: 2026-05-08T00:00:00Z
source:
  kind: github_comment
  uri: https://github.com/Jonnyton/Workflow/issues/488#issuecomment-...
  actor_family: operator | checker | daemon | host | user
loop_context:
  request_id: WIKI-DESIGN
  github_issue: 488
  branch: design-note-draft/issue-488-codex-2556068193
  run_id: null
  artifact_refs:
    - docs/design-notes/proposed/2026-05-08-loop-self-stewardship-intervention-ledger.md
classification:
  intervention_class: missing_acceptance_evidence
  severity: p0 | p1 | p2 | p3
  lifecycle_phase: claim | plan | build | review | foldback | monitor
  repeated: true
critique:
  observed_failure: "The branch claimed done without rendered chatbot proof."
  evidence: "Final message listed direct MCP calls only."
  operator_action: "Requested ui-test and post-fix clean-use evidence."
  expected_loop_behavior: "Detect public-surface change and require ui-test before completion."
correction_target:
  substrate: prompt | memory | script | test | gate | runbook | plan | status
  owner_surface: community_loop
  proposed_change_ref: null
verification:
  self_corrected_before_operator: false
  later_run_ref: null
  later_run_result: pending | corrected | repeated | waived
privacy:
  contains_private_user_data: false
  retention: public_repo_ok
```

The object intentionally separates `critique.observed_failure` from
`classification.intervention_class`. The observed failure is the concrete
incident; the class is the reusable learning target. This keeps the loop from
overfitting to one comment while still preserving evidence.

## 4. Intervention Classes

V1 should start with a small controlled vocabulary, then add classes only when
fresh incidents cannot fit an existing class:

| Class | Meaning | Typical Promotion |
|---|---|---|
| `claim_collision_or_missing_claim` | Work began without a clean STATUS/worktree boundary, or overlapped another active lane | claim-check prompt change, STATUS convention, pre-claim script gate |
| `wrong_work_order` | Loop picked work that bypassed a dependency, review gate, or uptime priority | scheduler rule, context-feed promotion, work-row dependency |
| `duplicate_or_superseded_lane` | Loop filed or built a branch already covered by another lane | cohit check, issue dedupe, search prompt |
| `missing_acceptance_evidence` | Completion claim lacks required test, user-surface, or post-fix clean-use evidence | checklist gate, workflow check, runbook update |
| `checker_key_refusal` | Opposite-family checker refused because requirements, evidence, or safety gates were absent | checker preflight prompt, package validator |
| `unsafe_runtime_or_public_surface_change` | Branch changed MCP/runtime/public behavior without the required proof path | ui-test gate, deploy canary, risk classifier |
| `stale_or_false_status` | STATUS/wiki/issue comment claimed a state contradicted by current code or runtime evidence | freshness-stamp rule, watch script |
| `low_quality_patch_shape` | Change was too broad, refactored unrelated code, or missed the smallest useful fix | patch-size rubric, diff review prompt |

This vocabulary should live close to the future implementation, but the design
decision is that intervention classes are platform learning targets, not
private operator notes.

## 5. Metrics

The ledger should report three rates, always over a named time window and
class set:

- `manual_intervention_rate`: interventions per loop-handled request.
- `repeat_intervention_rate`: repeated interventions per class after the first
  substrate correction was available.
- `self_correction_rate`: repeated-class opportunities where the loop detected
  and corrected the issue before an operator or checker had to intervene.

The headline target is:

```text
self_correction_rate =
  self_corrected_repeated_class_opportunities /
  all_repeated_class_opportunities
```

The rate must be computed by class. A loop that reaches 100% on
`missing_acceptance_evidence` but 0% on `wrong_work_order` has solved one class,
not self-stewardship in general. Waivers may exist for explicit host decisions,
but waived events stay in the denominator for visibility unless the class is
retired by design.

## 6. Promotion Rules

Repeated interventions should ratchet into stronger substrate changes:

1. First occurrence: write a ledger event and classify it.
2. Second occurrence in the same class: add or update a prompt, memory, runbook,
   or checklist so the loop has explicit guidance.
3. Third occurrence: add a script, test, or workflow gate when the signal is
   machine-checkable.
4. Fourth occurrence after a gate exists: treat it as a substrate outage or
   design gap; open a STATUS concern or proposed design note, depending on
   whether the failure is live-state or architecture.

This matches the project's auto-iteration discipline: recurring behavioral
failures should not stay as advice. They should move toward enforceable checks
when the signal is stable enough.

## 7. Training-Data Substrate

"Structured training data" in this proposal means a durable learning substrate
for the loop's prompts, retrieval context, checker rubrics, tests, and gates.
It does not require model fine-tuning in v1.

The safe v1 path is:

1. Capture intervention events as structured records.
2. Build summaries by class for daemon prompts and checker rubrics.
3. Convert high-confidence repeated classes into deterministic preflight checks.
4. Preserve raw events so future offline analysis can evaluate whether a
   prompt, script, or gate actually reduced repeated interventions.

Future model training, if ever approved, must use only privacy-cleared events,
must preserve provenance, and must exclude private user content unless the
privacy policy explicitly permits promotion into reusable cognition.

## 8. Composition With Existing Design

- `PLAN.md` Community Evolvable Optimization: the ledger is a typed lesson
  stream for improving the platform itself, with lineage and evaluator
  separation. It strengthens the optimization substrate rather than adding a
  parallel control plane.
- `PLAN.md` Uptime And Alarm Path: repeated manual interventions are witnessed
  failure classes. Once a class has a known remedy, it should graduate into a
  self-heal layer, gate, or watch rule.
- `docs/design-notes/proposed/2026-05-06-escalation-replay-on-substrate-fix.md`:
  escalation replay handles one stale-terminal-handoff class. The intervention
  ledger is the upstream source that decides which classes deserve similar
  treatment.
- `docs/exec-plans/active/2026-04-30-live-community-reiteration-loop.md`: the
  ledger gives the live community reiteration loop a measurable feedback
  surface for project-design, bug, patch, feature, docs/ops, and branch
  refinement filings.
- `ideas/INBOX.md`: the captured self-stewardship idea is promoted by this
  proposal. The idea should stay as historical provenance until the design is
  accepted or superseded.

## 9. Implementation Sketch

Step 0: choose the storage path. Recommendation: start with a repository-local
JSONL artifact under `output/interventions/` or a GitHub issue comment footer,
then promote to a first-class data file only after two consumers exist.

Step 1: add a small schema validator and fixture tests for the V1 object. The
validator should reject missing class, evidence, expected behavior, privacy
classification, and verification fields.

Step 2: update loop handoff/review prompts so every requested change,
checker-key refusal, or operator correction includes a compact
`workflow-intervention:` footer that can be harvested into the ledger.

Step 3: add a periodic report that groups events by class, computes the three
rates, and highlights classes that crossed the promotion threshold.

Step 4: wire high-confidence classes into concrete checks one at a time. For
example, `missing_acceptance_evidence` can become a completion preflight that
maps touched surfaces to required proof types.

Step 5: only after the ledger has stable events and at least one reporting
consumer, decide whether accepted schema and class vocabulary belong in
`PLAN.md`, a docs/spec file, or runtime-owned schema code.

## 10. Acceptance Gates For Future Implementation

Any future runtime or workflow implementation should prove:

1. It captures at least one synthetic intervention event per initial class.
2. It rejects malformed events instead of silently storing partial learning
   data.
3. It computes metrics over fixtures with repeated, corrected, repeated-again,
   and waived cases.
4. It preserves privacy classification and provenance in every exported event.
5. It does not create a new chatbot-visible MCP action unless a separate design
   note proves conversational operation is necessary.
6. It does not let the loop mark an intervention as self-corrected unless the
   correction happened before the operator/checker critique that would have
   exposed the failure.

## 11. Open Questions

1. Should ledger events be primarily GitHub-native comments or repository JSONL
   artifacts? Recommendation: comments for human-visible critiques, JSONL for
   normalized harvested data once reporting exists.

2. Who owns class vocabulary changes? Recommendation: proposed additions can be
   community-filed, but acceptance requires opposite-family review until the
   class list stabilizes.

3. When does an intervention class retire? Recommendation: after a defined
   clean-use window with no repeated interventions and with a surviving test or
   gate where machine-checkable.

4. Can a loop-authored critique count as an intervention? Recommendation: yes,
   if the loop caught and corrected its own failure before checker/operator
   intervention. Those events are the numerator for self-correction-rate.

## References

- `ideas/INBOX.md`
- `docs/design-notes/proposed/2026-05-06-escalation-replay-on-substrate-fix.md`
- `docs/exec-plans/active/2026-04-30-live-community-reiteration-loop.md`
- `PLAN.md` Community Evolvable Optimization
- `PLAN.md` Uptime And Alarm Path
