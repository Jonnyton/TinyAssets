# The assigned-queue consumer error-loops ~41 times a minute

**Severity:** P2 · **Filed:** 2026-08-28, measured on production
**Surface:** `tinyassets/runtime/assigned_queue_consumer.py`

## Measured, not estimated

```
$ docker logs tinyassets-daemon --since 5m | grep -c Traceback
206                       # 41 per minute

103  PermissionError: cloud background attempt is unavailable
103  CloudContinuationActivationError: executor_audience_unavailable:
     trusted cloud worker assignment is absent or mismatched
```

Two exceptions, in lockstep, on a fresh container (4 minutes up). It restarts with the
container every deploy and immediately resumes, so this is steady state rather than a
burst — and it is the same pair that was in the log hours earlier, before any of the
billing work.

Both come from `_pump_automation`: one from
`reconcile_one_terminal_cloud_automation` → `record_cloud_automation_terminal`, the
other from `activate_one_requested_cloud_automation`. The universe is the founder's.

## Why it is worth a file rather than a shrug

**It is not a billing problem and it is not new.** It is filed because of what it costs
the next person, not because it broke something today.

- **It buries everything else.** Every real error now arrives in a stream of ~2,500
  tracebacks an hour. I checked this log four times tonight while landing billing
  changes, and each time had to establish "these are the pre-existing ones" before I
  could read anything. That is a tax on every future investigation, and eventually one
  will be paid by missing something.
- **A permanently-red signal carries no information**, the same argument already made
  for `full-tests` in `2026-08-27-full-tests-permanently-red.md`. A loop that has always
  been failing cannot tell you when it starts failing differently.
- **It burns CPU on a box whose worker pool is the scarce resource** — four concurrent
  runs per box is the users-per-box ceiling in the cost model.

## What it is not

Not a data-loss or correctness bug that I can see: both paths raise before doing
anything, so the loop appears to be inert apart from the noise and the cycles.
`openspec/changes/execute-assigned-queue-consumer/` describes intended work on this
subsystem, but nothing there records that it is currently hot-looping in production,
which is why this file exists.

## Two things to decide

1. Whether the consumer should back off when its precondition is absent, rather than
   retrying at full speed against a condition that cannot change without a deploy.
2. Whether `executor_audience_unavailable` should be logged once per state-change rather
   than once per attempt.
