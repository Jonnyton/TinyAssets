---
title: Wiki Plan To Repo Design Note Source Gate
date: 2026-05-10
author: codex-wiki-design
status: proposed
request_id: WIKI-DESIGN
github_issue: 754
wiki_source: pages/patch-requests/pr-097-pr-096-supersedes-wiki-plan-to-repo-design-note-double-write.md
scope: design-only; no runtime code in this branch
builds_on:
  - PLAN.md#scoping-rules
  - PLAN.md#api-and-mcp-interface
  - PLAN.md#state-and-artifacts
  - PLAN.md#work-targets-and-review-gates
  - workflow/api/wiki.py
  - workflow/bug_investigation.py
---

# Wiki Plan To Repo Design Note Source Gate

## 1. Classification

Issue #754 is a project-design request. The failure is bug-shaped because it
creates duplicate work, but the filing explicitly asks for architectural
guidance before implementation: a wiki-authored design page becomes a repo
design note twice, first as the intended source page and then again through
`file_bug kind=design`.

This note defines the minimal source-side contract for a later runtime change.
It does not change runtime code.

## 2. Current Evidence

Local source evidence on 2026-05-10:

- The public `wiki` tool docstring tells chatbots to call `file_bug` directly
  for bugs, patch requests, feature requests, and design proposals.
- `workflow/api/wiki.py:_wiki_file_bug` accepts
  `kind in {bug, feature, design, patch_request}` and routes each kind to its
  own wiki directory.
- `_wiki_file_bug` always creates a trigger receipt and then calls
  `workflow.bug_investigation._maybe_enqueue_investigation`.
- `_maybe_enqueue_investigation` enqueues a canonical investigation whenever
  `WORKFLOW_BUG_INVESTIGATION_BRANCH_DEF_ID` is configured, regardless of
  whether the filing is a bug, design proposal, feature request, or patch
  request.

Those pieces make the reported double-write plausible. A chatbot can first use
`wiki action=write` or `promote` to create a durable design page, then follow
the tool guidance and call `file_bug kind=design`. The second call creates a
new triage request and can cause a writer to produce a duplicate repo design
note from the already-written wiki source.

## 3. Problem

The system currently treats two different user intents as the same thing:

1. "Create or update this wiki design page."
2. "File a new work request that needs navigator triage and writer output."

For bugs, conflating filing and enqueueing is acceptable because a bug filing
is usually a request for investigation. For design pages and patch requests,
the page itself can already be the source artifact. Filing another
`kind=design` request after the page exists is often not an escalation; it is a
duplicate pointer to the same artifact.

The source of truth should be the wiki page. Repo design notes are derived
artifacts or reviewed foldbacks, not parallel source records with independent
identity.

## 4. Recommendation

Implement a three-layer idempotency contract over the existing wiki primitive.
Do not add a new MCP action.

Layer 1: chatbot prompt and tool-description guidance.

The `wiki` tool guidance should distinguish creating a source page from filing
a work request:

- If the chatbot has already written or promoted the requested design,
  patch-request, or project-plan page, it should return that page path and stop.
- It should not follow a successful `wiki action=write`, `patch`, `promote`,
  or `supersede` with `file_bug kind=design` or `kind=patch_request` unless the
  user explicitly asks to file a separate work request.
- If the user asks for implementation after the page exists, the chatbot should
  cite the existing wiki page as the source instead of minting another design
  filing.

Layer 2: wiki API gate.

`file_bug` should gain an additive source-page guard for non-bug kinds. The
smallest compatible shape is an optional `source_page` string accepted by the
existing `file_bug` action. When `kind in {design, patch_request}` and
`source_page` points to an existing wiki page, the API should not mint a new
request by default. It should return a structured idempotent response such as:

```json
{
  "status": "source_already_exists",
  "kind": "design",
  "source_page": "pages/patch-requests/pr-097-...",
  "hint": "Use the existing wiki page as the design source; set force_new=true only for a materially separate request."
}
```

If `force_new=true`, the API may still create a distinct filing, but the
response and page frontmatter should preserve `source_page` so downstream
writers can see the relationship.

The guard should also protect the common no-`source_page` path by checking for
an explicit wiki path in `observed`, `expected`, `repro`, or `workaround` for
`kind in {design, patch_request}`. That heuristic is a backstop, not the
primary contract; callers should pass `source_page` once the parameter exists.

Layer 3: writer backstop.

