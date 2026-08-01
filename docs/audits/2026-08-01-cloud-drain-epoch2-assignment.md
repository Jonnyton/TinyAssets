# Cloud drain epoch-2 assignment audit

Date: 2026-08-01
Environment: Windows 11, Python 3.14, branch `codex/cloud-drain-activation-composition-20260801`

## Outcome

The dark cloud-drain path can now narrow one persisted, activation-bound
epoch-2 request task into one background-attempt reservation. The resolver
rereads the exact prepared continuation, active cloud epoch, immutable Branch
version, request/admission/task aggregate, background binding generation and
digest, source generation, remaining envelope, expiry, and a server-selected
cloud worker. Any mismatch returns no authority.

The slice also repairs an interface incompatibility discovered by the RED
test: canonical epoch-2 IDs use `req_`, `adm_`, and `bt2_`, but the background
authority's request-task key rejected those non-bearer forms. They are now
admitted as nominal references, and the real epoch-2 IDs produce the stable
logical attempt key used for restart replay.

## Safety boundary

- The resolver grants no bearer capability and performs no provider or GitHub
  effect.
- Background-attempt insertion remains owned by
  `BackgroundBranchAttemptIssuanceService` and unique by logical attempt key.
- The task must still be pending and carry the exact current cloud activation
  epoch, lease, executor class, and immutable Branch version.
- The background binding must be rooted in the same persisted request and
  admission generation.
- The server-selected daemon/runtime/worker audience must exactly match the
  reservation request and the task's directed daemon.
- The epoch-2 consumer remains dark. The local drain remains the only live
  bridge until server-authoritative cutover is implemented and proven.

## Verification

- `py -m pytest -q tests/test_cloud_automation_continuation.py tests/test_background_branch_authority.py tests/test_background_branch_authority_service.py tests/test_request_admission_store.py tests/test_automation_activations.py`
  - 260 passed after current-main reconciliation, including an eight-way
    single-winner/replay concurrency check for the composed assignment.
- `py -m ruff check tinyassets/cloud_automation_continuation.py tinyassets/background_branch_authority.py tests/test_cloud_automation_continuation.py tests/test_background_branch_authority.py`
  - passed before documentation foldback.
- `git diff --check`
  - passed before documentation foldback.

## Remaining critical path

This is not live cloud execution. The next slice must compose restart-safe
activation plus admission, claim the reserved attempt under current worker
custody, then connect the bounded provider receipt to reconciled outbound
effects. Actual cutover still requires the local claimant to observe the same
server fence before epoch-2 consumption can be enabled.
