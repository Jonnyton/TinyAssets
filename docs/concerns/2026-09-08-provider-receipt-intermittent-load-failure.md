# Intermittent missing provider receipt in the Linux load proof

**Filed:** 2026-09-08. **Verified:** GitHub-hosted Linux JUnit artifacts, as below.

Status: OPEN. Observed in synthetic non-production concurrency tests; current
live user impact and root cause are unproven. This is separate from the bounded
workspace quota/status correction in PR #3560.

## Evidence

On 2026-09-08 PDT / 2026-09-09 UTC, the Ubuntu/Python 3.11 extended suite
reported `PermissionError: agent provider receipt is missing` in
`tests/load/test_agent_runtime_cloud_load.py::test_cross_process_prelaunch_and_expired_claim_recovery_converge`.
The exception is raised by `storage/provider_work_authority.py`'s
`_agent_receipt_for_authority` during the fresh-process `claim`, after
`issue_receipt` returned. The test uses recording doubles, not a live provider.

- Historical run [34300646808](https://github.com/Jonnyton/TinyAssets/actions/runs/34300646808),
  created 2026-09-09 01:48 UTC, predates the workspace patch and contains the
  same failing test and exception in its `junit-heavy-tests` artifact.
- Immediate baseline run [34301938622](https://github.com/Jonnyton/TinyAssets/actions/runs/34301938622)
  initially passed this test (103 other extended failures). The supplemental
  baseline run 34302359138 passed it too.
- Candidate run [34303595238](https://github.com/Jonnyton/TinyAssets/actions/runs/34303595238)
  has 104 extended failures: the same 103 plus this already-observed failure.
- `git diff --exit-code 4c923557 79a4f765 --` over the load test, invocation and
  provider-call/execution test helpers, provider execution service, provider
  authority/store and invocation store shows no source changes in those paths.
- Focused Windows command
  `python -m pytest -q tests/load/test_agent_runtime_cloud_load.py::test_cross_process_prelaunch_and_expired_claim_recovery_converge`
  passed once in 16.93 seconds. This does not establish Linux correctness.

Artifacts were downloaded with `gh run download <run> --name junit-heavy-tests`;
JUnit was compared by exact test id and exception. No test was quarantined,
skipped, edited or retried until green to excuse an introduced failure. One
baseline-only heavy-job rerun was dispatched before historical evidence was
found; it is supplemental, not needed to establish that this predates PR #3560.

## Next verification

Reproduce on Linux with the unchanged provider-runtime path and capture issued
receipt identity, database identity and transaction outcome before claim, using
synthetic identifiers only. Test Linux fork/inherited-connection behavior rather
than treating the Windows spawn result as an oracle. Do not call that the cause
until a discriminating reproducer establishes it. Fix through its runtime owner
with cross-family review; do not hide it by changing this workspace patch.
