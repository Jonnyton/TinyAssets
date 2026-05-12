---
title: Before Filing a Patch Request - The User-Buildable Check
date: 2026-05-12
status: promoted
type: concept
request_id: WIKI-DOCS
issue: 824
---

# Before Filing a Patch Request - The User-Buildable Check

## Core Claim

Before filing a `patch_request`, first ask whether the user can build the
requested outcome from existing Workflow primitives, wiki guidance, remixable
branches, and a chatbot's ordinary composition ability.

If the answer is yes, the useful artifact is not a platform patch. It is the
composition path: the smallest set of existing primitives, pages, gates, and
checks a user or daemon can follow to get the outcome without changing
Workflow's runtime surface.

## Why This Check Exists

Workflow treats platform primitives as scarce. Every new runtime capability
adds maintenance cost, increases chatbot tool-selection load, and can freeze a
policy that the community could have evolved through wiki pages and remixable
workflows.

The user-buildable check keeps the patch loop from turning every helpful idea
into platform code. It also gives browser-only users and local-app users the
same first question: "What can I already do with the system I have?"

## The Check

For any candidate `patch_request`, answer these questions before filing:

1. Can the outcome be composed from existing workflow nodes, branches,
   evaluators, gates, wiki pages, or remix material?
2. Would a competent chatbot reliably explain or assemble that composition in
   a short exchange?
3. Is the missing piece a true primitive, or only a convenience wrapper around
   existing primitives?
4. Would a community-authored guide, template, or branch give future users the
   same leverage without platform code?
5. If the answer differs by user capability tier, is the gap about local-host
   access, browser-only limits, provider support, or a real platform absence?

## Outcomes

- **User-buildable:** do not file a platform patch request. Write or improve
  the wiki guide, template, branch, or checklist that makes the composition
  discoverable.
- **Mostly user-buildable, but fragile:** document the composition and file the
  narrowest request for the missing primitive or evidence surface.
- **Not user-buildable:** file a `patch_request` that names the structural gap,
  the attempted composition path, and why existing primitives cannot cover it.

## Patch Request Body Expectations

A well-scoped patch request should include:

- the user-visible outcome,
- the existing primitives or wiki pages checked,
- the composition path that was attempted or ruled out,
- the exact structural gap that remains,
- the verification gate that would prove the gap is closed.

Avoid requests whose only justification is "this would be convenient." In
Workflow, convenience starts as community documentation unless the composition
is unreliable, unavailable to an important user capability tier, or blocked by
a missing primitive.

## Related Workflow Concepts

- `PLAN.md` - Minimal primitives
- `PLAN.md` - Community-build over platform-build
- `PLAN.md` - User capability axis
- `docs/ops/wiki-bug-sync-runbook.md`
