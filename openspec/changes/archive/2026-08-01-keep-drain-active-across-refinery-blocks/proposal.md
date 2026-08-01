## Why

The live drain had 47 exact-current-main refinery candidates but entered a
blocked cooldown after one refinery target landed a durable blocker. The
post-block alternative check excludes refinery candidates, contradicting the
platform rule that visible refinable work prevents truthful idleness.

## What Changes

- Treat a different recent-block-filtered refinery candidate as eligible
  follow-up work after a refinery target returns a verified `BLOCKED` result.
- Preserve exact-target quarantine so the blocked refinery lane is not retried
  until current main clears its blocker.
- Keep ordinary admission safety unchanged: refinery workers remain
  coordination-only and never authorize product implementation.
- Add regression proof from the observed one-blocked-plus-other-refinable
  backlog shape.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `development-coordination-runtime`: a blocked refinery target no longer
  causes an idle delay while a distinct safe refinery candidate remains.

## Impact

The change affects `scripts/openspec_drain_supervisor.py`, its focused tests,
the local watchdog's observed controller state, and the as-built development
coordination runtime specification. It adds no dependency and does not change
provider concurrency, product code, or cloud authority.
