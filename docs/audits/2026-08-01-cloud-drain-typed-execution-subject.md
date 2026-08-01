# Cloud drain typed execution-subject evidence

Date: 2026-08-01
Environment: Windows 11, Python 3.14
Branch: `codex/cloud-drain-runtime-compositor-20260801`
Change: `activate-custom-agent-runtime-core` task 2.1 prerequisite for PR #2082

## Scope and outcome

The exact owner handoff in PR #2087 assigned the shared activation conversion
to the active cloud lane. This slice adds one immutable `ExecutionSubject`
tuple `(kind, ref, digest)` and makes it the sole activation and claim identity.

- Ordinary Branch activations use `branch_version`, the immutable Branch
  version ID, and its canonical content digest.
- Agent activations use `agent_runtime_manifest` and one reserved automation
  key derived from the private agent-binding ID. Callers cannot supply an
  alternate agent automation alias.
- Activation CAS, rebind, stop, admission, and epoch-2 claim validation bind
  the exact subject kind/reference/digest in addition to epoch, executor, and
  lease.
- The retained `immutable_branch_version` SQL field is a derived compatibility
  projection for Branch rollback only. New authority reads and claims use the
  typed subject; agent rows leave the compatibility field null.
- Legacy stopped activation rows migrate without changing their epoch or
  timestamp. A legacy active row has no trustworthy content digest, so
  migration refuses it transactionally without rewriting the row; an operator
  must stop it under the old owner before upgrade rather than accept a
  fabricated digest.
- The epoch-2 consumer remains dark. No provider invocation, GitHub mutation,
  public connector operation, or tray cutover is enabled by this slice.

## Fresh verification

- RED: `tests/test_execution_subject.py` and the new typed activation tests
  initially failed collection because `tinyassets.execution_subject` did not
  exist.
- `py -m pytest -q tests/test_execution_subject.py tests/test_automation_activations.py tests/test_request_admission_store.py tests/test_branch_tasks_v2.py tests/test_cloud_automation_continuation.py`
  - 187 passed in 17.10 seconds.
  - Covers typed validation, exact kind/ref/digest claim fencing, eight-way
    reserved-key convergence, competing agent-manifest and Branch CAS races,
    stopped-row migration, non-mutating active-row refusal, admission
    persistence, task subject tamper refusal, and the existing cloud
    continuation compositor.
- `py -m pytest -q tests/test_execution_subject.py tests/test_branch_tasks_v2.py tests/test_background_branch_authority.py tests/test_background_branch_authority_service.py tests/test_provider_work_authority.py tests/test_cloud_automation_continuation.py tests/test_request_admission_store.py tests/test_automation_activations.py`
  - 379 passed in 21.91 seconds across the broader activation, admission,
    background-attempt, provider-work, continuation, and migration owners.
- `py -m ruff check <10 changed canonical/test files>`
  - passed; no repository-wide formatting rewrite retained.
- `py scripts/invariants_run.py --check mirror-parity`
  - all 301 canonical files mirror-matched.
- `py -m pytest -q tests/desktop_install/test_packaged_runtime.py tests/test_universe_bundle.py tests/test_pre_commit_mirror_parity.py`
  - 32 passed in 4.18 seconds.
- `openspec validate activate-custom-agent-runtime-core --strict`
  - valid.
- `openspec validate activate-main-universe-spec-drain --strict`
  - valid.
- `git diff --check`
  - passed.

## Remaining gate

This evidence does not complete task 2.1 until the broader authority suite and
an independent exact-head architecture/security review pass. PR #2082 remains
dark and draft. Provider launch/effect reconciliation, epoch-1 fencing,
epoch-2 enablement, phone control, and 24-hour PC-off proof remain subsequent
cloud-drain gates.
