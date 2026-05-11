---
title: Make write.page a Checkpointable Run with Composable Policy Nodes
date: 2026-05-11
author: codex-wiki-patch
status: proposed
request_id: WIKI-PATCH
github_issue: 806
wiki_source: pages/patch-requests/pr-114-pr-114-write-page-should-be-a-checkpointable-run-with-user-c.md
scope: design-only; no runtime code in this branch
builds_on:
  - PLAN.md#work-substrate-vocabulary
  - docs/design-notes/proposed/2026-05-10-promote-work-substrate-vocabulary.md
---

# Make write.page a Checkpointable Run with Composable Policy Nodes

## Classification

This request is project design, not a mechanical runtime patch. Turning
`write.page` into a checkpointable `Run` with user-composable write-time
policy `Nodes` changes the page-write execution model, policy surface, and
recovery semantics. It should be accepted as a design direction before any
runtime code changes.

## Recommendation

Keep `write.page` as the public MCP handle, but model every non-read page
write as a `Run` over a small write graph:

1. `resolve_target`: normalize category, filename, page path, and caller
   scope.
2. `slug_policy`: derive or validate the target slug.
3. `dedupe_policy`: compare similar pages and decide create, update, or
   reject.
4. `dry_run_policy`: produce the exact planned write without mutating storage.
5. `write_artifact`: draft, patch, promote, or file the page.
6. `recovery_policy`: checkpoint enough state to retry, resume, or roll back
   after interruption.
7. `receipt_policy`: emit evidence linking inputs, policy decisions,
   checkpoint ids, and the resulting wiki path.

Hosts should be able to compose or replace policy nodes within their authority,
for example stricter slug rules for a public commons, mandatory dry-run for
new contributors, or a custom dedupe threshold for a private notebook.

## Required Invariants

- The MCP tool name remains `write.page`; this proposal does not add a new MCP
  action.
- Existing callers can keep using the current parameters while the runtime
  internally records a `Run`.
- `dry_run=True` must be a first-class policy node, not a special-case branch
  that skips evidence.
- Slugging and dedupe decisions must be visible in the run receipt so users can
  understand why a page path was chosen or rejected.
- Checkpoints must be safe to replay: repeating a completed write run should
  not silently create a duplicate page.
- Recovery must preserve user-authored content and prefer a draft artifact
  over destructive mutation when conflict state is unclear.

## Minimal Implementation Slice

The first runtime slice should avoid a broad graph rewrite:

1. Add an internal page-write run envelope around the existing
   `workflow.api.wiki.wiki(action="write" | "patch" | "file_bug")` paths.
2. Record a checkpoint before mutation with normalized target, content hash,
   policy decisions, and dry-run mode.
3. Return a compact receipt from `write.page` that includes `run_id`,
   `checkpoint_id`, `policy_nodes`, `status`, and existing path fields.
4. Add tests proving dry-run receipt shape, slug policy visibility, dedupe
   visibility for filed requests, and idempotent replay after a completed
   write.

That slice gives users observable checkpoint semantics without changing the
public tool schema or making policy-node composition user-configurable on day
one.

## Out of Scope

- Renaming `write.page` or adding another MCP handle.
- Replacing the wiki storage layout.
- Making all Workflow runs use the same graph executor in this branch.
- Changing community-authored branches or issue pages.

## Acceptance Checks

- A dry-run page write returns a receipt with a stable `run_id`,
  `checkpoint_id`, ordered `policy_nodes`, normalized target, and no file
  mutation.
- A real page write can be retried with the same checkpoint without producing a
  duplicate draft or page.
- A slug collision or dedupe hit is represented as a policy decision in the
  receipt, not as opaque prose.
- A failed write leaves enough checkpoint data for a later recovery node to
  resume or report the precise conflict.

## Verification

This branch is design-only:

- No `workflow/*` runtime files are changed.
- No plugin mirror rebuild is required.
- Runtime implementation should follow after this design is accepted or folded
  into `PLAN.md`.
