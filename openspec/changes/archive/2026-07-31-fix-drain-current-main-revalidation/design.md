## Context

`inspect_current_main_snapshot` already fetches origin and passes
`--status-ref origin/main` to the canonical claim checker. The later
`inspect_candidate_pressure` helper called `inspect_candidate_snapshot`
directly with no ref, causing it to read the controller worktree instead.

The watchdog also carried its restart decision in the same local variable as
ordinary discovery. After a graceful stop, it deleted the request marker and
the following launch block immediately rediscovered the terminal run,
discarding the already-selected fresh-run decision.

## Decision

Delegate pressure-only validation to `inspect_current_main_snapshot` with
`max_hints=0`. This reuses the existing bounded fetch/ref-classification path
and avoids a second definition of current-main truth.

Carry a per-loop launch decision from dead-controller handling into the launch
block. Rediscover persisted runs only when no explicit decision is pending.

## Failure Behavior

Fetch or classification failure remains a rejected result and consumes the
existing bounded failure budget. The repair changes only which coordination
snapshot is authoritative, not the gate's fail-closed behavior.

Terminal outcomes remain sticky without an explicit request. The watchdog
starts fresh only when that request was observed and the prior controller has
stopped.
