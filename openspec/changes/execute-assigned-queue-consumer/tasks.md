## 1. Background provider authority

- [ ] 1.1 Add failing tests for the distinct `background_branch_run` binding, immutable branch roles, cross-universe/provider rejection, rotation-before-launch, snapshot cleanup, and no ambient fallback.
- [ ] 1.2 Implement the atomic assigned-provider/background-attempt/custody/budget fence and per-launch provider call until the authority tests pass.

## 2. Shared claimed-task executor

- [ ] 2.1 Add differential tests covering immutable version execution, run reservation/reuse, cancellation heartbeats, terminal metadata, and delegated-authz/confidentiality inputs.
- [ ] 2.2 Extract `execute_claimed_branch_task(base_path, claimed_task, executor_identity, provider_call)` and switch `fantasy_daemon` to the shared implementation.

## 3. Assigned queue consumer

- [ ] 3.1 Add failing claim/store tests for flag-off zero claims, epoch/version/lease CAS, two-consumer single winner, retryable authority release, and restart recovery.
- [ ] 3.2 Implement the bounded/stoppable consumer, per-universe/global caps, daemon startup integration, and exception containment behind the default-off flag.

## 4. Verification and mirror

- [ ] 4.1 Prove scheduled runs retain the assigned direct provider path and run all new plus touched-area test suites and Ruff.
- [ ] 4.2 Rebuild the Claude-plugin mirror, verify parity, review the full diff for shape/basic safety, and record residual risks without enabling or deploying.

## 5. Consumer is the live worker (live finding, flag on since 2026-08-25 19:14Z)

Context: with `TINYASSETS_ASSIGNED_QUEUE_CONSUMER=1` live on prod (`e17d8747`), the only pending task
stayed `pending / awaiting_compatible_capacity / no_live_compatible_worker` and nothing explained why:
`claim_assigned` refusals are a silent `continue`; `get_status` still derives liveness from cloud_worker
supervisor beats; `resume` cannot produce a task because `activate_one_requested_cloud_automation` /
`produce_one_due_cloud_automation_slice` are only called from the retired `tinyassets/cloud_worker.py`;
and `prepare_cloud_automation` mints bindings with `runtime_id=None`, so
`claim_background_queue_authority_in_transaction` can never pass `bool(binding.runtime_id)` until an
activation with a real executor audience rotates the binding.

- [x] 5.1 Failing tests first (real store, mirror `tests/test_background_budget_finalization_e2e.py`):
  (a) flag on: `poll_once()` writes one supervisor heartbeat per serving universe that
      `tinyassets/api/universe.py::_classify_epoch2_workers` accepts (alive, subprocess_alive,
      capabilities incl. OPERATOR_CAPABILITY, queue_protocol_version) so `compatible_worker_count >= 1`
      and the `no_live_compatible_worker` reason clears; flag off: no beat file, no side effect.
  (b) when `claim_assigned` returns None for a candidate, the consumer records a named refusal
      `(branch_task_id, reason, observed_at, consumer_id)` via a READ-ONLY explain path that returns the
      FIRST failing predicate name from `_transaction_allows_assigned_consumer` and
      `claim_background_queue_authority_in_transaction` (e.g. `no_admission_row`,
      `no_background_authority`, `binding_not_active`, `binding_expired`, `binding_runtime_missing`,
      `attempt_not_reserved`, `automation_already_active`, `activation_claim_invalid`, `queue_owner_exists`);
      `get_status` epoch-2 diagnostics then show `operational_state="awaiting_background_authority"`,
      `reason=<name>` while the refusal is fresh (< 5 x poll interval); stale -> existing semantics.
  (c) flag on, one serving universe with a prepared automation whose desired state is ACTIVE:
      `poll_once()` activates it via `activate_one_requested_cloud_automation` with a
      `BackgroundBranchExecutorAudience(CLOUD, daemon_id=<the binding's daemon>, runtime_id=<a runtime
      instance the consumer registered once per boot>, worker_id=consumer_id)`, produces the due trigger
      via `produce_one_due_cloud_automation_slice`, and a later `poll_once()` claims + executes the
      resulting task through the existing carrier path (owner PENDING->RUNNING->terminal). Flag off: nothing.
- [x] 5.2 Implement: beat writer (reuse `supervisor_heartbeat_filename` + the cloud_worker beat shape),
      refusal ledger + explain path, activation/production inside `poll_once` under the process lease
      (port the cloud_worker loop body ~L1080-1240 WITHOUT the `os.environ[...] =` identity mutation:
      identity flows only through the audience object; never `create_daemon(created_by=<owner>)` on a
      user's behalf - reuse the binding's daemon / `select_project_loop_daemon` as prepare did), and the
      status projection in `tinyassets/api/universe.py`.
- [x] 5.3 Legacy pending tasks with no claimable authority are NOT deleted or cancelled server-side;
      they are surfaced with their named reason (5.1b) so the owner decides via the user surface.
- [x] 5.4 Ruff + touched suites green (`tests/test_background_served_provider.py`,
      `tests/test_background_budget_finalization_e2e.py`, `tests/test_assigned_queue_consumer*.py`,
      status tests); plugin mirror parity; no deploy/enable changes (flag already live).
