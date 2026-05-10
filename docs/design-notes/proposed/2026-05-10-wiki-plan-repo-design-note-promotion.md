---
title: Wiki Plan To Repo Design Note Promotion
date: 2026-05-10
author: codex-wiki-design
status: proposed
request_id: WIKI-DESIGN
github_issue: 753
wiki_source: pages/patch-requests/pr-096-loop-s-wiki-plan-to-repo-design-note-auto-promote-pattern-is.md
scope: design-only; no runtime code in this branch
builds_on:
  - PLAN.md#scoping-rules
  - PLAN.md#state-and-artifacts
  - PLAN.md#work-targets-and-review-gates
  - PLAN.md#harness-and-coordination
---

# Wiki Plan To Repo Design Note Promotion

## 1. Classification

Issue #753 is a project-design request. It reports substrate debt in the
community loop's writer behavior: wiki-authored plans are being auto-promoted
into repo design notes even when the wiki page should remain the canonical
user-readable plan.

Because the filing is architectural, this branch records the design direction
only. It does not change writer runtime behavior.

## 2. Problem

The wiki is the canonical surface for user-driven plans and patch requests. It
is readable through the public Workflow wiki path and does not require project
folder access. When the loop writer automatically copies a wiki plan into
`docs/design-notes/`, the system creates two sources for the same user-authored
intent:

1. the wiki page, which remains the community-facing source;
2. a repo design note, which can drift, invite repo-only review habits, and
   make public plans look like they require project checkout access.

That duplication is substrate debt. It increases review surface without adding
new design judgment, and it weakens the distinction between community-readable
plan state and repo-maintained architectural decisions.

The reported PR canaries, PR #642, #644, #645, and #647, are treated as visible
evidence of the pattern: the loop produced repo design-note branches for
wiki-plan material where the durable source should have stayed in the wiki.
This note does not evaluate those branches individually; it uses them as the
failure class named by the filing.

## 3. Design Contract

The loop writer MUST NOT auto-generate repo design notes from wiki plans.

Repo design notes are for synthesis, decisions, tradeoff analysis, and
implementation contracts that need repository review. Wiki pages are for
user-driven plans, patch requests, community proposals, and readable public
coordination. A wiki plan may reference a repo design note, and a repo design
note may reference a wiki source, but the two are not automatic mirrors.

The promotion decision must be explicit and typed:

- `wiki_canonical`: the wiki page is the canonical plan; no repo note is
  generated.
- `repo_design_needed`: the request needs architecture synthesis or a decision
  record; create or update a design note.
- `repo_spec_needed`: the request needs an implementation contract rather than
  an architectural note; create or update a spec or exec plan instead.
- `no_repo_artifact`: the issue can be answered or closed through wiki or issue
  state alone.

The default for user-driven wiki plans is `wiki_canonical`.

## 4. Minimal Implementation Path

A later runtime change should be small and writer-scoped:

1. Find the loop writer path that turns wiki patch requests or wiki plans into
   repo design-note branches.
2. Replace unconditional design-note creation with a promotion classifier that
   emits one of the typed decisions above.
3. For `wiki_canonical`, leave the wiki page as the source and write only a
   concise issue or release-gate note explaining that no repo artifact is
   needed.
4. For `repo_design_needed`, keep the current design-note path, but require the
   writer to add original synthesis beyond copying the wiki page.
5. Add tests using the canary shape from PR #642/#644/#645/#647: wiki-plan
   filings should not create repo design-note files unless the classifier
   returns `repo_design_needed`.

This should not add a new MCP action, new public primitive, or broad scheduler
policy. It is writer triage over existing artifacts.

## 5. Acceptance Checks

A runtime implementation should prove:

1. A wiki patch request that is a user-authored plan remains wiki-canonical and
   produces no `docs/design-notes/` file.
2. A true project-design filing can still produce a proposed design note when
   architecture synthesis is needed.
3. The writer's final issue comment names the chosen artifact authority:
   wiki-only, repo design note, spec, exec plan, or no repo artifact.
4. Existing manual design-note requests still work.
5. The behavior is covered by focused tests around the writer classifier or
   coding packet generation path.

For #753 itself, this proposed note is intentionally allowed: the issue asks
for an architectural response under the daemon request contract, so the repo
note records the policy change rather than mirroring the original wiki plan.

## 6. Fit With PLAN.md

This follows the scoping rules because it removes an unnecessary platform
habit instead of adding a new primitive. The user need is not "create another
artifact"; it is "keep the right artifact authoritative."

It follows State And Artifacts because durable state must be typed. Wiki pages
and repo design notes have different authority, audiences, and decay patterns.
Conflating them makes long-horizon reasoning less legible.

It follows Work Targets And Review Gates because a target can be notes,
publishable work, a wiki plan, or a repo design artifact. Moving from one
target type to another should pass a review gate; it should not happen as a
side effect of filing shape alone.

It follows Harness And Coordination because community-visible coordination
should stay readable from shared public artifacts. Requiring repo access for a
wiki-readable plan narrows the collaboration surface and makes multi-provider
coordination harder.

## 7. Non-Goals

- No deletion or rewrite of PR #642, #644, #645, or #647.
- No migration of existing accepted design notes back into wiki pages.
- No runtime writer change in this branch.
- No new MCP action or chatbot-visible primitive.
- No redesign of community-authored branches.

## 8. Open Questions

1. Where should the promotion classifier live?

   Recommendation: closest to the loop writer's artifact-selection step, before
   any branch file is generated.

2. Should the wiki page frontmatter carry the promotion decision?

   Recommendation: only if the wiki already has a stable review-state field.
   Otherwise write the decision in the issue/release-gate comment first to
   avoid adding schema before the policy proves useful.

3. Should existing auto-generated notes be swept?

   Recommendation: do not sweep them as part of #753. Treat cleanup as a
   separate branch-refinement task only when a specific branch or PR asks for
   it.

## References

- Issue #753
- Wiki source: `pages/patch-requests/pr-096-loop-s-wiki-plan-to-repo-design-note-auto-promote-pattern-is.md`
- PR #642, PR #644, PR #645, PR #647
- `PLAN.md` Scoping Rules
- `PLAN.md` State And Artifacts
- `PLAN.md` Work Targets And Review Gates
- `PLAN.md` Harness And Coordination
