---
severity: P1
title: A deploy that kills a running automation freezes that universe's automations for up to 3 hours
filed: '2026-09-27'
summary: the per-universe automation lease has a TTL equal to the run timeout (3h). A process killed mid-run never releases it, so the next process sees the universe busy until it expires. Shortening the TTL naively lets two runs overlap.
---

# P1 - a deploy that kills a running automation freezes its universe's automations for up to 3h

**Filed:** 2026-09-27 | **Verified:** 2026-09-27 against `e7089847` (code reading, plus Codex
in-memory interleavings) | **Severity:** P1 (Forever Rule: 24/7 uptime)

## Premise

`AssignedQueueConsumer._run_automations` (`tinyassets/runtime/assigned_queue_consumer.py:658`)
takes the universe lease with `ttl = run_timeout_seconds()`, which defaults to 10800 s. A
refresher thread re-stamps the lease every `LEASE_REFRESH_SECONDS` (60 s). The lease is released
only in that batch's `finally`.

Every merge to `main` deploys and recreates the container, which kills whatever is in flight
(`deploy-kills-in-flight-turns`). When that process was running an automation:

- its lease row stays behind with up to 3 h left, and nothing refreshes it;
- the new process has a new boot-scoped `consumer_id`, so
  `AutomationStore.acquire_universe_lease` (`tinyassets/automations.py:616`) sees a live foreign
  holder and records `universe_busy:worker_assigned_<old boot>`;
- every automation in that universe, including a 300 s loop the owner built to run 24/7, is skipped
  until the old lease expires.

With several deploys a day, a universe that is always running something is frozen most of the time.

## Why the obvious fix is wrong

A 180 s TTL (3 refresh beats) was built on `claude/completion-trigger` (`69e2d151`, reverted). A
gpt-6-astra refute review returned `VERDICT: ADAPT` with two reproduced overlap sequences.

Verbatim:

> treats lease ownership as proof the previous runner died; [assigned_queue_consumer.py:766]
> ignores refresh returning `False`. A starts at t=0; refresh starvation exceeds 180 seconds while
> A remains alive. B acquires at t=181, closes A's attempt, and starts another run at t=241 while A
> still executes.

> After [assigned_queue_consumer.py:727] extends the lease, the batch future completes and is
> reaped. [...] On the next poll, [automations.py:750] permits the same holder to reacquire,
> replacing the long lease with 180 seconds and admitting another attempt while the uncancelled
> worker remains alive.

## Shape of the fix

The fix must hold under both sequences. Two candidates:

1. **Release on boot for a provably dead holder.** A holder id carries its boot. A process whose
   boot is dead (for example, the container instance id no longer matches the running one) cannot
   still be calling a provider. This is only correct where "dead" is provable rather than inferred
   from a missed refresh.
2. **Fence on the refresh result.** A holder whose refresh returns `False` has lost the lease. It
   must cancel its run and must not write its outcome over the new holder's. Same-holder
   re-acquire must not shorten a held long lease.

Whichever lands needs a test for each quoted sequence.
