# Workflow checklist deployment loop

## Founder direction, 2026-09-04

Deploy the current round of generic platform fixes, then send the existing
TinyAssets webapp conversation exactly:

> Retest your workflow checklist

Use the bound agent's rendered response to identify the next platform fix;
review, merge, deploy, and repeat until its checklist passes. Do not add
coaching or directly manage the user's workflow definitions or universe state.
This supersedes the previous instruction to stop before sending a live retest.

## Current round

The workspace effect dispatcher did not forward the node timeout into pool
admission, leaving both create and checkout on the zero-wait default.
The fix forwards that budget into one retry after the initial admission probe
and reconciliation sweep. The existing transactional pool waits only on locks.

Windows Python 3.14 verification, 2026-09-04:

- `python -m pytest -q tests/test_effects_at_node_time.py tests/test_workspace_effector.py tests/test_workspace_pool.py`: 243 passed, 3 skipped.
- Broader workspace/runtime selection: 194 passed, 22 skipped.
- Ruff, plugin import probe and mirror parity passed.
- `python scripts/linux_oracle.py -- -q tests/test_effects_at_node_time.py tests/test_workspace_effector.py tests/test_workspace_pool.py`: could not start because Docker Desktop's Linux engine was unavailable. Startup then failed at its inference socket. Linux CI remains the landing gate.
- Claude review: APPROVE; recovered from its completed transcript because the wrapper retained only a closing message. Reviewer independently ran 140 tests (2 skipped).

Latest user checklist evidence was against `b1ec544c` around 21:29 UTC,
before terminal lock release deployed as `2102d630` at 21:33 UTC:
heartbeat, missing-input preflight and workspace happy path passed;
sequential and parallel probes were running; concurrent workspace refused;
external delivery reached a stale destination and received HTTP 404.
The intentional failure probe v3 is excluded.
