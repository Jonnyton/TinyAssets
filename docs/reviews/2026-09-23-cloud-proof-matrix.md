# Cloud admission: copied-setting regression proof

2026-09-23 UTC. Candidate base `219af0aa`, branch
`codex/cloud-admission-proof-matrix`. Scope: three test modules, this review,
and correction of stale planning wording. No runtime, permission, schema,
workflow or account change; no skip, xfail or quarantine added.

## Independent review

Claude Opus authored the tests in dispatch19738 (311s, exit0), then added
matching admitted controls in dispatch5183 (333s, exit0). Codex independently
read the complete diff and exercised both fixed and genuinely unfixed code.
**Codex verdict: APPROVE the test implementation.** Every existing negative
assertion is preserved; four admitted tests now run plain and with copied
settings. The registration case already has a matching positive.

The follow-up's final stop-hook recap mistakenly described its own dispatch as
another running builder. The authoritative tool result is terminal; there is no
second controls implementation to reconcile. Its unexecuted import-error
prediction was disproved by the baseline below, not used as evidence.

## What is covered

The copied set is the daemon's explicit non-secret `environment:` block in
`deploy/compose.yml`, plus hostname/service labels and socket hostname mocks.
Path variables are deliberately rerooted into pytest temporary storage outside
the repository. No literal `/data` equivalence, secret `env_file` contents,
credential custody, real metadata access, or production authority is claimed.

| Matrix row | Executable evidence | Scope |
|---|---|---|
| 1 claim | `test_unadmitted_direct_claim_assigned_claims_nothing` | Direct claim, no optional authority callback; persisted task remains pending |
| 2 registration | `test_unadmitted_ensure_daemon_runtime_writes_no_cloud_worker_row` | Persisted-row refusal |
| 3 startup/provider | Existing startup sentinel tests and foreground/served refusal tests | No listener/provider call/receipt/reservation on refusal |
| 4 existing registration | `test_existing_runtime_row_matches_nothing_for_an_unadmitted_process`, `test_unobserved_process_matches_no_runtime_row` | Existing row grants no authority to an unadmitted or unresolved reader |
| 5 copied settings | Six negative cases spanning claim, registration, foreground provider, served provider, existing-row eligibility, and startup | All execute against old and fixed code; admitted controls share the same settings |
| 6 recovery | Existing `test_cloud_recovery_admission.py` | Assigned-consumer tests; watchdog integration is not established by this slice |
| 6b retirement | [retirement proof](2026-09-23-cloud-retirement-admission.md) | Separate PR3922, not newly exercised here |
| 7 ingress | Existing origin-client refusal tests in the startup module | Fixture request, not a live tunnel-forwarded negative |
| 8 admitted positive | Registration plus four parameterized admitted controls | Allowed behavior preserved with and without copied settings |
| 9 free-user answer | None in this slice | Live acceptance remains outstanding |

The older design matrix and storage summary mentioned instance/boot-epoch
binding, contradicting the accepted Enforcement sites (B) paragraph and task7.
Those two stale lines are aligned with (B): no new epoch schema, no anti-replay
claim from an unauthenticated UUID, and legitimate admitted restarts must work.
The PID-cache test is not stored-epoch replay proof and was not run in this
cohort. This correction does not substitute a PID test for a missing property.

## Measured fixed/unfixed comparison

Windows, Python3.14, September23. Three modules:
`test_cloud_only_admission_regressions.py`,
`test_cloud_only_provider_admission_regressions.py`,
`test_cloud_admission_serving_startup.py`.

- Builder: **41 passed, 0 skipped, 6.25s**.
- Independent Codex: **41 passed, 0 skipped, 6.00s**, nine dependency warnings;
  Ruff clean. Command: `python -m pytest -q <three modules> -p no:randomly
  -p tests.skip_census_plugin --basetemp <external temp>
  --junitxml <external XML> --skip-census-out <external JSON>`.
  Artifacts: `C:/Users/Jonathan/AppData/Local/Temp/ta-matrix-controls-lead-20260923.xml`
  and `ta-matrix-controls-lead-20260923-skips.json` in the same directory.
- Genuine pre-guard base `a468232ce942e489ed9a7a41118f898a851f4da1`, isolated
  detached `wf-cloud-proof-baseline`; only these test files transplanted,
  no production source patched: **7 assertion failures, 9 passes,
  25 deselected, 0 skips, 5.71s**. All modules collected. Six copied-setting
  negatives and the original direct-claim negative fail at missing refusal;
  all selected plain/copied admitted controls pass.
  Command: `python -m pytest -q <three modules> -p no:randomly
  -k 'copied_cloud_labels or existing_registration_and_cloud_labels or
  admitted_direct_claim or admitted_foreground_run_still or
  admitted_background_served_turn_still or admitted_boot_reaches'
  --basetemp <external temp> --junitxml <external XML> --tb=line`.
  Artifact: `C:/Users/Jonathan/AppData/Local/Temp/ta-matrix-controls-baseline-20260923.xml`.

These are local red/green results, not Linux or live boundary proof. Earlier
3921 Linux artifact10730483284 contains96 original admission cases with0skips
across seven modules; it does not cover these new cases.

## Remaining acceptance

Hosted Linux proof for this slice is pending. No Docker Desktop/WSL was started.
Task9 is not complete: watchdog integration and relevant broader matrix proof
must stay explicit. Full cloud credential/routing custody and clean free-only
onboarding are also not established. This test-only change does not authorize
retesting that account or close the whole cloud-only change.
