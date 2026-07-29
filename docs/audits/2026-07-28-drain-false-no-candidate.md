# OpenSpec Drain False `NO_CANDIDATE` Incident

Date: 2026-07-28 PDT
Environment: Windows 11, installed sign-in drain
Run: `drain-20260728-202641-6c9510`, attempt 1

## Symptom

The tray became yellow after the worker returned:

```text
Claimable STATUS rows: 0
DRAIN_RESULT: NO_CANDIDATE - -
```

At the same time, `openspec_flow.py audit` reported 834 unchecked tasks across
32 active changes.

## Root cause

Current `claim_check.py` evidence showed:

- 0 claimable;
- 11 foreign claims classified in flight;
- 8 of those 11 also classified as stale-claim candidates;
- 24 pending rows blocked by dependency prose or file overlap.

The worker brief said stale claims *may* be reaped, but did not require reaping,
blocker freshness checks, or safe cross-cutting promotion before
`NO_CANDIDATE`. The supervisor trusted the terminal marker without comparing it
to canonical claim-check state. Conservative coordination therefore converted
abandoned ownership metadata into an indefinite throughput lock.

The host then confirmed that the 11 claim owners were closed sessions. Changing
only those statuses back to `pending` changed the same checker from 0 to 6
claimable lanes. No task, branch, worktree, or OpenSpec artifact was deleted.

During the next scheduled attempt, the controller dispatched worker 2 but left
`state.status` at the prior `idle` value. The worker was active while the tray
remained yellow. The same lane now marks every attempt `running` before dispatch
and has a regression test for the idle-to-active transition.

## Corrective controls

1. Every worker brief carries a mandatory exhaustion order: own claim,
   claimable finish-first row, stale reaping, blocker revalidation, then safe
   cross-cutting promotion.
2. The supervisor independently parses `claim_check.py --json` after
   `NO_CANDIDATE`.
3. Nonzero `claimable` or `stale` counts make the result invalid and consume a
   finite failure strike.
4. Explicit host confirmation may release same-day closed-session claims;
   autonomous logic retains the existing 24-hour/no-heartbeat stale threshold.
5. Every new worker attempt persists `running` before dispatch so the tray
   reflects active work rather than the previous attempt's terminal state.

## Verification target

The focused regression must prove that claim-check exit status does not hide
valid JSON pressure, that nonzero claimable/stale counts reject idle, and that
zero/zero remains a clean bounded idle. Final runtime proof must show the
installed drain selecting one of the newly claimable lanes without a duplicate
worker.
