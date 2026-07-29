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
   provider and GitHub authority. The tray is only a pre-cutover bridge and is
   stopped before cloud acceptance. **Approved.**

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

The local supervisor remains only until cloud cutover. Cutover is
single-active: stop the tray drain, activate the cloud Branch, prove the cloud
lease/receipts and phone-only controls, then leave the tray drain disabled.
Rollback may stop cloud and temporarily restore the tray, but the two do not
drain concurrently. The tray's state is never canonical health for the cloud
loop.

## Phone-Only Ownership

After cutover, Jonathan manages the drain as an ordinary user through the live
TinyAssets connector from a phone chatbot. Without any computer online, he can:

- inspect the current claim, last useful progress, receipts, authority source,
  retry state, budgets, and blocking reason;
- pause, resume, and stop future slices without interrupting an already
  committed external effect;
- describe a change to the drain, inspect the complete versioned definition and
  diff, dry-test it, publish a new immutable Branch version, and bind or roll
  back the active loop version;
- repair a failed loop by editing its ordinary user-owned composition rather
  than asking an operator to patch a privileged service.

These operations use the canonical chatbot handles and normal owner
authorization. No desktop UI, local filesystem, CLI, host login, or maintainer
intervention may be required.

## Key Assumptions to Validate

- **Must be true:** Jonathan can bind provider authority that a cloud executor
  can use without exposing raw credentials or silently falling back to
  maintainer quota.
- **Must be true:** a private universe Branch can receive a persisted trigger,
  claim one task exactly once, execute Git/GitHub effects through a scoped
  grant, and resume after worker restart.
- **Must be true:** background execution carries the real user/universe/Branch
  authority instead of a synthetic privileged actor.
- **Must be true:** the live connector exposes the complete inspect,
  pause/resume, author/test/publish, rebind, and rollback path to a phone
  chatbot without a desktop-only credential or filesystem step.
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
- single-active cutover with the tray drain stopped before cloud acceptance;
- phone-chatbot inspection, control, repair, and versioned evolution;
- current-main claim admission, bounded execution, PR/CI/review, and terminal
  receipts;
- visible health: last useful progress, current claim, next retry, blocking
  reason, provider/authority source, and no-progress alarm;
- proof that the loop progresses for at least 24 hours while Jonathan's PC is
  off, survives a cloud-worker restart, and never double-claims.

## Not Doing

- no market-compute fallback in the MVP;
- no new top-level MCP verb or privileged patch-loop service;
- no tray/cloud concurrent drain and no parallel multi-lane drain until a
  separately designed concurrency proof passes;
- no bypass of GitHub review, CI, branch protection, or OpenSpec archive gates;
- no raw provider-secret deposit through chat;
- no claim that a green local tray proves cloud-loop health;
- no public commons publication until the private loop is stable and safe to
  remix.

## Acceptance

The MVP is accepted only when Jonathan's computer remains off for the entire
proof and rendered phone-chatbot conversations through the live connector:

1. inspect, pause, and resume the cloud loop;
2. edit its ordinary user-owned definition, inspect the exact diff, dry-test
   it, publish a new immutable version, activate it, and roll back;
3. observe at least 24 hours of useful cloud progress plus cloud-worker restart
   recovery.

Every execution receipt must name Jonathan's user-owned authority source. The
tray drain must be stopped for the proof, and no trace may show maintainer
quota, market compute, duplicate claims, desktop/CLI dependence, or a
privileged bypass.

## Host Approval

Approved 2026-07-29 with two binding clarifications:

- the tray runs only until the cloud version is ready and never concurrently
  with the accepted cloud drain;
- “done” means Jonathan can manage, repair, and evolve the cloud drain through
  a phone chatbot while his computer is entirely off.

## Temporary Bridge Limitation

The local watchdog CLI's `restart` command writes a marker that a fully stopped
watchdog cannot consume; the tray restart action relaunches the consumer first.
This remains a temporary bridge limitation, not behavior inherited by the cloud
loop.
