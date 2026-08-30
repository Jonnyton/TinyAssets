# Retire the fleet-era activation layer

## Why

`user-owned-automations` proved its replacement live on 2026-08-30: the daemon's own consumer
ran the founder's heartbeat automation (`d25a356811d0405c8bc92ebc9601c68f` → runs
`c500e5d9f7e0451a`, `d0116b67415145a6`) and the re-registered schedule (`9a331b73…` → run
`ab48eff7bc2c4722`) on the founder's own subscription, deriving authority at run time. The
fleet-era layer that used to decide WHETHER background work may run is now dead weight that still
executes: every consumer tick evaluates the retired runtime concept and records
`no_serving_runtime` for each serving universe and `consumer_not_applicable:assigned_cloud_automation`
for the surviving `bt2_…` task rows (`assigned_queue_refusals` on the droplet, 2026-08-30T02:29Z);
`write_graph target=automation operation=list` still shows nine `retired_fleet_era` rows; the
boot log flags the founder's legacy schedule row every restart; `get_status` still reports
`epoch2_operational` worker counts for a fleet that no longer exists.

The measured inventory (`design.md`, taken against the tree on 2026-08-29) is −18,361 production
lines and −12,863 test lines across four slices, with the foreground served path verified
untouched: `tinyassets/runs.py` has zero references to `branch_tasks_v2`/Epoch2, `run_graph` goes
through `foreground_run_provider`, `converse` through `providers.call` + `provider_serving_binding`,
and `tinyassets/automations.py` imports `new_foreground_run_provider_session` directly — it never
needed the queue-claim carrier.

This was task 3.3 of `user-owned-automations`. It was split out so that change could archive on
its live proof instead of idling on a four-PR deletion (delivery flow: finish or archive; a change
idle 14 days is not in flight).

## What Changes

Four PRs, in the map's order, each keeping the foreground path and the new consumer green:

1. **Cut the legacy pump from the consumer** — `_serving_runtime`, `_publish_heartbeat`'s
   runtime descriptor half, `_pump_automation`, `_record_pump_preconditions`,
   `_worker_model_for_provider`, `supervisor_heartbeat_filename`. The unconditional liveness
   beat for every serving universe stays (the watchdog reads it). The `no_serving_runtime`
   refusal disappears from the ledger.
2. **Delete the activation layer** — the 12 modules of inventory §1a and their 7 test files;
   a one-shot migration first marks every remaining `background_branch_bindings` (16) and
   `cloud_automation_controls` (9) row `retired` with reason
   `fleet_era_activation_layer_retired_2026-08-29` and logs the count; the eight tables drop in
   a later commit of the same PR only once grep proves the daemon no longer reads them.
   `TINYASSETS_REQUESTER_PROVIDER_ENROLLMENTS_JSON` leaves the env catalog.
3. **Retire the queue-claim carrier** — `background_served_provider.py`,
   `runtime/claimed_branch_execution.py`, `branch_tasks_v2.py`, the consumer's `_try_claim` /
   `_execute`. `get_status.epoch2_operational` collapses to its `available: false` form rather
   than reporting zeros. `TINYASSETS_WORKER_MODEL` leaves the catalog.
4. **Runtime-instance half of the registry** — `runtime_reconcile.py` and the eleven measured
   spans of `daemon_registry.py`; `author_runtime_instances` DDL and readers. `create / list /
   get / summon / banish / update_daemon_behavior` stay (brain, wiki, tray).

Hard constraints (from the map, re-verify spans before cutting):

- `tinyassets/provider_work_authority.py` and `tinyassets/storage/provider_work_authority.py`
  are foreground-load-bearing — prune only `validate_worker_runtime_in_transaction`.
- `tinyassets/storage/automation_activations.py` survives; excise only its
  `cloud_automation_controls` lookup, else every agent-runtime activation returns `None`.
- `UNIVERSE_SERVER_HOST_USER` and `TINYASSETS_WORKER_ID` stay (paid market, idle cycle,
  fantasy_daemon). `assigned_queue_refusals` stays (D5). `supervisor_liveness` stays.
- `scripts/check_background_authority_inventory.py` is a CI gate: update it in the same commit
  as the code it inventories. Rebuild the plugin mirror in every PR.
- Each PR: ≤ 8 release-critical files; no AUTHORITY paths unless the map requires it (it does
  not); one Codex refute per PR asked to name any foreground-path breakage with file:line.

## Capabilities

### Modified Capabilities

- `daemon-runtime-and-dispatch` — the REMOVED requirements for the fleet reconciliation plan
  (`Stale retired-fleet reconciliation is dry-run first`, `Apply is bound to the reviewed plan`,
  `Only stale retired-cloud-capacity tasks are cancelled`, `Only stale unowned cloud-worker
  runtimes are retired`) leave the as-built spec with slice 4, which deletes the code they
  describe.
- `background-branch-execution-authority` — the fleet-era requirements (executor audience,
  runtime pin, enrollment manifest) leave with slice 2.
- `live-mcp-connector-surface` / status — `epoch2_operational` shape change with slice 3
  (documented, not a new handle).

## Non-goals

- No change to `tinyassets/automations.py`, the scheduler, or the served carrier's foreground
  session — the replacement is proven and stays as is.
- No migration of legacy rows into the new tables — they are retired explicitly, not
  re-authorized (Codex finding 5 on the parent change).
