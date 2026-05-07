---
title: Acceptance Scenario Packs For Life Admin
date: 2026-05-07
author: codex-wiki-design
status: proposed
request_id: WIKI-DESIGN
github_issue: 584
wiki_source: pages/patch-requests/pr-073-pr-073-acceptance-scenario-packs-as-substrate-primitive-test.md
scope: design-only; no runtime code in this branch
builds_on:
  - PLAN.md#evaluation
  - PLAN.md#scoping-rules
  - docs/ops/acceptance-probe-catalog.md
  - workflow/evaluation/__init__.py
---

# Acceptance Scenario Packs For Life Admin

## 1. Recommendation Summary

Accept PR-073 as a design direction, but define Acceptance Scenario Packs as a
Workflow-native manifest format, not a new MCP action and not a vendored
external benchmark harness.

An Acceptance Scenario Pack is a reusable long-horizon evaluation bundle. It
declares personas, starting state, prompts or task episodes, required tool/API
or browser evidence, rubric checks, artifact expectations, and the way those
checks collapse into `EvalResult` evidence. Packs are substrate because many
domains can reuse the same shape, but the first life-admin pack should be
community-authored content over existing primitives.

This matches the accepted `PLAN.md` direction for Acceptance Scenario Packs:
combine user simulation, rubric checks, MCP/API or browser evidence, and
artifact capture into `EvalResult` evidence. The design deliberately keeps the
engine primitive small. The primitive is the pack contract plus runner
adapter, not a growing set of life-admin-specific tools.

## 2. Classification

Request type: project design.

Smallest useful change: add this proposed design note so future
implementation work has a narrow contract, clear non-goals, and a concrete
life-admin seed pack shape. No runtime code change is appropriate in this
branch because the issue filing is architectural and does not explicitly ask
for implementation.

## 3. Pack Contract

Recommended v1 manifest shape:

```yaml
pack_id: life-admin-v0
version: 0
domain: life_admin
status: proposed
owner: community
privacy_profile: synthetic_or_user_supplied_redacted
episodes:
  - id: invoice-triage
    persona: busy-household-admin
    entrypoint: rendered_chatbot
    prompt_ref: prompts/invoice-triage.md
    starting_state_ref: fixtures/invoice-triage-state.yaml
    required_evidence:
      - kind: mcp_tool_call
        tool_or_action: workflow_status_or_domain_action
      - kind: artifact
        path_pattern: output/**/triage-summary.*
      - kind: rendered_chatbot_response
        criteria: no_platform_vocab_leak
    rubrics:
      - id: task_completion
        evaluator_kind: structural
      - id: user_language_fit
        evaluator_kind: editorial
      - id: evidence_grounding
        evaluator_kind: process
    result_mapping:
      verdict_rule: all_required_evidence_and_no_blocking_rubric_failures
      score_rule: weighted_rubric_average
```

The manifest should stay declarative. Runners may be local pytest, CI,
scheduled canary, user-sim, or rendered chatbot tests, but the pack does not
own those runners. It references existing runners by capability and records
their output as evidence.

Each episode emits one or more `EvalResult` records:

- `kind="structural"` for deterministic artifact, schema, and tool-call checks.
- `kind="process"` for trace-quality checks over tool use and grounding.
- `kind="editorial"` for human-language fit, privacy narration, or usability
  judgment.
- `kind="custom"` only when a domain-specific evaluator is unavoidable.

Pack-level status is a rollup over episode results. A v1 pack should not add
new `EvalResult` verdicts.

## 4. Life-Admin Seed Scope

The seed pack should exercise ordinary personal or household administration
work rather than a toy demo. Suitable v0 episodes:

| Episode | User job | Required proof |
|---|---|---|
| `invoice-triage` | Turn a messy invoice/payment reminder set into an action list | Grounded source summary, due dates, uncertainty flags |
| `appointment-reschedule` | Plan a reschedule message and preserve constraints | Draft message, conflict list, no unauthorized send |
| `document-chase` | Track missing paperwork across several entities | Checklist, owner/date fields, follow-up plan |
| `benefits-form-prep` | Prepare data for a government or employer form | Redaction discipline, missing-info questions |
| `subscription-audit` | Identify recurring charges and cancellation candidates | Evidence table, no unsupported savings claims |
| `household-project` | Break a multi-step repair/admin task into delegated steps | Milestones, dependencies, external-call cautions |

