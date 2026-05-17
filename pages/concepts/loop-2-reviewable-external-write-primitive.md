---
title: Loop 2 Reviewable External Write Primitive
type: concept
status: proposed
created: 2026-05-17
source_issue: 889
request_id: WIKI-DESIGN
wiki_source: pages/patch-requests/pr-122-external-write-primitive-needed-for-user-buildable-loop-2-to.md
tags: [loop-2, external-effects, pull-requests, user-buildable, substrate]
---

# Loop 2 Reviewable External Write Primitive

## Classification

Issue #889 is a project-design filing. It identifies a substrate capability
gap, not a bug in one branch: user-buildable Loop 2 can produce packets that
describe side effects, but it cannot request a reviewable external write such
as opening a pull request with the same parity that substrate Loop 1 can reach
through the repository automation path.

The smallest useful project change is this brain concept page. It records the
primitive boundary without adding a new runtime MCP action or drafting a
`docs/design-notes/proposed/` note by default.

## Recommendation

Add one substrate capability: a **reviewable external effect request**.

The primitive is not "write arbitrary external systems." It is a typed,
auditable request for Workflow to materialize an already-reviewed work artifact
into an external sink, under the caller's scope and confirmation policy.
Opening a GitHub pull request is the first sink because the community loop's
current readiness baseline is blocked on PR emission.

The repo already contains narrow auto-ship PR-opening material
(`open_auto_ship_pr`) for controlled canary lanes. Issue #889's missing piece
is the user-buildable Loop 2 contract that lifts "please open a PR" out of
packet prose and into durable state that such adapters can validate, resume,
reject, or execute.

This composes with the canonical substrate handles:

- `write.graph` owns the durable work artifact, run evidence, release-gate
  verdict, changed paths, rollback plan, and authority scope.
- `write.page` owns the reviewable wiki or commons record that explains the
  request, links lineage, and leaves a durable audit trail.
- The external sink adapter turns the approved artifact into a PR, records the
  PR URL/commit/status, and reports failures back as state, not prose-only
  packet output.

## Why This Is A Primitive

Packet-only side effects are not enough for user-buildable Loop 2 because a
packet can say "open a PR" but cannot itself cross the repository boundary.
That forces every user-built loop to depend on a substrate-only executor for
the last mile. The result is lower parity than Loop 1 even when the branch,
tests, evidence, and release gate are all community-buildable.

The missing capability is irreducible: a chatbot can compose branch edits,
review packets, release gates, and wiki records from existing primitives, but
it cannot safely create a repository PR without a permissioned external-effect
adapter. The platform should ship the adapter boundary, not a policy about
which loops deserve PRs.

## Contract

A reviewable external effect request should contain:

- `effect_kind`: initially `github_pull_request`.
- `source_artifact`: branch, run, ledger row, or packet identifier that already
  passed the local review gate.
- `authority_scope`: user, daemon, host, repository, and target branch.
- `changed_paths`: normalized paths, with allowlist/denylist enforcement before
  any external action.
- `evidence`: tests, lint, review verdict, and release-gate result.
- `rollback_plan`: concrete revert or close path.
- `review_record`: wiki/page link for the durable request.
- `confirmation_policy`: whether the action is dry-run, host-confirmed, or
  pre-authorized for a narrow canary class.
- `sink_result`: PR URL, failure class, external idempotency key, and final
  status once attempted.

The request is append-only and resumable. Retrying a failed PR open must use an
idempotency key derived from the source artifact and target sink so recovery
does not create duplicate PRs.

## First Sink: GitHub Pull Request

The GitHub PR sink should reuse the existing auto-ship safety envelope and the
older external-PR bridge vocabulary where they fit:

- dry-run validation stays separate from side effects;
- PR creation is feature-flagged or scope-gated;
- workflow/runtime, provider, API, dispatcher, migration, secret, auth, and
  workflow-file paths remain blocked unless a later review gate explicitly
  expands the envelope;
- PR creation failure is a structured `sink_result`, not a silent HOLD or a
  prose-only packet;
- opened PRs link back to the source request page and evidence handle.

Loop 2 parity is achieved when a user-built loop can emit this typed request,
the substrate validates it deterministically, and an approved sink adapter such
as `open_auto_ship_pr` opens or rejects the PR with structured evidence.

## Non-Goals

- Do not add a broad `external_write` MCP verb.
- Do not let branch code call GitHub directly with ambient credentials.
- Do not bypass host confirmation, repository permissions, path policy, or
  opposite-family review requirements.
- Do not redesign community-authored branches as part of this filing.
- Do not make GitHub the canonical store; it remains an export/review sink.

## Acceptance Shape

A future implementation slice is acceptable when a test can prove:

1. A Loop 2 run emits a typed `github_pull_request` request instead of only a
   packet instruction.
2. The request is persisted with source artifact, authority scope, evidence,
   rollback plan, and review page link.
3. The validator rejects forbidden paths and missing review evidence before any
   external side effect.
4. With PR creation disabled, the response is a dry-run decision containing the
   would-open PR shape.
5. With PR creation enabled in a controlled canary scope, the adapter opens one
   PR or records a structured failure, and retry is idempotent.

## References

- GitHub issue #889
- `PLAN.md` - Scoping Rules
- `PLAN.md` - Canonical Work Substrate Vocabulary
- `PLAN.md` - API And MCP Interface
- `docs/design-notes/2026-04-25-external-pr-bridge-proposal.md`
- `docs/milestones/auto-ship-canary-v0.md`
- `workflow/api/auto_ship_actions.py`
- `workflow/auto_ship.py`
