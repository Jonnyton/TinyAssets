---
title: Substrate Cheat Migration Portfolio
date: 2026-05-11
author: codex-wiki-design
status: proposed
request_id: WIKI-DESIGN
github_issue: 808
wiki_source: pages/plans/substrate-cheat-migration-portfolio.md
scope: design-only; no runtime code in this branch
builds_on:
  - PLAN.md#scoping-rules
  - PLAN.md#canonical-work-substrate-vocabulary
  - PLAN.md#multi-user-evolutionary-design
  - docs/design-notes/2026-04-18-full-platform-architecture.md#27-absorbed-surplus-from-dev-landed-artifacts
  - docs/design-notes/2026-05-04-operating-model-and-four-agent-topology.md
---

# Substrate Cheat Migration Portfolio

## Recommendation

Treat hardcoded domain/workflow pipelines as migration candidates into default
public, user-forkable Branch artifacts. Do not add new runtime primitives for
this request. The smallest useful project change is a migration portfolio that
names which hardcoded pipelines should become Branch definitions, which should
stay platform-owned, and which gates must pass before any code path is
rewired.

The desired end state is:

- User-facing workflow shapes live as Branch definitions over `Node`, `Edge`,
  `State`, `Run`, and `Trigger`.
- Existing Python/YAML hardcoded orchestration may remain as compatibility
  execution adapters until each migrated Branch has parity evidence.
- Default branches are public, discoverable, attributable, and forkable.
- Runtime safety, deployment, storage, auth, and ops pipelines remain
  platform-owned unless they describe a user-remixable work template.

## Classification

This request is a project-design filing. It is not a bug, patch, branch
refinement, feature implementation, or docs/ops runbook change.

The phrase "substrate cheat" describes the current shortcut: project authors
directly encode useful workflows in Python or hand-authored YAML before the
Workflow substrate can express, discover, fork, and evolve them as ordinary
user branches. The migration should reduce future cheats by turning stable
shortcuts into branch seeds the community can remix.

## Scope Boundary

In scope:

- Domain pipelines that represent work a user could plausibly ask a chatbot to
  build, run, fork, extend, or compare.
- Default catalog examples such as research-paper, fantasy-scene, invoice, and
  monthly-close branches.
- Hardcoded producer, evaluator, extraction, review, or routing flows when
  their shape is primarily a user workflow rather than an internal control
  plane.
- Compatibility wrappers that execute migrated branches through existing
  runtime code while parity is being proven.

Out of scope:

- CI/CD, deployment, auth, storage, moderation enforcement, secret handling,
  and incident-response pipelines as forkable defaults.
- Any automatic rewrite of community-authored branches.
- Runtime MCP tool additions or handle renames.
- Replacing safe platform invariants with editable user policy.

This follows PLAN.md's minimal-primitives rule: the migration uses existing
Branch, Node, Edge, State, Run, Trigger, `read.graph`, `write.graph`,
`run.graph`, `read.page`, and `write.page` concepts. If a hardcoded pipeline
cannot be represented with those concepts, the gap should be named separately
before implementation.

## Portfolio Shape

Each candidate should be tracked as a row in a migration portfolio before any
runtime change:

```yaml
id: substrate-cheat-migration/<slug>
source:
  kind: python|yaml|docs|prototype
  paths:
    - path/to/source.py
current_owner: platform|domain|prototype
user_workflow: true|false
recommended_target: branch|node|catalog-pattern|keep-platform-owned|retire
default_visibility: public|host-local|not-applicable
forkability:
  expected: yes|no
  rationale: short reason
parity_gate:
  existing_behavior: command, fixture, or trace
  branch_behavior: command, fixture, or trace
  acceptance: exact|semantic|manual-review
risk_gate:
  requires_opposite_family_checker: true|false
  requires_ui_test: true|false
  requires_load_test: true|false
status: candidate|designed|scaffolded|parity-proven|rewired|retired
```

