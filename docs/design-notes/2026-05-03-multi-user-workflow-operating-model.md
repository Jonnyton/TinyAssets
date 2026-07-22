---
title: Multi-User Workflow Operating Model
date: 2026-05-03
status: research
source: pages/plans/multi-user-workflow-operating-model.md
source_issue: 236
---

# Multi-User Workflow Operating Model

Community wiki source:
`pages/plans/multi-user-workflow-operating-model.md`, retrieved from the live
wiki on 2026-05-03. This repository note keeps the proposal visible to coding
sessions without promoting it to canonical `PLAN.md` truth.

## Classification

Request kind: docs/ops.

Smallest useful repo change: preserve the wiki proposal as a tracked design
reference and spell out how future implementation work should use it. No
runtime code change is implied by this issue.

## Operating Model Summary

Workflow should scale as a multi-tenant goals-and-runs substrate:

- active user work stays isolated in personal, universe, draft-branch, run,
  transcript, temporary-file, and credential scopes;
- shared state changes only through explicit publication, gate evidence,
  wiki promotion, bug/feature filing, or PR-gated canonical docs;
- shared branch versions and other forkable/citable records must be immutable
  once other users can reference them;
- substantive execution should become durable runs with lifecycle state,
  step-level append-only events, checkpoints, cancellation, expiry, and
  idempotency keys for externally visible side effects;
- user requests should pass through server-owned fair queues with per-user,
  per-organization, per-goal, per-worker, and priority-class controls;
- workers claim jobs with expiring leases and generation checks, not permanent
  locks;
- storage, transcript, artifact, compute, provider-token, concurrency, and
  long-running-job budgets must be visible and enforceable;
- high-concurrency facts belong in typed records, not wiki prose;
- discovery should federate by stable references instead of collapsing every
  workspace into one mutable global namespace.

## Relationship To Current Plan

This proposal is aligned with existing `PLAN.md` direction:

- `Full-Platform Architecture (Canonical)` already targets multi-user
  collaboration, shared discovery, paid-market inboxes, moderation, and
  hostless uptime.
- `Multi-User Evolutionary Design` already names Goal as first-class above
  Branch and treats many branches pursuing one Goal as the default pattern.
- `State And Artifacts` and `Live State Shape` already separate durable state
  from temporary execution surfaces.
- `API And MCP Interface` already treats MCP clients as control stations, not
  the source of system truth.

The proposal adds sharper implementation constraints around isolation,
fairness, leases, budgets, and typed record boundaries. Those constraints
should inform future specs and reviews, but they are not yet accepted as a
complete canonical design.

## Implementation Implications

Future multi-user work should be checked against these invariants before it
ships:

- A single user cannot fill disk, consume all worker slots, or starve other
  users' interactive jobs.
- A worker crash cannot orphan a run indefinitely.
- Provider exhaustion cannot create an infinite retry loop or unbounded
  transcript growth.
- Shared branch references do not move after forks, rankings, citations, or
  gate evidence point at them.
- Private user context is excluded from shared publication by default.
- Hot Goals degrade through queue caps, caching, and backpressure rather than
  unlimited write amplification.
- Chatbot-facing status messages are grounded in real queue, budget, lease,
  and failure fields.
- Every shared high-concurrency fact has a typed record and stable ID.

## First Follow-Up Candidates

The wiki page's minimum viable path can be decomposed into later scoped lanes:

1. Storage, transcript-growth, provider-exhaustion, and per-user cap
   observability.
2. Durable run records with queue, lease, heartbeat, cancellation, expiry, and
   idempotency-key fields.
3. Content-addressed branch versions and fork lineage for publication.
4. Fair scheduling policy with per-user/per-goal caps, priority classes,
   aging, and backpressure language.
5. Federation-by-reference across Goals, Branches, Runs, Gate Events, Bugs,
   and Wiki pages.

Each lane should become a concrete spec or `STATUS.md` work row before code
changes begin.

## Open Questions

- What is the first durable queue backing store: Postgres, SQLite with strict
  single-host discipline, or an external queue?
- Are daemon-hosting users trusted workers, semi-trusted workers, or untrusted
  executors that receive only sandboxed jobs?
- What is the minimum branch-version snapshot that is reproducible enough to
  fork but cheap enough to store?
- Should per-Goal caps be static, derived from gate activity, or dynamically
  adjusted by system pressure?
- What exact chatbot language should represent queue delay, budget denial,
  provider exhaustion, and lease recovery?
