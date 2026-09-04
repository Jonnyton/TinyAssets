# Workspace sweeper lifecycle — Claude Opus review

**Reviewed:** 2026-09-03

**Environment:** Windows worktree, read-only Claude Opus peer

**Reviewed revision:** `3925102fc62e6e9d211e670eaf50cb3c82c608d7`

**Command:** `python scripts/peer_agent.py claude --model opus --timeout 900
--out docs/audits/2026-09-03-workspace-sweeper-lifecycle-claude-review.md
--prompt-file .peer-review-sweeper-3925102.md`

**Reviewer verdict:** `ADAPT`

The wrapper's final-output file was replaced by the reviewer's later citation
correction after a stop hook rejected its first final message. The complete
structured review was recovered from the same Claude CLI session transcript
(`e34d997c-eba8-4045-bc42-4575d9624953`). No second review was dispatched.

## Structured findings

1. **DISAGREE_EVIDENCE — blocking.** `_stop_all_workspace_sweepers` took a
   handle snapshot without arming `_WORKSPACE_STOP_REQUESTED` for keys already
   in `_WORKSPACE_RECONCILING`. The production HTTP/SSE/stdio teardown calls
   this all-worker path, so it could return success before an in-flight
   reconciliation published a late worker. The single-worker stop already had
   the required veto.
2. **DISAGREE_EVIDENCE.** The zero-handle clock fast path fixed the observed CI
   error, but a live-handle stop still resolved `time.monotonic` through the
   shared standard-library module. A test's finite global monkeypatch could
   therefore still break cleanup before its monkeypatch fixture unwound.
3. **DISAGREE_CONCERN.** The first zero-handle regression assigned to
   `runs.time.monotonic` directly, temporarily mutating the shared standard
   library module for every process thread.
4. **DISAGREE_CONCERN.** A wedged sweeper remains registered after a timeout,
   so the global test fixture can repeat the same failure and timeout in later
   tests.
5. **DISAGREE_CONCERN.** Successful stop intentionally clears the reconciled
   marker, allowing a restart-in-place to rerun startup reconciliation. The
   missing stop-all veto made that behavior especially risky during teardown.

The reviewer independently agreed that publication implies a started thread;
no lifecycle lock is held across join; self-stop and stale-stopper identity are
safe; fork children replace inherited lock and registry state; workers retain
their injected sweep callable; production cadence is unchanged; and serving
teardown orders scheduler, sweepers, then writer barrier.

## Disposition

Implementation revision `785e8671297e96210c2e4eee82a24efbb4fe847d`
addresses findings 1–3:

- Stop-all now arms the startup veto for every same-process reconciling key
  while holding the lifecycle lock, before it snapshots workers. A
  deterministic blocked-reconciliation test proves no late worker or stale
  reconciled state can survive cleanup.
- The sweeper lifecycle owns a module-local monotonic callable captured at
  import, and both deadline reads use it. A live-worker regression patches the
  shared `time.monotonic` and proves shutdown remains successful.
- The empty-stop regression patches only that module-local lifecycle callable
  inside a bounded context, so the test no longer mutates the process clock.

Finding 4 does not change code: unregistering a thread that is still alive
would recreate the original cross-test leak and let it call later tests'
monkeypatches. Repeated loud failure is safer than pretending the worker is no
longer owned. Finding 5 is the documented restart-in-place behavior; the
blocking teardown interaction is removed by finding 1's veto.

Focused verification on 2026-09-03:

- `tests/test_workspace_run_wiring.py`: 35 passed.
- The two formerly failing MCP latency tests plus workspace lifecycle and
  effector suites: 173 passed, 2 skipped.
- Ruff passed for the changed canonical runtime and lifecycle tests.
- Plugin build import probe passed; all 390 canonical files mirror-matched.
