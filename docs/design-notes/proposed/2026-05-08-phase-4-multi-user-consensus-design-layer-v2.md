---
title: Phase 4 Multi-User Consensus Design Layer V2
date: 2026-05-08
author: codex-wiki-docs
status: proposed
request_id: WIKI-DOCS
github_issue: 643
wiki_source: pages/concepts/phase-4-multi-user-consensus-design-layer-v2.md
scope: design-only; no runtime code in this branch
builds_on:
  - PLAN.md#full-platform-architecture-canonical
  - PLAN.md#multi-user-evolutionary-design
  - docs/design-notes/2026-05-03-multi-user-workflow-operating-model.md
  - docs/specs/community_branches_phase4.md
---

# Phase 4 Multi-User Consensus Design Layer V2

## 1. Classification

Request kind: docs/ops.

Project classification: project-design preservation. The issue points at a
community wiki concept page, not a code defect. The smallest useful repository
change is to preserve the design layer in a proposed note so coding sessions can
see the full-scale-first consensus/read-state shape while the wiki remains the
community-authored source.

No runtime code change is implied by this request.

## 2. Source And Freshness

The filing names the wiki page
`pages/concepts/phase-4-multi-user-consensus-design-layer-v2.md` and Issue #643.
The 2026-05-08 queue-steering comment says this page is the canonical
full-scale-first consensus design layer and that loop watch repeatedly surfaced
it as an old pending item. This note is therefore a repository-side proposed
design artifact, not an accepted `PLAN.md` amendment.

The wiki page content was not present in this checkout. Future foldback should
compare this note against the live wiki page before accepting or implementing
any lane derived from it.

## 3. Design Intent

Phase 4 v1 closed the single-user loop:

`build branch -> run branch -> judge run -> edit node -> rerun -> compare`.

Phase 4 v2 extends that loop to the multi-user product shape without first
shipping a throwaway single-user consensus layer. The design target is not "one
user rates one run"; it is "many users create, read, judge, fork, remix, and
converge on shared workflow knowledge while the system preserves attribution,
read state, and disagreement."

Full-scale-first means the first durable model must already fit:

- many users reading and judging the same branch version or node lineage;
- many branches bound to the same Goal without forcing premature convergence;
- node-level and branch-level consensus signals that can be recomputed from
  typed events;
- personal read state that does not mutate shared truth;
- immutable cited versions once other users have forked, judged, ranked, or
  linked them;
- moderation and abuse response on consensus inputs, not only on final pages;
- chatbot surfaces that can explain what changed, what is agreed, and what is
  disputed without exposing raw backend tables.

## 4. Relationship To Current Design

This proposal aligns with current `PLAN.md` rather than replacing it.

`PLAN.md#full-platform-architecture-canonical` already rejects phased
throwaway architecture and targets a multi-tenant collaborative backend.
Consensus state must therefore be designed as shared product data from the
start, not as local run metadata later migrated into a social substrate.

`PLAN.md#multi-user-evolutionary-design` already makes Goal first-class above
Branch and treats diverse branches as an ecology. Consensus must preserve that
ecology. Its purpose is to expose signal and support convergence where useful,
not to collapse each Goal into one canonical workflow.

`docs/specs/community_branches_phase4.md` already defines the single-user
judgment and iteration records. V2 should treat those records as the local loop
inside a wider consensus system: a user judgment is still free text and
attributed to a human, but aggregation, read state, and cross-user comparison
must operate over durable typed records.

`docs/design-notes/2026-05-03-multi-user-workflow-operating-model.md` already
adds isolation, leases, budgets, typed high-concurrency facts, and
federation-by-reference. V2 consensus should use those constraints directly.

## 5. Durable Record Shape

Later implementation specs should avoid wiki-prose-only consensus state. At
minimum, the design needs typed records in these categories:

- **Consensus input event:** one user's judgment, flag, fork rationale,
  comparison note, outcome-gate report, or moderation action. Append-only,
  attributed, timestamped, and tied to a stable target reference.
