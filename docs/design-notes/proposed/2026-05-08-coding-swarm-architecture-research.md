---
title: Coding Swarm Architecture Research
date: 2026-05-08
author: codex-wiki-design
status: proposed
request_id: WIKI-DESIGN
github_issue: 437
wiki_source: pages/notes/pages-notes-cowork-coding-swarm-architecture-research-2026-05-05.md
source_status: issue metadata reachable; wiki source unavailable from this checkout and GitHub wiki clone
scope: design-only; no runtime code in this branch
builds_on:
  - PLAN.md#scoping-rules
  - PLAN.md#providers
  - PLAN.md#harness-and-coordination
  - docs/design-notes/2026-05-04-operating-model-and-four-agent-topology.md
  - docs/specs/2026-05-03-dual-key-auto-ship-acceptance.md
  - docs/specs/loop-outcome-rubric-v0.md
---

# Coding Swarm Architecture Research

## 1. Classification

Issue #437 is a **project-design** filing. It points at a Cowork-authored wiki
note, `pages/notes/pages-notes-cowork-coding-swarm-architecture-research-2026-05-05.md`,
but the wiki page is not present in this repository checkout, the public raw
wiki URL returns 404, and cloning `Jonnyton/Workflow.wiki` with the workspace
remote credentials returns "Repository not found." This note therefore records
the smallest safe project change available from current evidence: preserve the
request as a proposed design wrapper and map it against existing Workflow
architecture without making runtime changes.

Do not treat this as acceptance of any inaccessible claims from the source
wiki note. Before promotion to `docs/design-notes/` or `PLAN.md`, an
opposite-family reviewer should retrieve the original wiki note or confirm it
is intentionally unavailable.

## 2. Recommendation Summary

Use "coding swarm" to mean a **review-gated lane ecology**, not a central
multi-agent scheduler. Workflow already has the essential architecture pieces:
the `STATUS.md` claim surface, GitHub/worktree lanes, provider-context feed
checkpoints, dual-family review, loop outcome labels, auto-ship safety
envelopes, and user-filed wiki/issue intake. The next design move should be to
make these pieces explicit as a swarm contract before adding new runtime
coordination primitives.

The smallest useful architecture change is a proposed contract:

1. Swarm units are GitHub-shaped lanes, not ephemeral chat threads.
2. Every lane has a typed source, ownership boundary, evidence trail, and
   review gate.
3. Multiple providers may work concurrently only through visible lane claims.
4. Cross-family review remains the default safety invariant for substantive
   changes.
5. The swarm optimizes for lower manual intervention rate, not higher agent
   count.

This keeps the PLAN.md minimal-primitives and community-build rules intact. A
"swarm scheduler" would be a platform feature unless a specific structural gap
proves it cannot be composed from existing claims, worktrees, PRs, ledgers,
and review gates.

## 3. Proposed Swarm Contract

### Lane Is The Unit Of Parallelism

A coding swarm member does not own an abstract task. It owns a lane with:

- source: issue, wiki path, idea promotion, audit, exec plan, or host request;
- claim: `STATUS.md` row or issue-local auto-change branch metadata;
- write boundary: exact files/directories, not broad subsystems;
- branch/worktree: one branch and, for durable local work, one `_PURPOSE.md`;
- evidence: tests, lint, rendered user proof when applicable, and review notes;
- foldback: PR, draft PR, parked lane, or explicit abandoned/swept record.

This is already the discipline described by AGENTS.md and PLAN.md. The design
choice is to call it the swarm substrate and resist a second coordination
plane.

### Coordinator Is A Referee, Not A Foreman

The coordinator's job is to maintain invariants:

- prevent overlapping write claims;
- classify blocked, host-owned, stale, and claimable lanes;
- surface hidden provider context before build/review/foldback;
- require evidence before status promotion;
- route blocked findings back to wiki/issues so future agents inherit them.

It should not decide implementation details for every lane. PLAN.md's
daemon-driven principle still applies: improve context, tools, and evaluators
when decisions fail instead of encoding recipes.

### Review Is Stereoscopic

For substantive changes, especially runtime, public surface, storage, auth,
migration, concurrency, or data-loss-risk work, the swarm needs at least two
families of model judgment. This follows the existing Codex/Cowork dual-key
acceptance pattern:

- one OpenAI-family reviewer;
- one Anthropic-family reviewer;
- GitHub PR review state as canonical for PR-backed changes;
- status/ledger mirrors for chatbot visibility, never as a replacement source
  of truth.

Docs-only design proposals may be drafted by one family, but promotion to
accepted architecture should wait for opposite-family review when the source
came from research, external context, or an inaccessible wiki note.

### Swarm Health Is Outcome Quality, Not Busyness

The coding swarm should be measured by:

- clean terminal lane rate;
- rollback/revert rate;
- stale-claim rate;
- manual checker intervention count;
- percentage of lanes with complete evidence;
- post-fix user-surface confirmation where applicable;
- repeated blocker classes converted into substrate improvements.

Agent count, branch count, and comment count are weak signals. More agents can
make the system worse if they create overlapping work, stale claims, or shallow
review. A healthy swarm trends toward fewer manual rescues because its
coordination substrate catches failures earlier.

## 4. Non-Goals

- No new MCP actions are proposed here.
- No runtime scheduler, queue, or agent identity primitive is proposed here.
- No change to `workflow/*`, packaging, or live chatbot behavior is proposed.
- No central "lead agent" authority is introduced beyond existing host,
  STATUS.md, PR, and review gates.
- No acceptance of the inaccessible wiki note's unstated architecture claims.

## 5. Open Questions Before Acceptance

1. What claims did the original Cowork wiki note make that are not captured by
   the existing May 4 operating-model note?
2. Should swarm lane metadata be normalized into a machine-readable record, or
   are `STATUS.md`, `_PURPOSE.md`, PR bodies, and ledgers sufficient for now?
3. Which swarm metric should be promoted first: manual intervention ledger,
   stale-claim rate, or evidence-completeness rate?
4. When an auto-filed WIKI-DESIGN issue points at an unavailable wiki page,
   should the loop automatically add a source-retrieval blocker label/comment
   instead of dispatching design drafting?

## 6. Acceptance Gate For This Proposal

This proposal is ready to promote only after:

- an opposite-family reviewer retrieves or independently confirms the source
  wiki note's contents;
- the reviewer checks this contract against PLAN.md scoping rules and the May
  4 operating-model note;
- any missing source claims are either folded into this proposal or explicitly
  rejected;
- the result remains design-only unless a concrete structural gap is proven.
