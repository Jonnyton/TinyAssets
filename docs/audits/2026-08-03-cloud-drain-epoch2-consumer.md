# Cloud drain epoch-2 consumer evidence

Date: 2026-08-03 UTC / 2026-08-02 PDT

## Scope

This record covers the queue-consumer bridge between the deployed cloud worker
fleet and ordinary epoch-2 Branch tasks. It does not claim chatbot activation,
useful repository delivery, tray cutover, or the required 24-hour PC-off
acceptance.

Implementation commit after the final current-main rebase: `bcc9dbbf`. The
immutable PR comment records the final exact PR head, including this evidence
document.

Owning change: `activate-main-universe-spec-drain`.

## Why this is platform work

The implementation adds no drain-specific scheduler or selection policy. The
daemon consumes the same versioned BranchTask read model used by ordinary
user-authored workflows. Task selection, prioritization, evaluation, retry,
and loop strategy remain user-buildable Branch data. The platform code added
here owns only the hard runtime boundary: trusted capacity, transactional
claiming, restart recovery, lifecycle transitions, and activation
single-flight.

## Runtime boundary

- A cloud worker registration records the server-owned executor class
  `cloud`; user-authored task inputs cannot supply it.
- The supervisor persists a short-lived release-derived worker descriptor on
  the exact provisioned runtime instance.
- `read_worker_claim_context` resolves exactly one provisioned runtime for the
  worker from canonical SQLite state. Duplicate descriptors, malformed state,
  runtime/universe mismatch, missing executor class, and expired descriptors
  fail closed.
- The epoch-2 claim transaction rereads the descriptor through the same SQLite
  connection and requires exact equality with the caller's descriptor before
  queue mutation.
- Activation-bound tasks additionally reject a second running or
  cancel-requested task for the same `(universe_id, automation_id)` while the
  transaction holds `BEGIN IMMEDIATE`.

## Restart and lifecycle behavior

Before selecting new work, the daemon:

1. resumes its one live epoch-2 claim;
2. reconciles a live cancellation without running material work;
3. recovers expired canonical leases and attempts those recovered tasks before
   ordinary selection; and
4. only then performs merged v1/v2 selection.

Recovered tasks still pass the complete current worker descriptor and
activation transaction. Recovery itself grants no provider, execution, or
effect authority. Heartbeat, cancellation, success, and failure transitions
route through `Epoch2BranchTaskAdapter`; v1 JSON-queue behavior remains on its
existing owner.

A restart does not trust the fact that a task is already `running`.
`read_live_v2_task_for_resume` rereads the linked admission, current worker
descriptor, lease, and activation tuple under `BEGIN IMMEDIATE`. A stopped,
rebound, stale, mismatched, expired, malformed, or ambiguous authority tuple is
terminalized as `resume_authority_invalid` without material Branch execution.
The trusted worker/runtime identity is attached to the in-memory execution
model only after this revalidation.

## Local evidence

Environment: Windows PowerShell, Python 3.14.3, repository worktree based on
`origin/main` at `d8dea1a9`.

Commands run at implementation head:

```text
py -m pytest -q tests/test_fantasy_daemon_epoch2_dispatch.py \
  tests/test_branch_tasks_v2.py tests/test_cloud_worker.py \
  tests/test_goal_pool.py tests/test_fantasy_daemon_branch_task_lease.py \
  tests/test_soul_loop_dispatch.py
```

Result after the final current-main rebase: `255 passed in 40.70s`. This
includes eight
fresh-database, two-worker races; each race produced exactly one
activation-bound claim winner.

```text
py -m ruff check tinyassets/branch_tasks_v2.py tinyassets/cloud_worker.py \
  fantasy_daemon/__main__.py tests/test_fantasy_daemon_epoch2_dispatch.py \
  tests/test_cloud_worker.py
openspec validate activate-main-universe-spec-drain --strict
py -m scripts.invariants.mirror_parity
git diff --check
```

Results: Ruff clean; OpenSpec strict validation passed; canonical/plugin mirror
parity passed; diff check clean.

## Independent review

Fresh-context same-provider review is permitted by the host after the opposite
provider reported its hard subscription limit. An initial review of
`5dca7056` was started before the proactive restart-authority amendments and
is therefore advisory only. A second fresh-context review of the final exact
head is required. The verdict and immutable PR comment must be added here
before merge.

## Deployment and acceptance state

- Production dark deployment of this consumer: not yet run.
- Production public canary after this consumer: not yet run.
- Ordinary repo + spec Branch activation: not yet run.
- Rendered phone-chatbot inspect/control/evolve/rollback proof: not yet run.
- Single-active tray-to-cloud cutover: not yet run; the local drain remains
  active.
- Continuous PC-off proof: 0 of required 24 hours.

The consumer flag being code-owned `True` means capable workers may advertise
epoch-2 support. Useful cloud-drain activation remains fail-closed without a
project-loop daemon runtime, an exact live worker descriptor, and a current
cloud automation activation tuple.

## Temporary drain continuity

At 2026-08-02 19:11 PDT, the local watchdog reported the controller alive and
attempt 16 running. One attempt-15 admission collision was recorded, then the
supervisor admitted attempt 16 automatically. The local bridge remains active
until cloud acceptance is proven.
