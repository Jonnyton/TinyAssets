# Admitted stale-fleet retirement — red/green evidence

**Date:** 2026-09-23
**Change:** `cloud-only-runtime-admission` (task 8, still partial)
**Base tree:** `fab37a6cf1c2dd341555ffcbe806690f320b9895`, worktree
`wf-cloud-retirement-admission`
**Environment:** Windows 11, CPython 3.14.3 (`3.14.3 tags/v3.14.3:323c59a`),
`pytest` local run. **No hosted, deployed, Linux or Docker result is claimed
here.** The Linux proof must come from CI.

Closes `docs/concerns/2026-09-23-runtime-reconcile-retirement-ungated.md`
(deleted in the same change; its row is removed from `docs/concerns/README.md`).
The concern owed a gate-vs-document decision. **Decision: gate**, at the write
boundary rather than at `main`, so an in-process caller gets the same refusal.

## What changed

`tinyassets/runtime_reconcile.py::_apply_plan` now calls
`require_process_cloud_admission(surface="stale fleet retirement")` as its first
statement — before `RequestAdmissionStore(base_path)` is constructed and before
any transaction opens. `main`'s existing sanitized error handler gained
`PermissionError`, so the refusal is reported as `{"error": ...}` on stderr with
exit 2 instead of a traceback.

Unchanged on purpose: the read-only dry run stays ungated; the reviewed-plan
digest and both exact-count fences stay in force; the per-row CAS fences stay in
force; the explicit-cancellation semantics are unchanged.

## Shape this encodes

*Automatic recovery* and *explicit operator retirement* are different acts and
the docs now say so separately. Automatic recovery (watchdog, assigned-consumer
startup/poll) preserves pending work when no admitted successor exists — that
rule is not weakened anywhere in this slice. Explicit retirement is a
digest- and count-confirmed cancellation of exactly the approved stale tasks; it
assigns nothing, so it is never a successor, but it writes, so it is admitted.

## Commands and measured results

All three runs used the same invocation shape, differing only in `--basetemp`:

```
TMPDIR=/c/Users/Jonathan/AppData/Local/Temp/ta-pt \
python -m pytest -q tests/test_runtime_reconcile.py \
  tests/test_cloud_recovery_admission.py \
  --basetemp=C:/Users/Jonathan/AppData/Local/Temp/ta-pt-<phase>
```

| Phase | Tree | Result |
|---|---|---|
| Baseline | `fab37a6c`, nothing modified | **14 passed** |
| Red | new tests + test-only CLI seam, `tinyassets/` **unchanged** | **2 failed, 15 passed** |
| Green | after the two production edits | **17 passed** |

`python -m ruff check tinyassets/runtime_reconcile.py tests/test_runtime_reconcile.py tests/test_cloud_recovery_admission.py`
→ `All checks passed!`

`python packaging/claude-plugin/build_plugin.py` → staged 499 files, `probe-ok`.

### The two that were red

Both are in `tests/test_cloud_recovery_admission.py`:

- `test_unadmitted_apply_plan_refuses_before_any_store_or_write` — calls
  `_apply_plan` directly under an injected UNADMITTED observation against a real
  stale fixture (one committed cloud task, one provisioned cloud runtime).
  `RequestAdmissionStore` and `retire_runtime_instance_if_stale` are replaced
  with raisers, so reaching either is a failure rather than a silent pass. The
  post-assertions re-read both real rows from SQLite.
- `test_unadmitted_cli_apply_exits_two_with_sanitized_json_and_no_mutation` —
  drives `main` with a correct digest and both correct counts. At baseline it
  returned **0 and mutated the database**: that is the concern's finding
  reproduced executably, not a synthetic red. It also asserts no stdout, no
  `Traceback` in stderr, and that the refusal string contains no data path, task
  id or instance id.

### The positive that passed at baseline

`test_unadmitted_cli_dry_run_still_reports_the_plan_and_mutates_nothing` is a
guard against over-gating, so it passes in all three phases by design.

### Preserving the subprocess CLI positive

