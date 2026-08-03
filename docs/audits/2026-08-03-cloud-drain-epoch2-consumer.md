# Cloud drain epoch-2 consumer evidence

Date: 2026-08-03 UTC / 2026-08-02 PDT

## Scope

This record covers the queue-consumer bridge between the deployed cloud worker
fleet and ordinary epoch-2 Branch tasks. It does not claim chatbot activation,
useful repository delivery, tray cutover, or the required 24-hour PC-off
acceptance.

Latest implementation commit after reconciliation onto `origin/main`
`773315ff`: `0397774f`. The
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

The execution boundary also preserves the activation's immutable published
Branch version. A canonical `run_branch` continuation goes through direct
Branch execution, the epoch-2 read model retains the complete activation
tuple and immutable admission actor, and `execute_branch_version` persists the
trusted daemon/runtime/worker identity plus queue lineage. Each queue task
atomically reserves exactly one run through a private `branch_task_id` unique
key. Restart and reservation-race reconciliation require an exact match across
task, run name, Branch definition/version, universe, actor, daemon, runtime,
and worker. A public caller-created run with the same display name cannot be
reused, and a durable nonterminal reservation never starts a second
provider/effect execution.

Epoch-2 task leases use the existing 30-minute safety envelope while a
dedicated 30-second heartbeat thread renews the lease during blocking provider
nodes. Missing ownership, renewal exceptions, or a heartbeat thread that
cannot stop propagate as execution-authority loss; they cannot be logged and
then reported as successful work. The independently refreshed worker
descriptor remains limited to 90 seconds for new claim authority.
Pending tasks for an activation that already has a running or
cancel-requested task are excluded in the transactional candidate query, so
they cannot head-of-line block unrelated automations.

## Local evidence

Environment: Windows PowerShell, Python 3.14.3, repository worktree based on
`origin/main` at `773315ff`.

Commands run at implementation head:

```text
py -m pytest -q tests/test_fantasy_daemon_epoch2_dispatch.py \
  tests/test_branch_tasks_v2.py tests/test_cloud_worker.py \
  tests/test_goal_pool.py tests/test_fantasy_daemon_branch_task_lease.py \
  tests/test_soul_loop_dispatch.py tests/test_request_admission_store.py \
  tests/test_run_branch_version.py tests/test_bug_investigation_dispatcher.py
```

Result after the fourth review-finding repair:
`359 passed in 24.79s` across
the epoch-2 consumer, cloud worker, transactional adapter/store, immutable
Branch version, v1 lease/dispatcher compatibility, and bug-investigation
integration suites. This includes queue-run reservation races with exactly one
winner, forged display-name rejection, full recovery-identity mismatch
rejection, reservation-loser reconciliation, continuous heartbeats beyond an
hour, and fail-closed lease-loss proof. The earlier activation-claim race and
head-of-line-starvation proofs remain covered.

```text
py -m ruff check tinyassets/branch_tasks_v2.py tinyassets/cloud_worker.py \
  fantasy_daemon/__main__.py tests/test_fantasy_daemon_epoch2_dispatch.py \
  tests/test_cloud_worker.py
openspec validate activate-main-universe-spec-drain --strict
py scripts/invariants_run.py --check mirror-parity
git diff --check
```

Results: Ruff clean; OpenSpec strict validation passed; canonical/plugin mirror
parity passed; diff check clean.

## Independent review

Fresh-context same-provider review is permitted by the host after the opposite
provider reported its hard subscription limit. An initial review of
`5dca7056` was started before the proactive restart-authority amendments and
is therefore advisory only. It returned `ADAPT` with six findings: canonical
`run_branch` routing, restart activation revalidation, the 90-second task
lease, mutable Branch-head execution and dropped runtime identity, duplicate
execution after an incomplete run, and activation head-of-line starvation.
The restart activation and trusted runtime fields were already repaired; the
remaining four are covered by the implementation and focused tests above.

The required second fresh-context review then inspected exact head `ff47949c`
and returned `ADAPT` on two additional concurrency faults: recovery trusted a
caller-spoofable, non-unique display name without validating the execution
identity; and node-boundary-only heartbeats allowed a valid long provider node
to outlive a fixed lease while renewal loss was logged and ignored. Both are
now repaired by the atomic private task/run reservation, exact identity gate,
continuous heartbeat guard, and fail-closed authority-loss propagation above.
A third fresh-context review of exact head `bc58e72c` independently validated
the two race repairs and the six earlier advisories, then returned `ADAPT`
because cancellation requested during a blocking node could be renewed and
the completed provider result could still finalize the task as succeeded. The
repair now treats observed cancellation as a typed execution stop and
propagates it through node-status callbacks and the continuous heartbeat
guard. A fourth review validated that path but returned `ADAPT` on the smaller
read-then-write window between the final cancellation check and success
transition, and on swallowed terminalization errors. Settlement now resolves
both states in the task-store transaction: `running` may become `succeeded`,
while `cancel_requested` can only become `cancelled`; store failures propagate.
Deterministic last-moment cancellation injection and terminal-store failure
tests cover both findings. A fifth fresh-context review of the new exact head
is required before merge.
Its immutable PR comment is the post-commit authority for the exact head and
verdict, avoiding a documentation-only commit that would invalidate the head
it reviewed.

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

At 2026-08-02 20:25 PDT, the local watchdog reported health `running`, the
controller alive as PID 19300, attempt 20 running, five completed slices, and
one consecutive failed slice. The supervisor remained live and responsible
for automatic retry. The local bridge remains active until cloud acceptance is
proven.
