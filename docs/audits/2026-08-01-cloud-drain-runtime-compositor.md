# Cloud drain runtime compositor evidence

Date: 2026-08-01
Environment: Windows 11, Python 3.14
Branch: `codex/cloud-drain-runtime-compositor-20260801`
Implementation commit: `af9da3a17709b3242d43ea046993871b55555cba`

## Scope

This dark slice replaces the manual test-only assembly between a prepared
cloud continuation and the existing epoch-2/background authority owners.
`PreparedCloudContinuationActivationService` now converges one immutable
definition and prepared continuation into:

1. the exact next active cloud activation epoch and caller-supplied
   server-selected lease identity;
2. one server-authored, deterministic, idempotent epoch-2 request/admission/task;
3. one trusted cloud worker audience and one reserved background attempt.

Every restart revalidates the current prepared continuation, background
binding, requester-owned provider binding, exact GitHub destination grant, and
server-owned daemon identity. Competing leases, revoked provider/destination
authority, missing daemons, a mismatched canonical admission-body digest, or
changed snapshots fail closed. IDs after the
pre-bound request ID are domain-separated hashes of the continuation and exact
activation identity; concurrent callers therefore converge through the
existing SQLite/CAS and logical-attempt replay owners.

The service deliberately does not claim the epoch-2 task, invoke a provider,
mutate GitHub, activate the queue consumer, or cut over from the tray.
`EPOCH2_QUEUE_CONSUMER_READY` remains `False`.

## Verification

- RED: the focused module initially failed collection because the new
  compositor contract did not exist.
- `py -m pytest -q tests/test_cloud_automation_continuation.py`
  - 41 passed, including eight concurrent activators, crash-after-activation,
    crash-after-admission, exact replay, competing lease, revoked provider,
    revoked destination, and missing-daemon cases.
- `py -m pytest -q tests/test_branch_tasks_v2.py tests/test_background_branch_authority.py tests/test_background_branch_authority_service.py tests/test_provider_work_authority.py tests/test_cloud_automation_continuation.py tests/test_request_admission_store.py tests/test_automation_activations.py`
  - 366 passed in 21.11 seconds.
- `py -m ruff check tinyassets/cloud_automation_continuation.py tests/test_cloud_automation_continuation.py`
  - passed.
- `py -m ruff format --check tinyassets/cloud_automation_continuation.py tests/test_cloud_automation_continuation.py`
  - passed.
- `py scripts/invariants_run.py --check mirror-parity`
  - all 300 canonical files matched.
- `git diff --check`
  - passed.

## Remaining critical path

Current main added `activate-custom-agent-runtime-core` after this slice began.
Its task 2.1 upgrades the shared activation/continuation/provider owners from a
bare Branch-version reference to one typed execution-subject
kind/reference/digest. PR #2082 therefore remains draft and MUST rebase/adapt
after that owner lands; merging it against the old activation shape would
violate the newer canonical delta.

The epoch-2 consumer is still dark. The next runtime slice must claim the
admitted task, launch through the bounded provider receipt/reservation owner,
and reconcile the exact outbound PR effect. Task 4.1 must then fence epoch 1
before enabling epoch 2; phone control and the 24-hour PC-off proof remain
release gates.
