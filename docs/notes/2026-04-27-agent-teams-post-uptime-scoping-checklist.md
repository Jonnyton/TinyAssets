# Agent-teams-on-TinyAssets: Post-Uptime Scoping Checklist

Date: 2026-04-27
Author: codex-gpt5-desktop
Status: ready-for-unblock execution

## Purpose

Convert the existing research note into a start-ready checklist once blocking prerequisites land:

- uptime-track close
- daemon-economy first-draft

## Entry gates (must all be true)

1. Uptime track marked stable by current coordination board.
2. Daemon-economy first-draft merged and callable.
3. No active P0/P1 regressions on public chatbot surface.

## Phase 0 scope lock

1. Confirm this remains a **user project composed from primitives**, not a platform-owned product.
2. Freeze target user story:
   - "Spawn teammate daemons as nodes across branches."
3. Freeze v0 non-goals:
   - no bespoke teammate orchestration top-level API
   - no new auth model
   - no automatic cross-branch retries beyond existing fallback

## Phase 1 seam validation checklist

1. Cross-branch invocation path works with current request surfaces.
2. Teammate identity/soul attachment can be represented by existing node metadata.
3. Inter-teammate messaging works via existing bid-market/free-queue mechanisms.
4. Partial-failure handling uses existing daemon fallback paths.
5. Provenance/audit trail is queryable from existing run/event surfaces.

## Phase 2 thin-slice candidate

Single scenario:

- one lead node
- two teammate nodes on sibling branches
- one message exchange
- one partial failure
- one successful final synthesis

If this can be composed cleanly, do not expand platform primitives.

## Escalation criteria

Only open platform primitive proposals if thin slice fails due to structural impossibility on existing surfaces.

Required escalation evidence:

1. exact seam that fails
2. why composition workaround is not viable
3. smallest additional primitive that resolves it

## Deliverables when unblocked

1. Scoped execution plan in `docs/exec-plans/active/`
2. One user-sim script for the thin slice
3. Gap report mapped to seams from the prior research note
