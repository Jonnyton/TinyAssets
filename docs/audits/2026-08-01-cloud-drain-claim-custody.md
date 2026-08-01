# Cloud drain claim-custody audit

Date: 2026-08-01
Environment: Windows 11, Python 3.14, branch `codex/cloud-drain-claim-composition-20260801`

## Outcome

The dark cloud-drain path now composes a transactionally claimed epoch-2 task
with its reserved background attempt. `PreparedCloudContinuationClaimResolver`
rereads the exact prepared continuation, active cloud epoch, request/admission/
task aggregate, background binding, server-selected worker, stored task claim
instant, heartbeat, and lease. The background attempt advances from `reserved`
to `claimed` only for that same worker and lease.

`BackgroundBranchAttemptClaimService` now invokes every claim-lifecycle
resolver inside the background authority transaction. Because the control-plane
stores share one SQLite database, the write transaction prevents activation,
task, binding, or attempt mutation between resolution and compare-and-swap.
Claim/renew resolutions also receive the requested lease expiry, so a resolver
can reject caller-selected custody that differs from the owning task.

## Safety boundary

- The epoch-2 adapter still owns the first task claim and transactionally
  validates the current activation tuple plus trusted worker descriptor.
- The background resolver supports ordinary `CLAIM` only. Renew, release, and
  recovery remain fail-closed for this composition until later custody slices.
- Queue `+00:00` instants are normalized at the background boundary, while
  equality is checked as UTC instants; neither authority's timestamp contract
  is weakened.
- A stopped activation, alternate worker, different lease, or post-claim
  heartbeat causes resolution to return no authority.
- Eight identical concurrent claim issuers yield one `APPLIED` transition and
  seven restart-safe `REPLAYED` observations. No second attempt is created.
- The claimed attempt resolves through the existing bounded provider-work
  receipt owner, but no provider launch or external effect occurs in this slice.
- `EPOCH2_QUEUE_CONSUMER_READY` remains false. The local drain remains the live
  bridge.

## Verification

- `py -m pytest tests/test_branch_tasks_v2.py tests/test_background_branch_authority.py tests/test_background_branch_authority_service.py tests/test_provider_work_authority.py tests/test_cloud_automation_continuation.py -q`
  - 314 passed on 2026-08-01 in the worktree above.
- `py -m pytest tests/test_background_branch_authority_service.py tests/test_cloud_automation_continuation.py -q`
  - 68 passed, including transaction-bound resolution, fail-closed custody,
    provider handoff, and eight-way concurrency.
- `py -m ruff check tinyassets/background_branch_authority_service.py tinyassets/cloud_automation_continuation.py tests/test_background_branch_authority_service.py tests/test_cloud_automation_continuation.py`
  - passed on 2026-08-01.
- `py -m ruff format --check tinyassets/background_branch_authority_service.py tinyassets/cloud_automation_continuation.py tests/test_background_branch_authority_service.py tests/test_cloud_automation_continuation.py`
  - passed on 2026-08-01.
- `git diff --check`
  - passed before documentation foldback.

## Remaining critical path

This is not live cloud execution. Task 1.2 still needs the activation/admission
compositor and provider launch/effect reconciliation. Cutover still needs the
single-active epoch-1 fence, dark epoch-2 enablement, live deployment, phone
control, and the 24-hour PC-off proof before the local bridge can stop.
