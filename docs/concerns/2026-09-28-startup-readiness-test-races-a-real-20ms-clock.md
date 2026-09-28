---
severity: P3
title: An engine startup-readiness test races a real 20ms clock
filed: '2026-09-28'
summary: '`test_invalid_route_never_probes_or_connects` gives the route waiter a real 20ms budget, so a slow first authority read exhausts it before the supervisor wake and `wakes == 1` sees 0; it failed as a NEW failure on PR #4069, which touches no Python'
---

# An engine startup-readiness test races a real 20ms clock

**Severity:** P3 · **Filed:** 2026-09-28 · **Verified:** 2026-09-28 against `origin/main`
a9384000 (Windows, local) and CI run 36302245122

## What is wrong

`tests/test_engine_startup_readiness.py::test_invalid_route_never_probes_or_connects` calls
`_open(0.02)` without the `startup_clock` fixture, so `wait_for_engine_mcp_route`
(`tinyassets/engine_mcp_http.py:76`) runs against the real event-loop clock. The loop checks
`engine_tools_authorized` (a database read) and then `remaining = deadline - loop.time()`. If that
first read takes longer than 20ms, the waiter returns `None` before it reaches `event.set()`, and
the test's `supervisor.wakes == 1` sees 0.

The `startup_clock` fixture in the same file exists for exactly this reason ("The 20ms contract
must not require filesystem reads to finish in 20ms"); two sibling tests use it, this one does not.

## Evidence

- CI run 36302245122 (PR #4069, 2026-09-27), shard 1/6:
  `FAILED ...test_invalid_route_never_probes_or_connects[change0] - assert (0 == 1)`, counted as
  the one NEW failure. The PR changed only a workflow, a runbook and a workflow test.
- Local, 2026-09-28, `python -m pytest tests/test_engine_startup_readiness.py -k invalid_route`:
  `[change0]` failed 2 of 11 runs, always the first parameter (cold first read), on a tree where
  `git diff origin/main -- tinyassets/engine_mcp_http.py tests/test_engine_startup_readiness.py`
  is empty.

## Likely fix

Add `startup_clock` to the test's fixtures so the deadline is logical time, as the sibling tests
do. The assertion itself (one wake, no probe, no list) stays unchanged.
