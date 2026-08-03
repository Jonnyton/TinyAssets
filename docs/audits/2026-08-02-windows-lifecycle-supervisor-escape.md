# Windows lifecycle supervisor retained-handle repair

Freshness: 2026-08-02, GitHub Actions and Windows local worktree. Landed by PR #2164 at merge commit `0b761784`; exact reviewed head `909c955b`.

## Incident

Desktop release runs `30764595380` and `30766508516` entered `Install, probe, repair, and uninstall exact CI artifact` and were cancelled by GitHub after fifteen minutes. The latter was the post-merge evidence run for custom-agent command PR #2160. Both had a configured 300-second Python supervisor deadline and ten-minute job timeout; neither retained a downloadable job log or supervisor verdict. Successful #2155 run `30765168694` completed the same lifecycle step in 24 seconds.

## Reproduced boundary and cause

The archived #2110 design and current `desktop-release-lifecycle-ci` spec require lifecycle stdout/stderr to go to private files so an escaped descendant cannot retain a supervisor or workflow output handle. Current code had drifted back to `subprocess.PIPE` plus two daemon drain threads. A new Windows regression starts a self-terminating synthetic descendant with inherited handles, gives it a unique completion marker, then exits the PowerShell lifecycle parent.

Against the old implementation, the supervisor waited for descendant pipe EOF and the test failed its three-second margin at 4.56 seconds; a static contract test also failed on the two `subprocess.PIPE` uses and `_drain_stream`. This proves the missing parent-exit/retained-handle boundary. Because historical cancellations retained no stack or log, it does not identify the exact real installer descendant or prove that this was the only cancellation mechanism.

## Repair

The supervisor now passes its two private binary capture writers directly to the PowerShell child. It owns no pipe, drain thread, or EOF join. After the exact root exits or bounded tree cleanup completes, it freezes each observed file size and replays only the configured prefix through an independent read handle. A surviving descendant may retain the temporary file, but cannot retain the supervisor/workflow output pipe or delay the verdict; cleanup failure remains a warning.

## Local evidence

- RED: retained-handle integration failed at 4.56 seconds; the no-EOF-dependency contract failed on `subprocess.PIPE` and `_drain_stream`.
- GREEN: the identity-safe retained-descendant test passed with supervisor return under three seconds and self-termination proof in 5.76 seconds total; captures are scoped to its pytest temp directory.
- Full desktop-install suite: 83 passed in 8.72 seconds on Windows at exact reviewed head `909c955b`.
- Ruff format/check passed for the supervisor and release-workflow tests.
- Strict OpenSpec validation passed for `repair-windows-lifecycle-supervisor-escape`.
- `git diff --check` passed.

## GitHub terminal evidence

Fresh independent review approved exact head `909c955b6036f4de6e567e8af5c0856b3fda1ff3`. Desktop release run `30768296827` completed successfully at that head. Its exact `test-unsigned-windows-install` job `91551392522` completed in 46 seconds, with the lifecycle step finishing in about 27 seconds. The supervisor replayed lifecycle-child notices for initial install, packaged health probe, same-version repair, and uninstall, then emitted its own `stage=supervisor.exiting` terminal checkpoint and returned success. All three platform builds and sign-and-verify jobs passed; publication remained skipped. PR #2164 then merged through the protected auto-merge path.
