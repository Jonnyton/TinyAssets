---
severity: P2
title: A cancelled deploy has never been observed recovering
filed: '2026-09-26'
summary: 'the 960s-over-900s arithmetic is FIXED (#4039 took the drain to 180s and the test now models both converges); what remains is that SSH cancellation mid-run is untested, the EXIT trap cleans scratch files rather than recovering a part-way bundle install, and the canary rollback shares the same job budget'
---

# Drain and rollback allowances exceed the deployment job budget

**Filed:** 2026-09-26
**Verified:** 2026-09-26, static review of PR #4039 worktree on Windows.
**Re-verified:** 2026-09-26, same worktree, after acting on the finding. **The
arithmetic half is FIXED and the remainder is not** — see "What is left" below.
The `**Source**` block stays verbatim, so read it as the state at review time,
not as today's numbers.
**Severity:** P2 (was P1; the overrun itself is gone)

`.github/workflows/deploy-prod.yml:68` sets 15 minutes; line 345 passes
HEALTH_TIMEOUT=180. `deploy/deploy_fail_safe.sh:1306,1313` converges and checks the
candidate; lines 1349,1359 repeat for rollback. `health_ok` starts a fresh
deadline at line 251. `deploy/compose.yml:96` now permits 300s per container stop.
Even two 290s waits plus the health allowances total 940s. Pull, import (up to
90s at line 1180), validation, snapshot, convergence, and canary need additional
time. Image build is a separate workflow (`deploy-prod.yml:23-25`), so it should
not be counted here.

The new test `test_the_bound_fits_inside_the_deploy_job` checks only one grace
against half a hardcoded job budget; it does not reserve recovery time. The
external canary rollback at workflow lines 374-391 also shares the job budget.
Only temporary-bundle cleanup is registered in the shell EXIT trap (line 405),
not transactional recovery on interruption. Exact remote-process survival on
SSH cancellation was not tested and must not be asserted from this review.

Make the workflow and host-operation timeout policy cover the full forward and
recovery path, and test cancellation/recovery. This review did not deploy or
change production.

## What was fixed (2026-09-26, PR #4039)

The grace came down from 300s to **180s** and the test was rewritten to model the
worst case the finding describes, rather than half a budget:

    2 x (180s drain + 180s health) + 120s overhead = 840s <= 900s

`tests/test_deploy_drains_in_flight_turns.py::test_the_worst_case_deploy_still_fits_inside_the_job`
now derives `timeout-minutes` and `HEALTH_TIMEOUT` from the workflow instead of
hard-coding them, counts BOTH converges, and reserves overhead. Restoring 300s
turns it red (mutation-scored). A second test keeps the grace under
`tinyassets-daemon.service`'s 200s `TimeoutStartSec`, which the same finding
surfaced.

## What is left, and why this file stays open

None of these is affected by the 180s change; all three predate it and are
properties of the deploy path, not of the grace:

- **Cancellation is untested.** Nobody has established what happens on the
  droplet when Actions terminates the SSH step mid-run. The review was explicit
  that remote-process survival must not be asserted from a static read, and it
  still has not been measured.
- **The EXIT trap is not transactional** (`deploy/deploy_fail_safe.sh`, the
  temporary-bundle cleanup): it removes scratch files, it does not recover a
  part-way bundle install.
- **The external canary rollback shares the same job budget** (`deploy-prod.yml`,
  the canary/rollback steps), so the 120s overhead reserved above is an estimate
  rather than a measured reservation.

Resolve this file when a cancelled deploy has been observed leaving the box in a
recoverable state, with the date and the command that showed it.