The portfolio is intentionally separate from implementation. It lets a daemon
or contributor classify migration work without guessing which files are safe to
edit.

## Migration Rules

1. Inventory first. Search for Python/YAML pipelines and classify each one as
   user-workflow, catalog seed, internal platform control plane, or obsolete
   fixture.
2. Promote the workflow shape, not the implementation accident. A branch should
   express the conceptual nodes, edges, state schema, triggers, and outcome
   gates, not copy Python helper boundaries one-for-one.
3. Preserve behavior until parity is proven. Keep the old executor as an
   adapter or oracle while the Branch definition is validated.
4. Make defaults forkable, not canonical-only. A migrated default is a seed
   branch under a Goal, not the single blessed workflow for that Goal.
5. Keep private instance data out of public defaults. Publish concepts,
   schemas, rubrics, and integration patterns; keep user files, credentials,
   customer data, and private traces host-local.
6. Do not migrate platform enforcement into user-editable policy. Guardrails
   that protect auth, safety, storage, or irreversible external effects remain
   platform primitives; branches can reference them but not own them.
7. Rewire last. Only after branch validation, parity evidence, and review
   should runtime code call the Branch path by default.

## Candidate Buckets

Seed first:

- `prototype/workflow-catalog-v0/catalog/branches/*.yaml` already demonstrates
  the target artifact shape. These should be treated as seed defaults and used
  to validate branch-schema coverage.
- Domain-visible pipelines in `domains/*/phases/` and `workflow/*` that users
  experience as authoring, extraction, review, evaluation, or routing flows are
  candidates for branch representation.
- Reusable docs catalogs such as integration patterns and domain patterns can
  become branch templates or node libraries when they have enough execution
  detail.

Defer or keep platform-owned:

- Deployment, backup, incident, secret, auth, storage, and CI pipelines.
- Test-only fixture pipelines unless they prove a missing branch capability.
- Compatibility code that exists solely to bridge old storage or client
  surfaces.

Retire:

- Hardcoded stubs with no caller, no current user surface, and no useful branch
  concept.

## Gate Ladder

Design-only branch:

- A proposed design note exists.
- No runtime code changes are made.
- The note identifies out-of-scope safety and ops pipelines.

Portfolio branch:

- Candidate rows exist with source paths, target type, and risk gate.
- A checker can reject rows that mark internal platform control planes as
  public user-forkable defaults without rationale.

Branch-scaffold branch:

- A Branch definition validates against the catalog schema.
- It declares nodes, edges, state schema, entry point, tags, domain, and
  privacy posture.
- It binds to a Goal when the Goal model is available; until then, the intended
  Goal is recorded in metadata.

Parity branch:

- Existing implementation and Branch execution are compared with focused
  fixtures or traces.
- Differences are either accepted as intentional design changes or fixed before
  default routing moves.

Runtime rewire branch:

- Code-change writers are Claude/Codex only.
- An opposite-family checker reviews the diff and evidence.
- Public MCP/chatbot-visible behavior gets rendered chatbot verification via
  the live connector when applicable.
- Uptime-track rewires include the required concurrency/load proof before they
  are considered done.

## Open Questions

1. Where should the portfolio live after this proposal: a docs table, a wiki
   page, or a generated report from source scanning? Recommendation: start as a
   docs table or wiki page; generate later only after fields stabilize.
2. What is the first candidate for parity migration? Recommendation: use an
   already-public catalog seed before touching a live runtime path.
3. How should default branches bind to Goals before the Goal schema lands?
   Recommendation: record `intended_goal` metadata and migrate to a real
   `goal_id` later.

## Verification

This proposal is documentation-only:

- No Python files are touched.
- No runtime tests or plugin rebuild are required.
- Review should verify that the design narrows the request to user-forkable
  workflow/domain pipelines and does not imply that ops or safety control
  planes become community-editable branches.
