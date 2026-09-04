**Measured on this host (same Python 3.11), confirming §1's recommended fix:**

- Uncancelled watchdog, clean exit path → `exit=0`, returns in `0.0s`. `cancel_dump_traceback_later()` buys nothing on the success path.
- Uncancelled watchdog, stalled `atexit` handler → `Timeout (0:00:01)!`, thread stack dumped, `exit=1`. The watchdog **does** fire during interpreter teardown when left armed.

So the finding is no longer inferential: deleting `faulthandler.cancel_dump_traceback_later()` at `tests/desktop_install/windows_lifecycle_supervisor.py:556` extends the bound across teardown at zero cost to a passing run, and keeping it is what strands the exact path the spec claims to cover and the concern doc names as a suspect.

Verdict stands: **CHANGES_REQUESTED** — (1) the `finally` cancel at `:556` disarms the watchdog before the teardown the spec asserts it bounds; (2) the regression at `test_release_workflow.py:375` stalls inside `process.wait()` (`:453`) so it cannot discriminate the new whole-lifetime contract; (3) lower severity, `timeout-minutes: 10` sits at job level and so covers the preamble, leaving the 420/600 ordering non-structural (measured 13s preamble on the incident run, so ~167s of real slack today).

I made no edits and no commits, per the brief. The remaining dispatch items — `voice-capability-final-review.md`, `2026-09-04-voice-capability-live-fix-claude.md`, `workspace-contention-wait`, `windows-lifecycle-outer-watchdog` — are explicitly out of scope for this brief ("ignore every other active or stale lane"), so I left them untouched rather than dispositioning them.
