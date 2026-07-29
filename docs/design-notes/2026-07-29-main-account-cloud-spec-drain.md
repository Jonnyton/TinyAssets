# Main-Account Cloud OpenSpec Drain

**Status:** proposed for host approval  
**Date:** 2026-07-29  
**Owner:** Jonathan's main TinyAssets universe

## Problem Statement

How might Jonathan's main-account universe continuously turn the highest-impact
admissible OpenSpec/STATUS work into reviewed, mergeable progress without
depending on his PC, maintainer model quota, market compute, or a privileged
TinyAssets-only automation loop?

The current Windows tray supervisor proved that bounded slices, mechanical
claims, independent review, and honest health can move work. It also proved the
wrong placement: continuity ends when the PC is off, the controller has its own
stale checkout state, and its tray color describes a local process rather than
the user's durable workflow.

## Directions Considered

1. **Keep the tray as the primary controller.** Fastest to patch, but it cannot
   meet zero-host uptime and does not exercise the platform's cloud-universe
   contract.
2. **Move the same script to GitHub Actions.** Host-independent, but creates a
   second product scheduler and a repository-specific privileged automation
   path outside the user's universe.
3. **Compose a private, user-authored Branch loop in Jonathan's main universe.**
   The universe owns the definition, trigger, checkpoints, receipts, and
   health; ordinary cloud execution runs bounded slices using Jonathan's bound
   provider and GitHub authority. The tray may execute the same Branch as an
   optional fallback. **Recommended.**

## Recommended Direction

Create an ordinary versioned Branch named conceptually `openspec-backlog-drain`
inside Jonathan's main universe. Bind it to a standing Goal whose desired
outcome is steady reduction of the highest-impact admissible platform work.
Run one bounded slice per invocation:

1. fetch and inspect the exact current `origin/main` coordination state;
2. select and mechanically claim one admissible STATUS/OpenSpec lane;
3. create or resume its isolated branch/worktree;
4. implement no more than one reviewable slice under explicit time/token limits;
5. run focused verification and independent opposite-provider review;
6. publish a PR, merge only through normal repository policy, and perform
   OpenSpec sync/archive foldback when complete;
7. persist a typed terminal receipt and checkpoint, then schedule the next
   slice.

The loop is not a special server subsystem. It is a user-owned composition of
the existing Branch, Trigger, Goal, Gate, Run, effect, and cloud-executor
primitives. Its GitHub write authority is destination-scoped to the TinyAssets
repository. Its model authority is explicitly Jonathan-owned. No ambient
maintainer credential or market seller may substitute.

The local supervisor remains a temporary bootstrap and optional recovery
executor. It must read current `origin/main` when selecting work, but its tray
state is not the canonical health of the cloud loop.

## Key Assumptions to Validate

- **Must be true:** Jonathan can bind provider authority that a cloud executor
  can use without exposing raw credentials or silently falling back to
  maintainer quota.
- **Must be true:** a private universe Branch can receive a persisted trigger,
  claim one task exactly once, execute Git/GitHub effects through a scoped
  grant, and resume after worker restart.
- **Must be true:** background execution carries the real user/universe/Branch
  authority instead of a synthetic privileged actor.
- **Should be true:** the current scheduler can express reliable continuation;
  if cron missed-tick behavior is insufficient, standing-Goal/event
  re-enqueueing supplies the smallest generic catch-up contract.
- **Should be true:** independent provider review can be represented as an
  ordinary gate without requiring two continuously running workers.

Each assumption is validated by an executable acceptance test using this drain,
not by a mocked architecture claim.

## MVP Scope

- one private main-account universe;
- one TinyAssets repository;
- one active slice at a time;
- Jonathan-owned provider authority only;
- manual start plus persisted cloud continuation;
- current-main claim admission, bounded execution, PR/CI/review, and terminal
  receipts;
- visible health: last useful progress, current claim, next retry, blocking
  reason, provider/authority source, and no-progress alarm;
- proof that the loop progresses for at least 24 hours while Jonathan's PC is
  off, survives a cloud-worker restart, and never double-claims.

## Not Doing

- no market-compute fallback in the MVP;
- no new top-level MCP verb or privileged patch-loop service;
- no parallel multi-lane drain until single-lane concurrency proof passes;
- no bypass of GitHub review, CI, branch protection, or OpenSpec archive gates;
- no raw provider-secret deposit through chat;
- no claim that a green local tray proves cloud-loop health;
- no public commons publication until the private loop is stable and safe to
  remix.

## Acceptance

The MVP is accepted only when a rendered chatbot conversation creates or
inspects the loop through the live connector, production evidence shows a
24-hour PC-off run with useful progress and restart recovery, every execution
receipt names the user-owned authority source, and no post-fix trace shows
maintainer quota, market compute, duplicate claims, or a privileged bypass.

## Open Question for Host Approval

Approve direction 3 as the target, with the Windows tray retained only as a
temporary bootstrap and optional executor while the cloud/BYOC prerequisites
land.
