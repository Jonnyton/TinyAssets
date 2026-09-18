# Cross-user accepted-delivery runtime integration

September 18, 2026 UTC. Isolated branch `codex/cross-user-delivery-mvp`, based
on current main. Selectively integrated only canonical runtime/tests from the
three September 9 implementation units and their directly related approved
design/review artifacts. No private workflow was edited.

The internal runtime submits an existing reserved attempt through the normal
executor in a fresh Context. Under the attempt's OS lock it revalidates current
receiver admin/graph ownership and the pinned snapshot, persists execution-start
before any provider work, binds the receiver's provider explicitly, invokes the
shared prepared-run worker, then publishes only a safe terminal receipt. Ordinary
run recovery happens before boot dispatch; the existing maintenance loop runs
subsequent passes. An executing attempt without a live lock becomes interrupted,
never automatically replayed. No caller-supplied identity or sender context is
copied into receiver execution.

## Verification

`python -m pytest -q tests/test_receiver_projection.py tests/test_receiver_links.py
tests/test_delivery_reservations.py tests/test_delivery_attempts.py
tests/test_prepared_run_worker.py tests/test_run_transaction_insert.py
tests/test_delivery_runtime.py tests/test_webhook_delivery_proof.py`

- Windows Python 3.14: 155 passed, 40 dependency deprecation warnings, 34.10s.
- Native WSL Docker through `scripts/linux_oracle.py --` with that exact test
  selection: 155 passed, no skips, 35.86s; Python 3.11.16, git 2.47.3,
  bubblewrap 0.12.0. Docker Desktop's pipe was absent; the existing native engine
  was used without installing/restarting a service.
- Ruff on changed canonical runtime and seven delivery test files passed.
- Plugin build staged 451 files and its import probe passed; diff check passed.
- OpenSpec strict validation passed. All ten proposed public action verbs
  passed `check_primitive_exists.py action <verb>` against origin/main.

Tests use real graph execution, SQLite, executor threads and OS locks. Only the
provider is deterministic. Separate assertions cover explicit receiver provider
binding, fresh request context, stale sender context exclusion, restart before
execution, interrupted started work, live lock exclusion, revoked receiver admin,
safe processing failures, and unsupported file-reference envelopes.

## Remaining gates and scope

This proves internal execution of previously accepted structured occurrences.
It does not yet expose public intake, output mapping/provenance, owner-directed
retry, public/served management or receipt actions. Runtime file staging,
immutable run-owned artifact bundles, exact-byte chunk reads and accounting remain
unimplemented. File delivery is not promised or represented as ordinary JSON.
Public/served wiring, exact-head independent review, CI, deployment and two-user
rendered acceptance remain open; the full OpenSpec change is not complete.
