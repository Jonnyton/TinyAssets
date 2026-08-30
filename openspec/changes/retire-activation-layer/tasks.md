## 1. Cut the legacy pump from the consumer (PR 1)

- [ ] 1.1 Remove `_serving_runtime`, the runtime-descriptor half of `_publish_heartbeat`, `_pump_automation`, `_record_pump_preconditions`, `_worker_model_for_provider`, `supervisor_heartbeat_filename`, `_safe_worker_id`, `_runtime_provider_name` and their `_run` call sites from `tinyassets/runtime/assigned_queue_consumer.py` (design §4 slice 1). Keep the unconditional liveness beat. Update `scripts/check_background_authority_inventory.py` and the two tests that import `supervisor_heartbeat_filename` in the same commit. Verify: `no_serving_runtime` stops appearing in `assigned_queue_refusals` on the droplet after deploy; the daemon watchdog still sees a fresh beat.

## 2. Delete the activation layer (PR 2)

- [ ] 2.1 One-shot migration marks every remaining `background_branch_bindings` and `cloud_automation_controls` row `retired` with reason `fleet_era_activation_layer_retired_2026-08-29` and logs the count; `write_graph target=automation operation=list` shows them as retired. Verify: droplet count logged on the first boot after deploy (expect 16 + 9).
- [ ] 2.2 Delete the 12 modules of design §1a and the 7 test files of §4 slice 2; the surgical edits in survivors (`storage/provider_work_authority.py` `validate_worker_runtime_in_transaction` only; `storage/automation_activations.py` `cloud_automation_controls` lookup only; import drops in `universe_server.py`, `runs.py`, `agent_runtime_provider_execution.py`, `storage/agent_runtime_provider_outcome.py`, `fantasy_daemon/__main__.py`). Verify: `tests/test_foreground_run_provider.py`, `tests/test_universe_intelligence.py`, `tests/test_api_status.py`, `tests/test_automations*.py`, `tests/test_scheduler*.py` green; set-compare against origin/main on the same tree.
- [ ] 2.3 Drop the eight tables (design §2) in a later commit of the same PR once `git grep` proves no daemon reader; remove `TINYASSETS_REQUESTER_PROVIDER_ENROLLMENTS_JSON` from `docs/reference/environment-variables.md`; sync the REMOVED fleet-era requirements out of `openspec/specs/background-branch-execution-authority/spec.md`.

## 3. Retire the queue-claim carrier (PR 3)

- [ ] 3.1 Delete `background_served_provider.py`, `runtime/claimed_branch_execution.py`, `branch_tasks_v2.py`; remove the consumer's `_try_claim` / `_execute`; re-point the nine survivors that import `branch_tasks_v2` (design §4 slice 3). Verify: the consumer still runs due automations live on the founder's universe after deploy (`ok:ran:<run_id>` in the ledger).
- [ ] 3.2 Collapse `get_status.epoch2_operational` to its `available: false` form (`_unavailable_epoch2_summary`) instead of zero worker counts; remove `TINYASSETS_WORKER_MODEL` from the catalog; edit the listed tests. Verify: `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp` green after deploy.

## 4. Runtime-instance half of the registry (PR 4)

- [ ] 4.1 Re-point the seven callers listed in design §4 slice 4, then delete `runtime_reconcile.py` and the eleven measured spans of `daemon_registry.py`; drop the `author_runtime_instances` DDL and its readers in `scoped_reset.py`, `reset.py`, `daemon_brain.py`. Verify: tray, brain and wiki paths green (`tests/test_daemon_registry.py`, `tests/test_daemon_dashboard.py`, `tests/test_supervisor_liveness.py`).
- [ ] 4.2 Sync the four fleet-reconciliation REMOVED requirements out of `openspec/specs/daemon-runtime-and-dispatch/spec.md`; the boot log no longer flags legacy schedule rows once the founder's `1508d5dc…` row is retired with the same reason. Archive this change.
