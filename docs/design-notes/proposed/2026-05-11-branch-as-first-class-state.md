---
title: Branch As First-Class State
date: 2026-05-11
author: codex-wiki-patch
status: proposed
request_id: WIKI-PATCH
github_issue: 778
wiki_source: pages/patch-requests/pr-104-branchasfirstclassprimitive-branches-themselves-must-be-expo.md
scope: design-only; no runtime code in this branch
classification: project-design
builds_on:
  - PLAN.md#scoping-rules
  - PLAN.md#cross-cutting-principles
  - PLAN.md#state-and-artifacts
  - PLAN.md#api-and-mcp-interface
  - PLAN.md#multi-user-evolutionary-design
  - docs/specs/community_branches_phase4.md
---

# Branch As First-Class State

## 1. Recommendation Summary

Treat the request as a project-design change, not a mechanical operator patch.
The useful primitive is not a new hardcoded `verdict`, `fork queue`,
`validator`, `classifier`, or `ledger` feature. The useful primitive is a
stable branch-state contract that lets a Workflow branch inspect and mutate
another branch through the same state discipline used for ordinary workflow
execution.

Do not add runtime code in this branch. The first safe step is to define the
contract boundary and implementation gates, because exposing branches as
read/write/run targets changes mutation semantics, authorization, auditability,
and collision behavior for every community-authored branch.

## 2. Classification

Issue #778 is a `project-design` filing.

The filing asks for branches themselves to be exposable as State that other
branches can read, write, run, diff, and fork. That is a meta-primitive: it
changes what a branch can operate on. It is broader than a bug fix and broader
than a single patch request, even though the filing shape is marked
mechanical.

## 3. Existing Surface

Workflow already has several branch-facing primitives:

- `get_branch`, `list_branches`, `build_branch`, `patch_branch`, and related
  branch edit actions in `workflow/api/branches.py`.
- `run_branch` and `run_branch_version` in `workflow/api/runs.py`.
- branch versions and run comparison/evaluation surfaces, including the Phase
  4 `compare_runs` design.

Those primitives let the chatbot and MCP client operate on branches. They do
not yet define a branch-as-state interface where one Workflow branch can take a
branch reference as durable input, emit branch mutations as typed output, and
compose those mutations with normal run/audit semantics.

## 4. Primitive Boundary

The proposed primitive is `BranchStateRef`: a typed state value that points at
a branch or branch version and carries enough metadata for safe composition.

Minimum v1 shape:

```yaml
branch_ref:
  branch_def_id: string
  branch_version_id: string | null
  goal_id: string | null
  capability:
    read: boolean
    write: boolean
    run: boolean
    fork: boolean
  observed_version: integer | null
  source_run_id: string | null
```

The ref is not a copy of the branch body. It is a capability-bearing pointer
that a branch can dereference through existing branch APIs. Actual writes still
go through platform-owned mutation paths so validation, audit, and conflict
checks remain centralized.

## 5. Composition Rule

Branch-related operations should be community-buildable branches by default:

- verdict branches read a `BranchStateRef`, run checks, and emit an
  attachable judgment.
- validator branches read a branch, validate shape or policy, and emit a
  report plus optional patch proposal.
- fork tools read a source branch and emit a new branch spec through the
  existing build/fork path.
- queue tools read task and branch refs, classify them, and emit scheduling
  recommendations.
- ledgers read branch mutations and runs, then emit summaries or attestations.

Platform code should only provide the irreducible read/write/run/fork/diff
capability boundary. The policies above should remain ordinary Workflow
branches that users can inspect, remix, and replace.

## 6. Non-Goals

- No hardcoded verdict, validator, queue, classifier, fork, or ledger policy.
- No new action per branch-related convenience.
- No direct arbitrary Python write access from one branch into another
  branch's persisted record.
- No bypass of branch validation, version checks, write ledgers, or future git
  history semantics.
- No redesign of community-authored branches as part of this request.

## 7. Implementation Gates

A later implementation should not start until these gates are met:

1. **Contract approval:** `PLAN.md` or an accepted spec names `BranchStateRef`
   or an equivalent type and records whether branch refs point to mutable
   heads, immutable versions, or both.
2. **Mutation semantics:** writes declare expected version and fail on stale
   heads instead of silently overwriting concurrent edits.
3. **Audit semantics:** every branch-state write maps to the same public action
   ledger or git-history invariant as direct `patch_branch`/`build_branch`
   writes.
4. **Capability semantics:** a branch can be given read-only, write, run, and
   fork capabilities separately. The default for a ref passed into an
   untrusted branch is read-only.
5. **Diff semantics:** v1 distinguishes branch-definition diffs from run-output
   diffs. A branch topology/schema diff is not the same artifact as
   `compare_runs`.
6. **Fork semantics:** fork operations preserve lineage and attribution, and
   do not collapse diverse-by-default Goals into a single canonical workflow.
7. **Chatbot UX:** the control-station prompt explains that branch-management
   features should be composed as branches unless the user is explicitly asking
   for a platform primitive.

## 8. Smallest Future Runtime Slice

The smallest runtime slice, after design approval, is not a broad rewrite. It
is a read-only `BranchStateRef` path:

1. Allow branch state schemas to declare a field with type `branch_ref`.
2. Let `run_branch` inputs accept that field as a branch ID or branch version
   ID and normalize it into the structured ref.
3. Add one read helper that resolves a ref to the same payload returned by
   `get_branch`, with capability metadata included.
4. Prove a validator branch can read another branch and emit a report without
   mutating it.

Only after that passes should write/fork/diff semantics be added.

## 9. Acceptance Criteria For This Design Note

- The request is classified as project design.
- The design identifies the missing primitive as a branch-state contract, not a
  bundle of operator-authored branch tools.
- Runtime code remains unchanged.
- Future work is gated on contract approval, auditability, version checks, and
  capability separation.
