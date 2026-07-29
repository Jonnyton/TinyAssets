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
6. An in-flight row owned by the exact drain identity also rejects
   `NO_CANDIDATE`; the worker must resume it rather than waiting 24 hours for its
   own abandoned claim to become stale.
7. A live replacement worker remained artifact-free for more than 14 minutes
   despite six claimable rows. The controller now injects at most five ordered
   own/claimable/stale hints, and the worker must revalidate and commit the first
   still-valid claim before broad audit.

## Verification target

The focused regression must prove that claim-check exit status does not hide
valid JSON pressure, that nonzero claimable/stale counts reject idle, and that
zero/zero remains a clean bounded idle. Final runtime proof must show the
installed drain selecting one of the newly claimable lanes without a duplicate
worker.

## Opposite-provider review

Claude Fable 5 returned **APPROVE** after two passes. It independently
reproduced `CandidatePressure(claimable=6, stale=0)` against the real repository,
confirmed that a nonzero `claim_check.py` exit cannot hide valid JSON, and
verified the bounded two-strike failure path.

The follow-up approved both final adaptations:

- exact drain-owned in-flight rows now reject `NO_CANDIDATE`, including rows
  whose Status cell carries an `ACTIVE` suffix;
- `begin_attempt` persists `running` before dispatch, so the tray cannot retain
  the preceding attempt's `idle` state while a worker is active.

No installation blocker remained. Runtime selection proof is still required
before foldback.

The later candidate-preselection review initially returned **BLOCK**: canonical
stale entries wrap their STATUS row under `row`, while the first parser treated
them as flat. That path was fail-safe but dropped every hint. The parser now
unwraps the canonical shape, and its regression constructs the payload through
the real `claim_check.build_payload` producer rather than a hand-written fake.

Claude's narrow re-review returned **APPROVE**. It independently round-tripped a
real producer payload, reproduced the regression failure, confirmed the
OWNED-to-CLAIMABLE-to-STALE order and five-hint bound, and verified that the
worker runs the bounded claim-phase context feed before committing a hint.
Evidence: 78 supervisor/watchdog tests passed on 2026-07-28 Windows 11; strict
OpenSpec validation and Ruff also passed. Live claim-speed proof remains the
last installation gate.

The reviewed high-effort worker then received five concrete hints but remained
claim-free for more than five minutes. The launcher had inherited
`model_reasoning_effort = "high"` from the interactive Codex configuration.
Drain dispatch now explicitly uses `medium`; the narrow slice still retains
test, review, CI, merge-verification, and failure-budget gates.

Claude's opposite-provider review returned **APPROVE** after tracing the
argument through `openspec_drain_supervisor.py` and `peer_agent.py` to the
effective Codex CLI override. It confirmed that Claude dispatch is unchanged
and that structural quality gates make medium appropriate for the preselected
single-slice contract. A negative regression assertion now pins that Claude
commands omit `--effort`.