The investigation/writer pipeline should treat wiki-sourced design filings as
idempotent. Before generating a repo design note for `kind in {design,
patch_request}`, the writer should inspect the filing frontmatter and body for
`source_page` or a `pages/.../*.md` wiki path. If that source has already
produced a repo design note, the writer should update or reference the existing
note rather than creating a sibling duplicate. If no repo note exists, the
writer may create one and include the wiki source path in frontmatter.

This writer check is not the main fix. It is the safety net for older chatbots,
third-party MCP hosts with stale tool metadata, and manually filed duplicates.

## 5. Minimal Implementation Path

The later code change should stay narrow:

1. Update the `wiki` tool docstring and any prompt-facing metadata that tells
   chatbots when to call `file_bug`.
2. Add optional `source_page` plumbing to `wiki(...)` and `_wiki_file_bug(...)`
   without changing existing callers.
3. Add the non-bug source-page guard before ID allocation and before trigger
   receipt creation.
4. Preserve `source_page` in frontmatter when a forced distinct filing is
   allowed.
5. Add a writer-side duplicate check before creating
   `docs/design-notes/proposed/*.md` from a wiki-sourced design or patch
   request.

No new MCP tool, action, queue, scheduler behavior, or separate "design note"
primitive is needed.

## 6. Acceptance Checks

A runtime implementation should include focused tests for:

1. A successful `wiki action=write` or existing wiki page followed by
   `file_bug kind=design source_page=<same page>` returns
   `status="source_already_exists"` and does not enqueue investigation.
2. `file_bug kind=patch_request source_page=<same page>` has the same
   idempotent behavior.
3. `force_new=true` still allows a separate filing and stores `source_page` in
   the generated page frontmatter.
4. The prompt/tool guidance contains the rule that writing a design page is not
   followed by `file_bug kind=design` unless the user explicitly asks for a
   separate work request.
5. The writer backstop refuses to create a second repo design note when an
   existing proposed note already cites the same `wiki_source`.

For touched Python files, run `python -m ruff check` on those files and the
focused wiki/writer tests. If canonical `workflow/*` runtime files are touched,
run `python packaging/claude-plugin/build_plugin.py` and leave mirror changes
in the working tree.

## 7. Fit With PLAN.md

This follows the minimal-primitives rule because it hardens the existing
`wiki` primitive instead of adding another MCP action.

It follows the API and MCP interface rule because the chatbot remains a
control station, not the author of a parallel source artifact. The interface
should make the right path obvious: use the wiki page as the durable source,
then let daemon/writer machinery derive repo artifacts from that source once.

It follows State And Artifacts because a design proposal needs one durable
source identity. Duplicate repo notes make the artifact graph look richer while
actually lowering trust.

It follows Work Targets And Review Gates because a wiki design page can be a
work target only after triage or explicit escalation. Writing the page and
filing a second request should not silently create two work targets for the
same source.

## 8. Non-Goals

- No runtime implementation in this branch.
- No new MCP action or primitive.
- No redesign of the community change loop.
- No migration of existing wiki pages or repo design notes.
- No removal of `file_bug kind=design`; the fix is idempotency and source
  clarity, not deleting an existing contract.

## 9. Open Questions

1. Should `source_page` be accepted for `kind=feature` too?

   Recommendation: allow it in frontmatter for all kinds, but only gate by
   default for `design` and `patch_request`. Feature requests may legitimately
   be filed after a wiki concept page exists.

2. Should the guard return `source_already_exists` or reuse
   `similar_found`?

   Recommendation: use `source_already_exists`. Similarity is fuzzy title/body
   matching; source identity is exact and should be machine-readable.

3. Should `force_new=true` bypass the source-page guard?

   Recommendation: yes, but only with `source_page` preserved and with a
   response note that the caller created a distinct work request from an
   existing source.

4. Where should the writer remember source-to-note mappings?

   Recommendation: start with repo-note frontmatter `wiki_source`, because the
   proposed design-note convention already uses it. Add an index only if scan
   cost or ambiguity becomes a real problem.

## References

- Issue #754
- `PLAN.md` Scoping Rules
- `PLAN.md` API And MCP Interface
- `PLAN.md` State And Artifacts
- `PLAN.md` Work Targets And Review Gates
- `workflow/api/wiki.py:_wiki_file_bug`
- `workflow/bug_investigation.py:_maybe_enqueue_investigation`
