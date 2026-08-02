## Context

The archived `bound-windows-installer-lifecycle-ci` design chose a stdlib Python parent and explicitly required the PowerShell child to write to private named capture files. Current implementation drifted: it launches the child with `stdout=subprocess.PIPE` and `stderr=subprocess.PIPE`, then owns two daemon drain threads that wait for pipe EOF before capture is complete.

Successful run `30765168694` completed the lifecycle step in 24 seconds. Runs `30764595380` and `30766508516` instead remained in that step for exactly fifteen minutes and were cancelled by GitHub; neither retained a log. The current 300-second `Popen.wait` deadline therefore did not produce its required verdict. The strongest bounded hypothesis is the untested parent-exit case: an installer descendant can inherit a pipe writer after the PowerShell root exits, leaving the supervisor's drain/shutdown path dependent on descendant EOF. This exactly contradicts the archived decision and current spec. A failing Windows regression must confirm the escape before production code changes.

## Goals / Non-Goals

**Goals:**

- Reproduce the supervisor escape when a lifecycle parent exits but a descendant retains inherited output handles.
- Make supervisor completion independent of EOF from every lifecycle descendant.
- Preserve fixed-horizon, byte-capped diagnostic replay and bounded exact-root/tree cleanup.
- Produce a terminal Windows CI verdict before GitHub's fallback cancellation.

**Non-Goals:**

- Change the installer, tray, product runtime, signing, publication, or clean-machine acceptance contracts.
- Diagnose which real installer descendant escaped in logless historical runs.
- Treat unsigned CI as customer installation or organic-use evidence.

## Decisions

### 1. Restore direct private-file capture

Pass the two private binary capture writers directly to `subprocess.Popen` for stdout and stderr. Remove supervisor-owned pipe readers and drain threads. The supervisor waits only for the exact PowerShell root deadline, performs bounded cleanup when needed, then reads each capture through an independent file handle up to a fixed observed-size horizon.

This matches the archived design and makes an inherited descendant handle refer only to a temporary file, never a supervisor or GitHub workflow pipe. The supervisor does not wait for file EOF and can return even if a descendant still holds or writes the file.

Alternative: keep pipes and add more thread joins, handle closes, or interpreter-exit workarounds. Rejected because the authority boundary would still depend on Windows pipe/daemon-thread behavior, the exact failure class that escaped twice.

### 2. Prove the missing parent-exit case

Add a Windows-only regression lifecycle that starts a quiet descendant with inherited standard handles, records its exact PID, and exits successfully. Run the supervisor beneath an outer test deadline. The test must fail against the pipe/thread implementation, must always terminate only the recorded synthetic descendant in cleanup, and must pass when the supervisor returns without waiting for descendant EOF.

Retain the existing noisy hung-root regression. Together they cover both sides: a root that never exits and a root that exits while an inherited handle survives.

### 3. Preserve bounded replay, not EOF completeness

Capture replay remains a prefix of at most the configured byte cap from the observed size at verdict time. Later descendant writes are deliberately excluded. A truncation warning reports the replay cap and the observed lower bound. Best-effort temporary-file deletion remains subordinate to returning the verdict.

## Risks / Trade-offs

- **An escaped descendant keeps writing its private file** → replay and supervisor completion stay bounded; the workflow runner remains defense-in-depth process cleanup, and deletion failure is only a warning.
- **Direct file capture loses live output** → existing behavior already delays replay until verdict; phase names and PIDs remain in the captured prefix.
- **The hypothesis is wrong** → the RED regression must demonstrate the current escape before implementation. If it does not, stop and gather a different boundary reproduction instead of changing production code.
- **The job is cancelled externally** → exact supervisor checkpoints and terminal CI status remain required; an external cancellation is not counted as a repaired pass.

## Migration Plan

1. Land the parent-exit/retained-handle RED regression on Windows.
2. Replace pipe/drain ownership with direct private capture handles and make the regression GREEN.
3. Run focused Windows/non-Windows tests, strict OpenSpec, lint, and independent exact-head review.
4. Push a PR and require its exact unsigned Windows lifecycle job to return success or a supervisor-authored bounded failure before merge.

Rollback is a commit revert; signing and publication remain gated and unchanged.

## Open Questions

The exact real installer descendant is unknown because GitHub retained no cancelled-run log. The repair does not require that identity if the missing inherited-handle boundary is reproduced and the same CI gate terminates independently afterward.
