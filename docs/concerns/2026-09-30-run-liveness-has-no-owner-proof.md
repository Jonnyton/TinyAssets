---
severity: P1
title: A queued/running run row has no proof of which process owns it, so a crashed engine child can silently end an owner's loop
filed: '2026-09-30'
summary: In-flight runs are ended by the boot sweep (runs older than the lock-holding server) or by a read that finds no live Future in its own process and no progress for an hour. Neither proves the owner is dead. A crashed engine child's run is ended silently by a read, and an owner's run_completed loop stops.
---

# A queued/running run row has no proof of which process owns it

**Filed:** 2026-09-30, from two gpt-6-astra refute rounds on the in-flight recovery fix
(the lock-gated sweep with its process-start cutoff).
**Severity:** P1 for 24/7 loops. Every serving universe has an engine MCP child process
that executes runs beside the server's own. The supervisor respawns a crashed child.

## What remains

- **A crashed engine child's run ends silently.** The replacement child does not sweep,
  because the server holds `.run_recovery.lock`. The row stays `running` until a read's
  orphan check (`runs._mark_orphaned_run_if_needed`: no local Future, no progress for
  `TINYASSETS_ORPHANED_RUN_GRACE_SECONDS`, default 3600) marks it interrupted. That
  transition is **not announced**, so an owner's `run_completed` loop waiting on it stops.
  On main before the fix, a replacement child's first run tool swept every row and
  announced them. That covered this case, but it also falsely interrupted every live run
  on the host.
- **Why the read-time path stays silent (round 2, P1).** It is a guess, not a death
  proof. A run it wrongly ends can still start or finish later: an unmanaged queued run
  that re-enters `running`. That run then announces its own completion, so one run
  produces two wakes and an owner's self-following loop forks into two chains. It can
  also wake a follower of a DIFFERENT branch before its prerequisite has finished.
- **A live sibling run can still be marked interrupted by a read** after an hour of
  silence (a long agent turn). This predates the fix, and the transition is not announced.
- **Announcement delivery is not durable.** The boot sweep emits after its commit. A
  crash between the two leaves terminal rows that no later sweep selects.

## The fix

Owner proof, then announce exactly once:

1. Stamp each run at creation with an owner token. Have every run-executing process (the
   server and each engine child) hold a liveness lock for that token for its whole life,
   the same shape as `automations.hold_process_liveness`.
2. Recovery, whether at boot, on a supervisor respawn, or on a read, interrupts exactly
   the rows whose owner is provably dead.
3. Record the announcement durably (an outbox row written in the same transaction as the
   status) so it is emitted once and survives a crash.

This is a storage change (a column or a side table, plus an outbox), so it needs an
OpenSpec proposal first.
