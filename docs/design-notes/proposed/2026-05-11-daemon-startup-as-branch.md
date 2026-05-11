---
title: Daemon Startup As Branch
date: 2026-05-11
author: codex-wiki-patch
status: proposed
request_id: WIKI-PATCH
github_issue: 803
wiki_source: pages/patch-requests/pr-111-pr-111-daemon-startup-bootstrap-should-be-a-user-redesignabl.md
scope: design-only; no runtime code in this branch
builds_on:
  - PLAN.md#community-evolvable-optimization
  - PLAN.md#engine-and-domains
  - PLAN.md#uptime-and-alarm-path
---

# Daemon Startup As Branch

## Recommendation

Treat daemon startup/bootstrap as a future redesignable branch, not as a
hard-coded special case forever. The useful target is a versioned startup
branch that can run the same kind of node, gate, evaluator, and policy
machinery as ordinary Workflow work while keeping the current non-negotiable
startup invariants protected by the engine.

This proposal is design-only. It does not change startup code, MCP actions,
plugin packaging, service files, or community-authored branches.

## Problem

Startup currently mixes engine obligations with domain and host choices. Some
startup work is not negotiable: load configuration, bind storage, recover
interrupted work, validate provider availability, enforce retention, register
domains, and expose enough status for uptime checks. Other startup work is
policy: what to inspect first, which memories to refresh, which branch should
resume, how much budget to spend before accepting user work, and which domain
warmups matter.

When both categories live only in imperative bootstrap code, users and daemon
hosts cannot redesign startup behavior through the same branch machinery they
use for other long-running work. The platform also loses lineage: a host cannot
easily answer which startup policy ran, why it changed, what gates approved it,
or how to roll it back.

## Proposed Shape

Introduce a conceptual startup branch with two layers:

1. **Engine preflight layer.** This remains owned by `workflow/` and must run
   before any user-redesignable node. It handles file locks, schema/storage
   readiness, secrets/provider binding checks, domain registry loading, crash
   recovery, and status emission. These are guardrails, not branch content.
2. **Startup policy branch.** This is a versioned branch selected by the host
   or universe configuration after preflight passes. It can contain ordinary
   nodes such as memory refresh, queue reconciliation, stalled-branch triage,
   provider health probes, domain warmups, and initial task selection.

The startup policy branch should be inspectable and remixable like other
branches. A user or daemon host should eventually be able to fork it, edit
nodes or gates, run evaluators, and promote a new version under a declared
merge policy.

## Invariants

- Engine preflight cannot be bypassed by a startup branch.
- A failed startup policy branch must leave the daemon in a degraded but
  inspectable state, not an ambiguous half-started state.
- Startup branch execution must be budgeted and bounded; it cannot block
  user-visible MCP availability indefinitely.
- Recovery of in-flight work remains idempotent and safe across process
  restarts.
- Domain-specific startup nodes belong to the domain layer, not shared
  `workflow/` infrastructure.
- Rollback must be possible by selecting a previous startup branch version or
  a minimal built-in recovery branch.

## Minimal Implementation Path

1. Inventory current startup responsibilities and classify each one as engine
   preflight, domain warmup, or user-redesignable policy.
2. Add a read-only startup manifest that records the current ordered startup
   steps and their classification. This gives users a visible target before
   anything becomes editable.
3. Extract policy-shaped startup steps into named node specs while keeping them
   invoked by the existing imperative bootstrap path.
4. Add evaluation gates for startup branches: bounded runtime, status emission,
   recovery idempotence, provider-degraded behavior, and rollback path.
5. Only after those gates exist, allow a host to opt into a versioned startup
   policy branch.

## Non-Goals

- No immediate rewrite of daemon startup.
- No new MCP action in this proposal.
- No weakening of uptime, recovery, storage, or provider-binding checks.
- No automatic migration of existing community-authored branches.
- No domain-specific startup policy in shared engine code.

## Fit With PLAN.md

This follows the community-evolvable optimization principle by making startup
policy a future remixable surface rather than hidden platform code. It follows
the engine/domain boundary by keeping mandatory preflight in `workflow/` while
letting domain warmups live with their domain. It also supports the uptime path:
startup becomes easier to inspect, evaluate, roll back, and improve without
waiting for maintainers to hand-edit bootstrap code.

## Verification

Because this is a proposed design note only:

- No runtime files are touched.
- No plugin mirror rebuild is required.
- Review should confirm the proposal preserves engine-owned startup invariants
  and does not imply that a redesignable startup branch exists today.
