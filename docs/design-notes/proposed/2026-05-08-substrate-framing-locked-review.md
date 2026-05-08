---
title: Substrate Framing Locked Review
date: 2026-05-08
author: codex-wiki-design
status: proposed
request_id: WIKI-DESIGN
github_issue: 451
wiki_source: pages/notes/pages-notes-cowork-codex-substrate-framing-locked-review-request-2026-05-06.md
scope: design-only; no runtime code in this branch
source_availability: wiki source path was not present in this checkout; review is based on issue title/body plus existing design notes
builds_on:
  - PLAN.md#scoping-rules
  - PLAN.md#api-and-mcp-interface
  - docs/design-notes/2026-04-26-minimal-primitive-set-proposal.md
  - docs/design-notes/2026-04-27-discovery-similarity-remix-substrate.md
---

# Substrate Framing Locked Review

## 1. Classification

This is a project-design request. The smallest useful project change is a
design review note, not runtime implementation.

Issue #451 asks for Codex review of a locked substrate framing: six
primitives, five MCP handles, and a host approval gate. The referenced wiki
page was not available at the synced path in this checkout, so this note
reviews the filing against the current PLAN and the two existing primitive
surface design notes.

## 2. Review Verdict

Conditionally approve the framing, with one required clarification before
implementation dispatch:

**The six primitives are the stable product concepts. The five MCP handles are
an exposure strategy, not permission to erase one primitive.**

The six primitives that already fit PLAN.md's scoping rules are:

| Primitive | Product job |
|---|---|
| `workspace` | Own-state orientation and workspace creation/inspection |
| `workflow` | Workflow design, patching, forking, and versioning |
| `run` | Execution, observation, continuation, and output delivery |
| `evaluate` | User-callable evaluation and gate execution |
| `commons` | Publish, fork, attribute, wiki, goals, and other write-side shared work |
| `discover` | Search, similarity, ranking, recommendation, and explainability over the commons |

`host` and `upload` remain local-app additions, not browser-only baseline
primitives. They should not count against the browser-first MCP handle budget.

The five-handle claim is acceptable only if it means one of these two shapes:

1. `discover` is first-class as a product primitive, but exposed primarily
   through MCP resources/prompts or a richer catalog surface instead of a
   separate callable tool handle in the first migration.
2. `discover` is temporarily folded into `commons` as an implementation phase,
   with a dated migration gate that splits it once search/similarity/ranking
   would otherwise bloat `commons`.

If the five-handle claim means "`discover` is not a first-class primitive,"
then it conflicts with `docs/design-notes/2026-04-27-discovery-similarity-remix-substrate.md`.
That note makes discovery the read-side infrastructure that lets
community-built designs replace platform-built features. Without that
primitive, commons-first architecture loses its retrieval path.

## 3. Why The Split Matters

PLAN.md's minimal-primitives rule says conveniences do not ship, but
irreducible structural gaps do. Discovery is not a convenience over publishing.
It is the substrate that lets a chatbot find, compare, explain, and remix prior
community work before inventing a new workflow.

Keeping `discover` conceptually separate also protects the API contract:

- `commons` answers "how do I publish, fork, attribute, or write shared state?"
- `discover` answers "what existing public work should I inspect or reuse?"

Those are different user intents, different ranking semantics, and different
future render paths. Combining them permanently would make the tool name
smaller while making the action menu larger and less predictable.

The five-handle strategy can still be correct if it uses MCP capabilities as
the exposure layer: tool handles for mutation and execution, resources for
browseable catalog records, prompts for reusable starting points, and richer
web catalog pages for inspection. That keeps the product primitive count honest
without forcing every primitive to appear as a separate top-level callable tool.

## 4. Host Approval Gate

The host approval gate should approve the product contract before any runtime
rename or consolidation work starts. It should answer these questions
explicitly:

| Question | Recommended answer |
|---|---|
| Are the six browser-first primitives accepted as product concepts? | Yes: `workspace`, `workflow`, `run`, `evaluate`, `commons`, `discover`. |
| Are `host` and `upload` outside the browser-first count? | Yes: local-app additions only. |
| Does five MCP handles mean five product primitives? | No. Handle count is exposure mechanics, not architecture. |
| Is `discover` allowed to launch through resources/prompts/catalog instead of a top-level tool? | Yes, if the contract stays first-class and the split gate is dated. |
| Can runtime code work start from this note alone? | No. Host approval plus an execution plan is required first. |

The approval record should avoid naming a final implementation handle map
unless the migration plan has already checked current FastMCP support on the
target hosts. MCP resources and prompts are roadmap-dependent across clients;
the product contract should be stable even when a host has to expose the same
primitive through a different transport shape.

## 5. Non-Goals

- No runtime tool rename in this branch.
- No removal of current `universe`, `extensions`, `goals`, `wiki`,
  `get_status`, `gates`, or `branch_design_guide` surfaces from this branch.
- No new MCP action proposed here.
- No attempt to redesign a community-authored branch from the missing wiki
  source.

## 6. Implementation Gate For A Future Branch

A future implementation branch should start with a short execution plan that
maps old public surfaces to the approved concepts and lists deprecation
behavior. Minimum checks before runtime work:

1. Contract matrix: current surface -> target primitive -> temporary handle or
   resource path.
2. Client matrix: Claude.ai, ChatGPT Developer Mode, and local-app behavior for
   each exposed handle/resource/prompt.
3. Backward-compatibility plan for current user-visible tools.
4. Focused tests for tool metadata, prompt/resource registration where
   supported, and chatbot-surface verification through the live connector after
   any public MCP behavior changes.

Until that exists, this request should remain design-only.
