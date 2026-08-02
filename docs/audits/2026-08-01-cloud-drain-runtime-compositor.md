# Cloud drain runtime compositor evidence

Date: 2026-08-01
Environment: Windows 11, Python 3.14
Branch: `codex/cloud-drain-runtime-compositor-20260801`
Initial implementation commit: `af9da3a17709b3242d43ea046993871b55555cba`
Current integration head: PR #2082 (see exact head in GitHub)

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
authority, missing daemons, a binding that expired or exhausted its live
attempt/cost budget after preparation, a mismatched canonical admission-body
digest, or changed snapshots fail closed before activation. IDs after the
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
  - 44 passed, including eight concurrent activators, crash-after-activation,
    crash-after-admission, exact replay, competing lease, revoked provider,
    revoked destination, expired/exhausted binding, and missing-daemon cases.
- `py -m pytest -q tests/test_branch_tasks_v2.py tests/test_background_branch_authority.py tests/test_background_branch_authority_service.py tests/test_provider_work_authority.py tests/test_cloud_automation_continuation.py tests/test_request_admission_store.py tests/test_automation_activations.py`
  - 369 passed in 23.92 seconds.
- `py -m ruff check tinyassets/cloud_automation_continuation.py tests/test_cloud_automation_continuation.py`
  - passed.
- `py -m ruff format --check tinyassets/cloud_automation_continuation.py tests/test_cloud_automation_continuation.py`
  - passed.
- `py scripts/invariants_run.py --check mirror-parity`
  - all 300 canonical files matched.
- `git diff --check`
  - passed.
- Exact integrated head `9c33a053` (2026-08-01, Windows local): 685 focused
  authority/runtime/controller tests passed; Ruff, both strict OpenSpec
  changes, 306-file mirror parity, cross-provider drift, and diff check passed.
- Opposite-provider Claude Fable 5 reviewed exact `9c33a053` read-only and
  returned `VERDICT: APPROVE`; receipt is recorded on PR #2082.

## Remaining critical path

The typed execution-subject, immutable manifest, component compiler, plan
compiler, and live grant-resolver prerequisites have landed and PR #2082 has
integrated them. The PR is ready and auto-merge enrolled.

The exact-head desktop-release run exposed a separate CI blocker. Job
`91434467418` entered the unsigned Windows lifecycle step at 00:14:12Z and was
still reported in progress more than 18 minutes later despite a job-level
`timeout-minutes: 15`. The lifecycle helper allowed four sequential 180-second
phases and, on timeout, called process-tree `Kill($true)` plus another blocking
wait. The corrected exact-head gate passes 90 seconds explicitly per phase,
logs phase start/completion, and uses non-blocking forced root termination
before throwing; the ephemeral runner owns descendant cleanup. The structural
test failed RED before this correction and now passes with the PowerShell AST
parse clean. Refreshed CI remains the acceptance evidence.

The epoch-2 consumer is still dark. The next runtime slice must claim the
admitted task, launch through the bounded provider receipt/reservation owner,
and reconcile the exact outbound PR effect. Task 4.1 must then fence epoch 1
before enabling epoch 2; phone control and the 24-hour PC-off proof remain
release gates.
