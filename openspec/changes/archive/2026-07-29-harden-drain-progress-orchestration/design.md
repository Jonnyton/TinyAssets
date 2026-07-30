## Context

The supervisor currently waits for `peer_agent.py` to exit before reading the
worker's result file. Codex can leave its command-safety PowerShell parser
alive after it has written the final result, so a successful slice can remain
in `running` state until the outer timeout. The watchdog derives green health
from the controller PID and persisted status alone, and restart recovery only
replays results previously classified as `INVALID_RESULT`.

The 2026-07-29 run provides a concrete migration case: attempt 1 wrote a valid
`PARTIAL` result for the admitted target and PR #1857 was merged, but the live
controller did not consume it.

## Goals / Non-Goals

**Goals:**

- Decouple terminal completion from provider-process exit without accepting a
  partial or malformed artifact.
- Reuse the ordinary result-validation and transition path for live and
  restart recovery.
- Make the tray distinguish active work from a completed artifact awaiting
  controller consumption.
- Avoid a full idle interval after a target-local block when another eligible
  candidate is already visible.

**Non-Goals:**

- Parallel drain workers or provider-utilization management.
- General changes to `peer_agent.py` or provider CLI lifecycle.
- Historical worktree deletion or backlog reshaping.
- Relaxing admission, GitHub merge verification, failure budgets, or stop
  semantics.

## Decisions

### Stable valid artifact is the terminal boundary

While the launcher is live, the supervisor polls the assigned result file. It
accepts the artifact only after the same non-empty content parses successfully
on two observations separated by a short stability interval. It then
terminates the launcher tree and represents the dispatch as successful so the
existing admission and merge-verification path remains authoritative.

This is preferred over changing the provider-wide launcher because the
supervisor alone owns the `DRAIN_RESULT` contract and admission identity.

### One recovery function handles any unconsumed terminal artifact

On `--resume`, before failure-budget enforcement or dispatch, the controller
checks whether the persisted attempt has a result not represented by
`last_result`. A valid artifact must match the preserved admission and pass the
same result transition used for a live dispatch. Invalid or mismatched
artifacts fail closed. Existing `INVALID_RESULT` strike reversal remains
limited to the parser-improvement case.

### Health derives a result-handoff state

The watchdog detects a non-empty result artifact for the current attempt that
is older than a small write-settle threshold while `last_result` is absent.
That state is yellow/waiting with an explicit diagnostic, even if the
controller PID is live.

### Local blocks do not imply global exhaustion

After `BLOCKED`, the controller releases admission and inspects the next
filtered snapshot. It skips the idle interval only when a different
owned/claimable/policy-qualified stale candidate remains. Otherwise existing
idle behavior is preserved. `NO_CANDIDATE` and repeated `PARTIAL` retain their
current waits.

### Admission lanes are unique per attempt

The controller includes the persisted attempt number in each mechanically
created branch and worktree path. Re-admitting the same still-open target after
a verified slice therefore creates a clean current-main lane instead of
colliding with the preserved prior slice. An exact same-attempt path or branch
collision continues to fail closed; the controller never deletes or overwrites
the pre-existing lane.

This is preferred over automatic worktree deletion because prior lanes remain
available for audit/recovery, and over random names because an interrupted
attempt retains a deterministic recovery identity.

## Risks / Trade-offs

- **Artifact observed during a write** → require successful parsing plus
  identical content across two observations.
- **Terminating a launcher hides a real late failure** → terminate only after
  a contract-valid result; ordinary admission and GitHub checks can still
  reject the outcome.
- **Restart replays an unrelated artifact** → require the persisted attempt
  number and exact admission target; fail closed on ambiguity.
- **Rapid block fallback spins across the same target** → retain the
  recent-block filter and require a different eligible hint.
- **Repeated slices accumulate worktrees** → keep historical cleanup outside
  this change; attempt-qualified lanes preserve recovery and can be retired by
  a separately reviewed retention policy.

## Migration Plan

1. Land the tested controller and watchdog change.
2. Stop the old controller only after the merged code is available.
3. Restart the scheduled drain against its existing run directory.
4. Verify attempt 1's `PARTIAL` result is recovered and a foldback worker is
   dispatched.
5. Roll back by restarting on the prior commit; persisted state and artifacts
   remain compatible.

## Open Questions

None for this bounded repair. Parallel providers and historical worktree
retention require separate evidence and changes.
