---
title: Workflow Substrate Canonical Vocabulary
date: 2026-05-08
author: codex-wiki-design
status: proposed
request_id: WIKI-DESIGN
github_issue: 449
wiki_source: pages/concepts/pages-concepts-workflow-substrate-canonical-vocabulary-6-primitives-5-mcp-handles.md
scope: design-only; no runtime code in this branch
builds_on:
  - PLAN.md#scoping-rules
  - PLAN.md#api-and-mcp-interface
  - docs/design-notes/2026-04-26-minimal-primitive-set-proposal.md
  - docs/design-notes/2026-04-27-discovery-similarity-remix-substrate.md
  - docs/design-notes/2026-05-04-operating-model-and-four-agent-topology.md
cohit_check:
  command: python scripts/check_primitive_exists.py action {discover,commons,workspace,workflow,run,evaluate}
  result: clean on refs/remotes/origin/main
---

# Workflow Substrate Canonical Vocabulary

## 1. Recommendation Summary

Adopt a two-layer vocabulary:

1. **Six product primitives** name what Workflow lets users and chatbots do:
   `workspace`, `workflow`, `run`, `evaluate`, `discover`, and `commons`.
2. **Five MCP handles** expose those primitives without expanding the public
   tool list: `workspace`, `workflow`, `run`, `evaluate`, and `commons`.

The mismatch is intentional. `discover` is an irreducible product primitive,
but it should compile into the `commons` MCP handle as a read-side action
family until action-menu size or client UX proves it needs its own top-level
tool. This preserves the minimal-primitives rule while still giving discovery
first-class vocabulary in design notes, wiki pages, chatbot reasoning, and
community conventions.

The third vocabulary layer is **brain conventions**: community-evolved wiki
pages, design patterns, rubrics, prompts, and operating norms that chatbots
discover, apply, remix, and improve. Brain conventions are not platform
primitives. They are commons content that evolves through use.

No runtime code should change from this note alone. This note is a proposed
canonical naming contract for future primitive consolidation work.

## 2. Classification

This request is a **project-design** change. It asks for architectural
vocabulary, not an implementation. The smallest useful change is this proposed
design note under `docs/design-notes/proposed/`.

## 3. Vocabulary Contract

### Six Product Primitives

| Primitive | User intent | Owns |
|---|---|---|
| `workspace` | Orient inside Workflow state | Universe/workspace list, inspect, create, health summary, user-visible location |
| `workflow` | Design or change executable structure | Branch definitions, nodes, edges, versioning, fork/patch shape |
| `run` | Make work happen and retrieve results | Submit, observe, cancel, resume, fetch outputs, delivery handles |
| `evaluate` | Judge or gate work | Rubrics, evaluator runs, gate claims, run diffs, outcome evidence |
| `discover` | Find reusable public work | Search, similarity, ranking, recommendations, explanations |
| `commons` | Contribute back to shared knowledge | Publish, fork, attribute, wiki write, issue filing, community signals |

This adopts the `discover` split recommended by
`docs/design-notes/2026-04-27-discovery-similarity-remix-substrate.md` while
retaining the tool-surface budget pressure from
`docs/design-notes/2026-04-26-minimal-primitive-set-proposal.md`.

### Five MCP Handles

| MCP handle | Primitive coverage | Initial action family |
|---|---|---|
| `workspace` | `workspace` | `inspect`, `list`, `create`, `status` |
| `workflow` | `workflow` | `build`, `patch`, `fork`, `version`, `register_node`, `describe` |
| `run` | `run` | `submit`, `status`, `events`, `fetch_outputs`, `cancel`, `resume` |
| `evaluate` | `evaluate` | `score`, `gate_claim`, `gate_list`, `diff`, `explain_result` |
| `commons` | `commons` + `discover` | `search`, `similar_to`, `top`, `recommend`, `explain`, `publish`, `fork`, `attribute`, `wiki`, `file_request` |

The rule is: **product primitives are semantic; MCP handles are packaging.**
If a chatbot says "discover," that is correct product vocabulary even if the
wire call is `commons.action=search`.

### Local-App Add-ons

