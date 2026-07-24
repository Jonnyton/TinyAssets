## Context

Both canary probe steps must tolerate their own non-zero exit long enough to
write `overall` and diagnostic outputs. The downstream alarm sink therefore
runs with `if: always()` and can process the current observation even when the
probe job ultimately fails. Today there is no later failing step, so a red
probe job concludes success and the next run's prior-conclusion query cannot
recognize it as the first red.

## Goals / Non-Goals

**Goals:**

- Preserve current-run output publication and alarm-sink execution.
- Make a red published result produce a failed probe-job and workflow
  conclusion that the next run can observe.
- Keep DNS and LLM-binding workflow controller shapes consistent.

**Non-Goals:**

- Change probe semantics, schedules, thresholds, labels, or incident bodies.
- Replace the existing prior-workflow-conclusion threshold with new state.
- Deduplicate or otherwise rewrite the alarm-sink JavaScript.

## Decisions

Each probe keeps its output-producing step as `continue-on-error: true`. A
final, non-tolerated shell step reads that step's published `overall` output
and exits non-zero exactly when it is `red`. This orders state publication
before failure propagation and avoids a second implementation of any alarm
logic.

The alarm-sink job retains its dependency on the probe job and `if: always()`.
GitHub Actions can therefore schedule it after a failed probe job and expose
the already-published job outputs for current-run issue management. Once the
sink finishes, the failed probe job still makes the workflow conclusion
`failure`, which is the threshold input for the next run.

A separate terminal step is preferred over removing `continue-on-error` from
the probe because immediate probe failure could prevent the current
observation from reaching the alarm sink.

## Risks / Trade-offs

- [A future edit moves the propagation step before output publication] →
  Structural tests require it to be the final probe-job step after the
  identified output-producing step.
- [A future edit tolerates the propagation failure] → Structural tests require
  the terminal step not to set `continue-on-error`.
- [A missing or unexpected output value concludes green] → Existing probe
  scripts deterministically publish green or red before returning; this change
  intentionally propagates only the published red state requested by the
  controller contract.

## Migration Plan

Deploy both workflow edits together. A red run begins producing a failed
workflow conclusion immediately; the following red run can then cross the
existing threshold. Rollback is the inverse workflow edit and requires no data
migration.

## Open Questions

None.
