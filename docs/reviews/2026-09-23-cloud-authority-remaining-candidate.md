# Residual cloud authority guards — candidate evidence

September 23, 2026 UTC. Base `16e6f0bf` (runtime `042cdce8`). This is
pre-release evidence, not a deployment or full cloud-boundary completion claim.

## Scope and independent review

Claude Opus authored the provider-service class derivation, non-null descriptor
publication/refresh admission, and Epoch2 cloud activation claim/resume guard.
Codex independently reviewed the source and ran the tests below. Existing live
universe/grant/model/lease/worker checks remain; there is no account-specific
repair or private workflow edit.

Lead findings addressed: transaction ordering is now an event-sequence assertion
for both claim and resume; the vacuous helper/docstring test was removed; the
lifecycle gate is scoped to actual cloud activations and two tray compatibility
controls were added; provider refusal tracing and authority-ledger assertions
now match the actual call path. Descriptor clearing remains revocation with the
existing exact-worker check, not capacity publication.

The follow-up peer exceeded its 480-second budget (terminal exit1), so its
handoff is NOT a final approval. Its retained tool evidence shows 9 failures /
7 passes with its exact runtime delta reverse-applied, restoration of that
delta, and 16 passes with the guards. The lead verified the restored diff and
independently obtained the passing results below. No runtime files were left
reverse-applied. The positive tray controls pass at baseline and with the fix.

## Independent Windows verification

Environment: Windows, `C:/Python314/python.exe`, pytest9.0.2. Only isolated test
data and fake providers; no production service, credentials or real model calls.

Common flags: `-p no:randomly --tb=short`, separate absolute basetemps under
`C:/Users/Jonathan/AppData/Local/Temp`, and JUnit reports in the lead's `output/`.

- Clean baseline `e389505b` (tree equal to `16e6f0bf`):
  `python -m pytest -q tests/test_agent_runtime_provider_execution.py
  tests/test_agent_runtime_provider_call.py tests/test_daemon_registry.py
  tests/test_branch_tasks_v2.py tests/test_fantasy_daemon_epoch2_dispatch.py`
  => 190 passed; health and continuation modules => 14 passed.
- Candidate: the same seven modules plus
  `tests/test_cloud_admission_remaining_authority.py` => **220 passed /25.98s**,
  terminal0 around02:25UTC. JUnit set comparison retains all **204** baseline
  cases and adds **16**, with zero missing baseline cases.
- Candidate: `python -m pytest -q tests/load/test_agent_runtime_cloud_load.py
  tests/test_cloud_only_provider_admission_regressions.py
  tests/test_cloud_only_admission_regressions.py
  tests/test_platform_runtime_provenance.py tests/test_assigned_queue_consumer.py
  tests/test_dispatcher_queue.py tests/test_cloud_automation_continuation.py
  tests/test_distributed_execution_authority.py` => **220 passed /46.47s**,
  terminal0; six dependency deprecation warnings, no failures or skips.
- `python -m ruff check` on the three runtime files and seven changed test files
  => clean. `python packaging/claude-plugin/build_plugin.py` => 499 files,
  import probe `probe-ok`. `git diff --check` => clean.
- `openspec validate cloud-only-runtime-admission --type change --strict` and
  the same with `--type spec` => valid.

Windows is not the Linux oracle. No Docker Desktop or WSL was started; the
personal desktop cannot host platform dependencies. Hosted Linux required
checks must still pass before landing; no quarantine expansion is proposed.

## Release acceptance and rollback

Required next evidence: exact-head independent approval, hosted checks, actual
image/deployment completion, protected deployed-SHA containment, public MCP
handle canary, then one rendered owner-app request exactly
`Retest your workflow checklist`. Never replay an uncertain request blindly.
No new free-account attempt is authorized by this candidate evidence.

If cloud startup/admitted execution fails or the canary becomes red, stop
rollout and use the existing hosted deployment rollback to the last verified
runtime `042cdce8`; preserve canonical data and expected-instance state. No
schema migration is introduced. Never fall back to the founder's desktop.

Credential custody, stale-retirement maintenance authority, complete recovery
matrix and free-user acceptance remain open. The spec update describes this
candidate's guards; it does not archive the broader change or establish any of
those facts. The retirement concern records no demonstrated desktop access to
writable production state.