`host` and `upload` remain local-app add-ons from the existing primitive-set
proposal. They are not part of the browser-tier five MCP handles and should not
be counted as general product primitives unless a future capability-axis review
shows browser users need equivalent top-level handles.

## 4. Brain-Evolves-Conventions Rule

Workflow's brain is the wiki/open-brain/commons layer. It evolves conventions:

- how to compose primitives for a domain;
- how to name reusable workflow patterns;
- how to evaluate quality;
- how to file bugs, patch requests, concepts, and design notes;
- how chatbots should speak to users in their vocabulary;
- how daemons should learn from repeated loop failures.

These conventions are **not** new MCP handles. They live as discoverable
commons artifacts. A chatbot applies them by composing the six primitives:

1. `discover` an existing convention or similar prior workflow.
2. `workflow` or `run` using that convention.
3. `evaluate` whether it worked.
4. `commons` publish the improved convention, attribution, or issue.

This keeps platform code small while letting the community continuously evolve
the behavior users experience.

## 5. Why This Is Smaller Than The Alternatives

| Option | Result | Verdict |
|---|---|---|
| Keep only five primitives and hide `discover` inside `commons` vocabulary | Smaller list, but weakens the commons-first mechanism and makes search/ranking feel incidental | Reject |
| Expose six MCP tools immediately | Clear naming, but grows the public tool list before evidence says the handle split is needed | Reject for now |
| Use six product primitives plus five MCP handles | Discovery is first-class in reasoning; public tool list stays tight | Recommend |
| Add a seventh "brain" or "conventions" primitive | Treats community knowledge as platform machinery and invites frozen policy | Reject |

The recommended shape passes the PLAN.md scoping rules:

- **Minimal primitives:** six semantic primitives, five tool handles.
- **Community-build over platform-build:** conventions evolve in commons, not
  as shipped platform features.
- **Privacy/community composition:** sensitive-domain conventions can evolve as
  patterns without becoming platform flags.
- **Commons-first:** discovery and contribution are explicit parts of the
  public commons loop.
- **Capability axis:** the five handles work for browser-only users; local-app
  additions stay tier-specific.

## 6. Migration Implications

This note does not authorize a runtime migration. If accepted, future
implementation work should be sequenced as a separate primitive-consolidation
arc with its own tests and host approval.

Expected future direction:

1. Keep current runtime tools stable until a migration plan exists.
2. Use the six primitive names in design notes, wiki pages, and chatbot-facing
   docs immediately after acceptance.
3. When consolidating MCP tools, target the five-handle surface above.
4. Treat `discover` as a candidate top-level handle only if `commons` becomes
   too large for reliable chatbot selection or client UX.
5. Migrate `branch_design_guide` toward MCP prompts when supported by the
   launch client matrix; do not preserve it as a long-term tool primitive.

## 7. Acceptance Criteria For Promotion

Before this vocabulary moves from proposed note to accepted design truth:

1. Opposite-family review confirms the six-vs-five split does not contradict
   the existing minimal primitive-set and discovery/remix notes.
2. Host confirms `discover` should be first-class product vocabulary even while
   packaged under the `commons` MCP handle.
3. A follow-up implementation plan names the migration boundary, compatibility
   strategy, and chatbot-surface verification matrix.
4. PLAN.md is updated only after approval; until then this note remains
   proposed design context.

## 8. Open Questions

1. Should the `commons` MCP handle use nested action names such as
   `discover.search` / `publish.workflow`, or flat action names such as
   `search` / `publish`? Recommendation: nested names for clarity once the
   action menu grows.
2. Should `workspace.status` absorb current global `get_status`, or should
   `run.status` be the only status shape chatbots learn? Recommendation:
   `workspace.status` for global health, `run.status` for per-run progress.
3. What is the first proof that `discover` deserves a separate MCP handle?
   Recommendation: repeated cross-client tool-selection failures caused by a
   bloated `commons` action menu, not design preference alone.

## References

- `PLAN.md` Scoping Rules
- `PLAN.md` API And MCP Interface
- `docs/design-notes/2026-04-26-minimal-primitive-set-proposal.md`
- `docs/design-notes/2026-04-27-discovery-similarity-remix-substrate.md`
- `docs/design-notes/2026-05-04-operating-model-and-four-agent-topology.md`
