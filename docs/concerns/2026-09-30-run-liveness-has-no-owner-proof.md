---
severity: P2
title: A queued/running run row has no proof of which process owns it, so recovery guesses from time
filed: '2026-09-30'
summary: In-flight runs are ended by a boot sweep (runs older than the lock-holding server) or by a read that finds no live Future in its own process and no progress for an hour. Neither proves the owner is dead. An engine child's run can be marked interrupted while it is still running, and a crashed child's run waits an hour to be announced.
---

# A queued/running run row has no proof of which process owns it

**Filed:** 2026-09-30, from the gpt-6-astra refute round on the in-flight recovery fix
(the lock-gated sweep with its process-start cutoff).
**Severity:** P2. Every serving universe has an engine MCP child process that executes
runs beside the server's own.

## What remains

- **A live sibling run can be marked interrupted by a read.** `runs._mark_orphaned_run_if_needed`
  treats a row as orphaned when THIS process has no Future for it and nothing has
  recorded progress for `TINYASSETS_ORPHANED_RUN_GRACE_SECONDS` (default 3600). A run
  in another process that works silently for an hour (for example a long agent turn)
  is marked interrupted while it is still running. Since the fix, that transition is
  also announced as `run_completed(interrupted)`, so an owner's loop gets a wake early.
  #4114 makes that wake wait for the agent's lease, so the agent never runs twice. The
  run's real completion is not announced afterwards.
- **A crashed engine child's run waits up to the grace window.** The supervisor
  (`engine_mcp_http._supervise`) respawns a dead child. The replacement does not sweep,
  because the server holds `.run_recovery.lock`. The dead child's rows stay `running`
  until a read finds them past the grace window. That read now announces them, so a
  run_completed loop resumes. Before the fix it never resumed.

## The fix, when it is worth it

Stamp each run at creation with an owner token. Have every run-executing process hold
a liveness lock for that token for its whole life, the same shape as
`automations.hold_process_liveness`. Recovery then interrupts exactly the rows whose
owner is provably dead, and announces them. This is a storage change (a column, or a
side table), so it needs an OpenSpec proposal first.
