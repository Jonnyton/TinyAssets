# Execution-use implementation checkpoint

2026-09-19 UTC, isolated workspace-memory-containment tree. This implements the
accepted Fable85986 ADAPT, not exact-head review or production activation.

The original owner guard remains PID/thread/database-bound. Its single issued,
nonserializable use receipt permits scoped worker operations, not start,
terminalization or release. The owning lock's finally closes new pins and drains
existing ones before registry removal and descriptor/mutex release, including
an exceptional wait. Nested execution scopes reuse the original receipt.

The source-code node pins acquisition through release. The real stdout drain
pins both RPC permission counting and invocation, including its trailing-line
path, with a thread-owned identity-check connection. Terminal FamilyFence
admission remains the effect boundary; lifetime pinning does not reopen it.

## Verification

Working tree, Linux oracle Python 3.11.16 / git 2.47.3 / bubblewrap 0.12.0:

`python3 scripts/linux_oracle.py -- -q tests/test_run_execution_use.py
tests/test_run_execution_lock.py tests/test_workspace_execution_use_lifecycle.py
tests/test_workspace_family_execution_guard.py
tests/test_workspace_family_transitions.py tests/test_branch_runner.py
tests/test_prepared_run_worker.py tests/test_run_provider_session.py`

Result: **138 passed, zero skips, 43.43s**. Plugin mirror rebuilt; focused ruff
and git diff --check passed. Tests include spawned-process guard contention,
forked/forged/wrong-database receipts, exceptional retirement wait, real sandbox
RPC drain after timeout, cancellation, trailing line, actual parallel LangGraph
sibling failure, and nested no-remint/no-retire behavior. Late family dispatch
is refused while owner exit is still waiting; cancellation is already committed.

## Release gates still open

The tests prove contention during late drain and fresh guard acquisition after
drain. They do **not** yet prove actual managed resume succeeds afterward: that
requires integrated kernel retirement and epoch transition. Runtime workspace
allocator, provisioning/broker membership, typed producer-leaf retirement,
dead-worker/outbox cleanup, fixed bootstrap activation and actual browser work
remain open. Existing production AS, user and capabilities are unchanged.
The WSL kernel diagnostic is not production-kernel compatibility proof.