These are synthetic-first scenarios. Real user files may be used only when the
pack declares privacy handling and artifact retention rules up front.

## 5. Composition From Existing Pieces

PR-073's title says the life-admin suite "composes from existing 6+5." I could
not find a checked-in canonical artifact named `6+5` or a PR-073 wiki page in
this checkout. Treat that phrase as a composition constraint, not as permission
to invent hidden requirements.

Recommended interpretation until the wiki source is available:

- The "6" should map to concrete life-admin episodes or public uptime surfaces
  that the pack covers.
- The "5" should map to the five `PLAN.md` scoping rules, used as design
  checks before any implementation: minimal primitives, community-build over
  platform-build, privacy as community composition, commons-first architecture,
  and user capability axis.

If the wiki page defines a different 6+5 set, fold that mapping into this note
before implementation. The runner contract above still holds as long as the
pack remains declarative and emits `EvalResult` evidence through existing
evaluator shapes.

## 6. Non-Goals

- No new public MCP action in v1. Existing tool calls, rendered chatbot tests,
  CI tests, and user-sim evidence are enough to run a pack.
- No vendored AgencyBench harness. Workflow can learn from long-horizon
  benchmark structure without importing its runner or ontology.
- No life-admin runtime implementation in the scenario-pack branch. The pack
  tests domain behavior; it should not smuggle domain features into the engine.
- No private-data fixture corpus checked into the repo.
- No evaluator self-modification during a candidate run. Candidate branches
  may be judged by the pack; they may not edit the locked pack they are judged
  against.

## 7. Implementation Sketch

Step 1: add a `docs/scenario-packs/life-admin-v0/` design-only seed with the
manifest, prompt files, synthetic fixture descriptions, and rubric text. This
is reviewable by community contributors before any runner exists.

Step 2: add a tiny manifest validator that checks required fields, stable
episode IDs, allowed evidence kinds, and valid `EvalResult` mapping labels.
This is a docs/data contract check, not an engine feature.

Step 3: create a runner adapter that can invoke one episode through an existing
path: pytest for structural fixtures, user-sim for local chatbot-like runs, or
`ui-test` for rendered chatbot acceptance when public MCP behavior is involved.

Step 4: teach CI to run only synthetic, deterministic episodes by default.
Rendered chatbot and real-user-file variants remain opt-in acceptance gates
with artifact retention rules.

Step 5: once the life-admin pack proves useful, allow other domains to add
packs under the same contract. Do not generalize the runner until at least two
domain packs have forced the same abstraction.

## 8. Gate Requirements

Before any implementation branch is treated as complete:

1. Opposite-family design review confirms the pack contract matches Workflow
   primitives and does not duplicate an existing action.
2. Manifest validation passes for every checked-in pack.
3. At least one synthetic episode runs locally and emits `EvalResult` evidence.
4. Any public MCP/chatbot-facing episode has rendered chatbot proof per
   `ui-test`, not only direct MCP calls.
5. Privacy handling is explicit for every fixture and artifact class.
6. Pack results include enough evidence refs for a future daemon or reviewer to
   understand why the verdict was pass, fail, skip, or error.

## 9. Open Questions

1. What exactly does PR-073's "existing 6+5" refer to in the wiki source?
   Recommendation: do not implement until the mapping is recovered or the host
   accepts the interpretation in §5.

2. Where should packs live long term: `docs/scenario-packs/`, `tests/scenario_packs/`,
   or a domain package? Recommendation: start in docs with validator coverage;
   move executable fixtures under tests only when a runner exists.

3. Should pack results become first-class run artifacts? Recommendation: yes
   eventually, but start by storing normal `EvalResult.details` evidence refs
   and artifact paths.

4. Should real user life-admin data be supported in v0? Recommendation: no.
   Use synthetic fixtures first; add user-supplied private fixtures only after
   retention, redaction, and access-control policy is explicit.

## References

- `PLAN.md` Evaluation
- `PLAN.md` Scoping Rules
- `docs/ops/acceptance-probe-catalog.md`
- `workflow/evaluation/__init__.py`
