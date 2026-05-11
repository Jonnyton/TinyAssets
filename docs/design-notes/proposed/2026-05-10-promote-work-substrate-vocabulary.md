---
title: Promote Work Substrate Vocabulary
date: 2026-05-10
author: codex-wiki-design
status: proposed
request_id: WIKI-DESIGN
github_issue: 755
wiki_source: pages/patch-requests/pr-098-promote-6-primitives-5-mcp-handles-substrate-canonical-vocab.md
scope: design-only; no runtime code in this branch
supersedes:
  - PR #662 close-as-superseded framing
builds_on:
  - docs/notes/2026-05-06-work-primitive-industry-framing.md
  - docs/design-notes/2026-04-26-engine-primitive-substrate.md
  - PLAN.md#scoping-rules
  - PLAN.md#api-and-mcp-interface
---

# Promote Work Substrate Vocabulary

## Recommendation

Promote the six substrate concepts plus five MCP handles into `PLAN.md` as
canonical project architecture:

- Concepts: `Node`, `Edge`, `State`, `Scope`, `Run`, `Trigger`.
- Handles: `read.graph`, `write.graph`, `run.graph`, `read.page`,
  `write.page`.

This is a vocabulary and architecture change only. It does not add runtime MCP
actions, change tool registration, or require plugin rebuilds.

## Rationale

The substrate framing has been stable in feedback memory and the promoted wiki
concept page since 2026-05-06, but `PLAN.md` is the design reference new
coding sessions read first. Leaving the vocabulary only in wiki memory and a
docs/ops note makes the project look split between the older 8-engine
primitive pressure test and the newer 6+5 work-substrate language.

The useful distinction is:

- The six concepts describe durable work at the graph layer.
- The five handles describe permissioned ways an agent or chatbot can inspect
  and act on that work through MCP-compatible surfaces.
- Existing modules and tools can keep compatibility names, but design docs,
  permission checks, and future tool descriptions should be able to map back to
  this vocabulary.

## Scope

In scope:

- Add a concise canonical section to `PLAN.md`.
- Reference this note from `PLAN.md`.
- Mark the older 8-engine-primitive note as historical pressure-test framing,
  not the canonical primitive count.

Out of scope:

- Runtime MCP tool renames or new actions.
- Permission implementation changes.
- Rewriting community-authored branches or PR #662 content.
- Changing `workflow/*` runtime code or plugin mirrors.

## Compatibility

The older `docs/design-notes/2026-04-26-engine-primitive-substrate.md` remains
useful because it mapped implementation modules and proved compositional
coverage. This promotion narrows what future contributors should call
foundational architecture. If future work needs implementation-specific
subsystems such as provider routing, retrieval, catalog, dispatcher, or
evaluation, those should be described as implementations or compositions of
the six concepts and five handles unless a new irreducible concept passes the
scoping rules.

## Verification

Because this is documentation-only:

- No Python files are touched.
- No runtime tests or plugin rebuild are required.
- Review should confirm `PLAN.md` now exposes the canonical vocabulary and does
  not imply new MCP actions exist today.
