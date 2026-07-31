# Suppress consumed drain merge replay

## Why

The live OpenSpec drain correctly recognized that PR #1945 had already been
consumed, but retained the same admission and resume target while charging the
failure budget. The replacement worker returned the same receipt, exhausted
the bounded run, and left the watchdog red until manual restart.

## What changes

- Treat an exact canonical merge receipt already consumed by this run as a
  stale-candidate suppression event, not new progress and not a worker failure.
- Clear the stale admission and resume target, suppress that target for the
  bounded run, and continue discovery.
- Preserve the original completed-slice and merge-receipt counts.
- Keep malformed, unverifiable, or previously unconsumed merge results on the
  existing visible failure paths.

## What does not change

- Merge verification, canonical PR identity, failure budgets, worker
  concurrency, watchdog terminal policy, or cloud activation.
