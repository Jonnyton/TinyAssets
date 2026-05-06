---
title: WIKI-DESIGN substrate framing review
date: 2026-05-06
status: proposed
request_id: WIKI-DESIGN
issue: 451
wiki_path: pages/notes/pages-notes-cowork-codex-substrate-framing-locked-review-request-2026-05-06.md
reviewer: codex-wiki-design
classification: project-design
---

# WIKI-DESIGN substrate framing review

## Summary

Accept the framing direction with one clarification before implementation:
Workflow should treat the locked surface as **six platform primitives, five
public MCP handles, and one host approval gate**.

The five public MCP handles are:

| Handle | User job | Existing design lineage |
| --- | --- | --- |
| `workspace` | Orient, create, and inspect workspaces/universes. | `2026-04-26-minimal-primitive-set-proposal.md` |
| `workflow` | Design, patch, fork, and version executable workflow definitions. | `2026-04-26-minimal-primitive-set-proposal.md` |
| `run` | Submit, observe, fetch, and resume work. | `2026-04-26-minimal-primitive-set-proposal.md` |
| `evaluate` | Score, compare, and claim outcome gates. | `2026-04-26-minimal-primitive-set-proposal.md` |
| `commons` | Discover, publish, attribute, file requests, and collaborate. | `2026-04-26-minimal-primitive-set-proposal.md` |

The sixth platform primitive is `host`: registering local daemon capacity,
capabilities, trust policy, and claim eligibility. It should not be exposed as
a browser-first public MCP handle until the local-app host flow is ready. The
host approval gate is the safety boundary around `host`-mediated execution and
auto-ship decisions, not a convenience feature and not a new user-facing tool.

## Why this fits PLAN.md

This clears the five scoping rules in `PLAN.md`:

- **Minimal primitives:** the public MCP surface remains five handles, matching
  the existing minimal primitive-set proposal. `host` is a capability-tier
  primitive, not a sixth browser handle.
- **Community-build over platform-build:** the handles expose composition
  points. They do not pre-bake domain workflows, privacy modes, requester
  policies, or bounty strategies.
- **Privacy via community composition:** private data remains host-resident.
  The host gate approves execution and publication boundaries; it does not add
  platform-side private storage.
- **Commons-first architecture:** `commons` is the shared collaboration surface;
  private host-only work remains outside platform storage unless explicitly
  published.
- **User capability axis:** browser-only users get the same five handles.
  Local-app users additionally gain `host` because they can donate daemon
  capacity and local software access.

## Relationship to existing design notes

This proposal does not replace the two active 2026-04-26 notes. It locks their
relationship:

- `docs/design-notes/2026-04-26-minimal-primitive-set-proposal.md` owns the
  chatbot/user-facing tool vocabulary.
- `docs/design-notes/2026-04-26-engine-primitive-substrate.md` owns the
  engine-internal substrate vocabulary.
- This note owns the bridge claim for Issue #451: the user-facing lock is
  **5 MCP handles + local-app `host` primitive + host approval gate**.

Avoid mixing the layers. The engine substrate remains the eight internal
operations named in the substrate note: graph execution, typed state,
checkpointing, provider routing, retrieval, evaluator, catalog, and dispatcher.
Those are implementation dependencies, not chatbot handles.

## Host Approval Gate

The host approval gate is load-bearing wherever Workflow asks a local or
trusted host to execute code, publish changes, spend money, or merge/deploy.
It should be modeled as policy around execution and shipping, not as another
general MCP handle.

Initial semantics:

- Default-deny for local code execution, local software invocation, daemon
  capacity donation, auto-ship, payment settlement, and publication from a
  private host boundary into the commons.
- Approval records are durable, reviewable, and scoped to the exact action
  class, host, request, and evidence packet.
- Runtime/substrate/API/deploy/auth/secrets classes require explicit host
  authority in addition to opposite-family reviewer approval, consistent with
  `docs/specs/2026-05-03-dual-key-auto-ship-acceptance.md`.
- Browser-only users can request hosted execution through `run`, but they do
  not directly control host registration policy.

## Implementation Gate

Do not implement runtime MCP changes from this note alone. Before code work,
open a scoped implementation spec that names:

- exact current tools/actions that fold into each handle;
- wire-compatible migration behavior for existing connector users;
- acceptance tests for Claude.ai and ChatGPT Developer Mode;
- read-only/status affordances for pending host approvals;
- plugin mirror requirements if canonical `workflow/*` runtime files change.

## Cohit Guard

Before drafting this note, `scripts/check_primitive_exists.py` was run against
`origin/main` for the proposed handles:

| Candidate | Result |
| --- | --- |
| `workspace` | clean |
| `workflow` | clean |
| `run` | clean |
| `evaluate` | clean |
| `commons` | clean |
| `host` | clean |

No existing action handler or map entry collided with the proposed names on
`origin/main`.

## Review Caveat

The synced wiki page referenced by Issue #451 was not present in this checkout
at `pages/notes/pages-notes-cowork-codex-substrate-framing-locked-review-request-2026-05-06.md`.
This review therefore uses the issue body plus current repo design context.
If the wiki note contains additional constraints, fold them into this proposed
note before accepting it.
