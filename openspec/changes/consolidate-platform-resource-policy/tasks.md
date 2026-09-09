## 1. Shape and existing truth

- [x] 1.1 Diagnose the live ten-start refusal, record owner acceptance boundary and independent review, and adapt the candidate to reuse existing stores without migration or new authority.
- [x] 1.2 Verify/sync/archive landed run-usage-budgets bookkeeping, preserving its actual current behavior and limitations.

## 2. Bounded platform correction

- [x] 2.1 Remove both workspace jobs-count refusal gates and obsolete parameters; retain observations and add regression tests proving more than ten operations while byte/storage/lock controls still refuse correctly.
- [x] 2.2 Add non-mutating owner-scoped resource-status observations with missing/corrupt/symlink/privacy/coverage tests; do not claim global capacity or total storage where unmeasured.

## 3. Ship and prove

- [ ] 3.1 Run focused Windows and Linux-oracle tests, rebuild plugin parity, obtain independent exact-head review and required CI, then deploy with authenticated canary and SHA containment.
- [ ] 3.2 Coordinate rendered app-owned continuation/acceptance, record exact scope and organic follow-up, sync shipped specs and archive this bounded correction; keep wider Patches open for remaining platform issues and owner acceptance.

Local evidence (2026-09-08, Windows, uncommitted candidate):
`python -m pytest -q tests/test_workspace_pool.py tests/test_workspace_effector.py tests/test_run_usage_budgets.py tests/test_engine_mcp_hardening.py tests/test_engine_mcp_server.py tests/test_resource_usage_status.py tests/test_api_status.py tests/test_get_status_primitive.py`
reported 390 passed, 9 skipped. This does not satisfy the Linux gate.

The local oracle could not start because Docker Desktop crashed initializing its
inference socket, before any test execution. Commander authorized the existing
Linux CI alternative without weakening tests or repairing the host. The relevant
workspace/status suites are not in `.github/heavy-test-files.txt` or quarantine;
their POSIX/symlink tests do not require bubblewrap. `tests.yml` workflow_dispatch
checks out the selected ref on Ubuntu/Python 3.11 and uploads JUnit. Use pinned
baseline and candidate refs, verify the executed SHAs and compare relevant
test outcomes/skips. Required PR CI remains an additional landing gate. This is
Linux evidence for this change, not a claim that sandbox-jail tests ran.