`tests/test_runtime_reconcile.py::_run_reconciler` still spawns a real
subprocess. A spawned child inherits no monkeypatch and, by design, no cached
verdict, so the admitted CLI positive would have gone red for the wrong reason.
The seam is one explicit test-only bootstrap line that calls the existing
`tests.cloud_runtime_fixture.install_admitted_observation()` — the same injected
fake resolver the in-process `cloud_runtime` fixture uses — before invoking
`main`. No environment variable (an env switch is reachable from a real
deployment's `env_file`; importing `tests` is not), no global autouse fixture,
no network, no credential. Subprocess coverage is not removed and the existing
mismatched-digest, wrong-count and missing-argument negatives are untouched.

## Independent lead verification and review

Codex independently reviewed the Claude-authored runtime/tests on September23,
2026 UTC. The earlier shape reviewer was **Claude Opus**, not Codex; its ADAPT
verdict corrected the recovery classification before implementation. It was a
shape review, not exact-head implementation approval. Its original artifact is
`output/cloud-recovery-boundary-review-result.md` in the lead checkout (not
shipped in this candidate). The builder's mistaken
family attribution is corrected here rather than adopted.

The guard precedes every apply write/store construction, and the shared resolver
is outside transactions. Existing CLI digest/count and per-row CAS fences remain.
RequestAdmissionStore.__init__ only stores configuration; planning uses read-only
connections. Direct negative checks both forbidden calls and preserved real rows;
the CLI negative drives correct digest/counts and verifies no mutation. The
admitted subprocess positive retains actual process isolation via an explicit
test-only injected resolver. No production env bypass or global fixture exists.

Independent Windows command (Python3.14, 2026-09-23 ~03:49UTC):

```
python -m pytest -q tests/test_runtime_reconcile.py tests/test_cloud_recovery_admission.py tests/test_cloud_admission_helper_contract.py tests/test_platform_runtime_provenance.py tests/test_cloud_only_admission_regressions.py tests/test_cloud_only_provider_admission_regressions.py tests/test_cloud_admission_serving_startup.py tests/test_concerns_index_matches_the_directory.py tests/test_mirror_parity_gate.py -p no:randomly -p tests.skip_census_plugin --tb=short --basetemp C:/Users/Jonathan/AppData/Local/Temp/ta-retirement-final-20260923 --junitxml C:/Users/Jonathan/AppData/Local/Temp/ta-retirement-final-20260923.xml --skip-census-out=C:/Users/Jonathan/AppData/Local/Temp/ta-retirement-final-skips-20260923.json
```

**203 passed,0 skipped /13.16s**, five dependency deprecation warnings.
Earlier independent focused and extended runs:21passed and182passed. The census
describes only these runs, not a global platform-skip count. Ruff passed on all
three changed Python files. Initial strict change validation caught wrapped
requirement wording; corrected before release and must pass alongside spec
validation. No test was skipped, relaxed or quarantined to clear this slice.

Lead corrections are documentation only: nominal schedule is not guaranteed
delivery; absent heartbeat is not necessarily stale (unit/container checks
remain); read-only planning may construct adapters before the apply guard.
No production behavior changed in those corrections.

## Remaining release gates and limits

The base is deployment-verified, not merely merged:
[PR3921's public receipt](https://github.com/Jonnyton/TinyAssets/pull/3921#issuecomment-5788453081)
records hosted `deployed_sha.py --assert-contains fab37a6cf1c2dd341555ffcbe806690f320b9895`
and public `--assert-handles` PASS at03:21UTC September23.
[Deploy35813917911](https://github.com/Jonnyton/TinyAssets/actions/runs/35813917911)
completed SUCCESS for that exact merge; re-read via `gh run view` and the public
comment API at04:01UTC. This receipt was external to the candidate checkout;
its absence from the earlier local acceptance doc did not mean no receipt existed.
These facts apply to the base, NOT this candidate or exclusive cloud custody.

Exact-head review receipt, hosted Linux checks, image/deployment, protected SHA
and public MCP handles still gate release. Then send one ordinary rendered
`Retest your workflow checklist`, inspect that original response, and check for
organic use. Neither fixtures nor a served answer prove exclusive cloud custody.

The watchdog comment and release-reconcile classification are source evidence,
not new executable watchdog admission proof. The existing mocked script harness
is tests/test_host_uptime_installers.py::test_installed_operational_entrypoints_invoke_from_runtime;
tests/test_watchdog.py covers a different script. Builder's local harness attempt
stopped at missing flock; no Linux result is inferred. No Docker Desktop/WSL or
production services/credentials were used on the personal desktop.

If admitted execution or the public canary fails after release, use the existing
hosted rollback path to verified fab37a6c, preserving canonical data and expected
instance state. No schema migration; never use a desktop fallback.

Tasks8/9/11/12 are not declared complete. Credential custody, the wider matrix,
clean free-only first-answer acceptance and whole-change archive remain open.
No private workflows or test-user connections were changed.