- **Consensus aggregate:** a recomputable projection over input events for a
  Goal, Branch version, Node lineage, Run, or Gate. Stores counts and summaries,
  but the event log remains authoritative.
- **Read-state marker:** per-user or per-session state such as last seen
  aggregate version, dismissed dispute, opened comparison, or reviewed
  moderation notice. Read state is private control-plane state, not shared truth.
- **Versioned target reference:** immutable IDs for branch versions, node
  lineage points, run outputs, gates, wiki pages, and design notes.
- **Dispute marker:** a typed indication that consensus is split, stale,
  suspected abusive, or awaiting moderation. Disagreement is first-class state,
  not a failed aggregate.

These records can later map to Postgres tables, SQLite prototypes, or wiki
exports, but the invariant is stable: high-concurrency consensus facts are
typed and replayable.

## 6. Read-State Requirements

Read state is the main v2 addition over single-user Phase 4. The system needs
to know what a user has already seen without letting that private fact rewrite
shared consensus.

Required properties:

- read markers are scoped to user, provider identity, or explicit anonymous
  session identity;
- read markers point at stable aggregate/version IDs, not mutable labels;
- clearing or changing read state does not delete consensus input events;
- chatbot status can answer "what changed since I last looked?" from read
  markers plus aggregate versions;
- moderation notices and dispute markers have independent acknowledgement state
  so a user can see both new consensus and new safety context.

This keeps the chatbot useful in multi-user collaboration without making the
chat transcript the source of truth.

## 7. Consensus Semantics

Consensus is a projection, not a vote that overwrites history. V2 should support
at least four visible states:

- **emerging:** enough events exist to summarize a trend, but confidence is
  low;
- **stable:** repeated independent input points in the same direction;
- **split:** credible inputs disagree, so the UI should show competing
  rationales instead of a single answer;
- **stale:** underlying branch, node, run, or gate state changed after the
  aggregate was computed.

The system should preserve minority rationales and forks. For Workflow's
evolutionary design, a split can be useful: it may identify domain subtypes,
provider-specific behavior, or separate user goals that should remain separate
branches.

## 8. Non-Goals For This Proposed Note

- No new MCP action is specified here.
- No schema migration is specified here.
- No consensus scoring formula is accepted here.
- No `PLAN.md` text changes are made here.
- No community-authored branch or wiki text is rewritten here.

Those choices require a follow-up spec or accepted design decision after the
live wiki page is compared against this preservation note.

## 9. Implementation Gates For Future Work

Any implementation derived from this design should pass these gates before it
is treated as done:

1. **Full-scale-first data model:** the proposed records support many users,
   many branches per Goal, immutable target references, private read state, and
   recomputable aggregates without a later migration of core identity.
2. **Concurrency proof:** concurrent input, aggregate refresh, and read-state
   updates have tests or load proof matching the project's uptime concurrency
   gate expectations.
3. **Attribution and moderation:** every consensus input is attributable at the
   level available to the actor, and moderation/dispute state is typed.
4. **Chatbot acceptance:** a rendered chatbot conversation can answer what is
   agreed, what is disputed, and what changed since the user last read it.
5. **Post-fix real-use watch:** after public-surface rollout, production traces
   or user-visible history must show clean use; if none exists yet, leave a
   `STATUS.md` monitoring item.

## 10. Follow-Up Lanes

Potential follow-up lanes, each requiring its own claim and scope:

- Compare this note against the live wiki source and amend any missing
  community-authored constraints.
- Draft a storage spec for consensus input events, aggregate projections,
  read-state markers, and immutable target references.
- Draft a chatbot UX spec for "what changed since I last looked?" and split
  consensus rendering.
- Draft a moderation spec for abusive or low-quality consensus inputs.
- Extend the Phase 4 user-sim with two simulated users judging and reading the
  same branch version from separate read-state contexts.

