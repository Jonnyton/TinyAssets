# Windows lifecycle supervisor retained-handle repair

Freshness: 2026-08-02, Windows local worktree based on current main `f4463292`. Exact PR/CI and reviewed-head evidence remain pending.

## Incident

Desktop release runs `30764595380` and `30766508516` entered `Install, probe, repair, and uninstall exact CI artifact` and were cancelled by GitHub after fifteen minutes. The latter was the post-merge evidence run for custom-agent command PR #2160. Both had a configured 300-second Python supervisor deadline and ten-minute job timeout; neither retained a downloadable job log or supervisor verdict. Successful #2155 run `30765168694` completed the same lifecycle step in 24 seconds.

## Reproduced boundary and cause

The archived #2110 design and current `desktop-release-lifecycle-ci` spec require lifecycle stdout/stderr to go to private files so an escaped descendant cannot retain a supervisor or workflow output handle. Current code had drifted back to `subprocess.PIPE` plus two daemon drain threads. A new Windows regression starts a synthetic descendant with inherited handles, records its exact PID for bounded cleanup, then exits the PowerShell lifecycle parent.

Against the old implementation, the supervisor waited for descendant pipe EOF and the test failed its three-second margin at 4.56 seconds; a static contract test also failed on the two `subprocess.PIPE` uses and `_drain_stream`. This proves the missing parent-exit/retained-handle boundary. Because historical cancellations retained no stack or log, it does not identify the exact real installer descendant or prove that this was the only cancellation mechanism.

## Repair

The supervisor now passes its two private binary capture writers directly to the PowerShell child. It owns no pipe, drain thread, or EOF join. After the exact root exits or bounded tree cleanup completes, it freezes each observed file size and replays only the configured prefix through an independent read handle. A surviving descendant may retain the temporary file, but cannot retain the supervisor/workflow output pipe or delay the verdict; cleanup failure remains a warning.

## Local evidence

- RED: retained-handle integration failed at 4.56 seconds; the no-EOF-dependency contract failed on `subprocess.PIPE` and `_drain_stream`.
- GREEN: the identity-safe retained-descendant test passed with supervisor return under three seconds and self-termination proof in 5.76 seconds total; captures are scoped to its pytest temp directory.
- Full desktop-install suite: 83 passed in 8.92 seconds on Windows.
- Ruff format/check passed for the supervisor and release-workflow tests.
- Strict OpenSpec validation passed for `repair-windows-lifecycle-supervisor-escape`.
- `git diff --check` passed.

## Remaining gate

This repair is not yet proven against the exact unsigned installer lifecycle in GitHub Actions. OpenSpec task 2.2 remains open. The PR must receive a supervisor-authored terminal Windows lifecycle verdict before merge; a GitHub cancellation, missing log, or merely green Linux/macOS build is a failure of this acceptance gate. Fresh independent exact-head review is also required.
