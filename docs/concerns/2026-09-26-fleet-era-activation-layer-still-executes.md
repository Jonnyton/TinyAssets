---
severity: P2
title: The fleet-era activation layer is dead, still runs, and still shapes `get_status`
filed: '2026-09-26'
summary: 'the layer that used to decide WHETHER background work may run was replaced live on 2026-08-30 but is still wired in: every consumer tick evaluates a retired concept and records `no_serving_runtime`, `get_status` still publishes `epoch2_operational` worker counts for a fleet that does not exist, and the measured subtraction is −18,361 production / −12,863 test lines. Re-verified 2026-09-26 on `31a1776c`'
---

# The fleet-era activation layer is dead, still runs, and still shapes `get_status`

**Filed:** 2026-09-26, on archiving `openspec/changes/retire-activation-layer/` unstarted
(0 of 8 tasks, last touched 2026-08-29, 28 days idle). The change is a plan; this is the
finding it was written to act on, kept where an unresolved finding belongs so it does not
depend on anybody reopening that plan.
**Verified:** 2026-09-26 against `origin/main` `31a1776c`.
**Severity:** P2 — no cross-user effect, but it burns work on every consumer tick and it
makes `get_status` report a fleet that does not exist.

## The finding

`user-owned-automations` proved the replacement live on 2026-08-30: the daemon's own
consumer ran the founder's heartbeat automation and its re-registered schedule on the
founder's own subscription, deriving authority at run time. The layer that used to decide
**whether** background work may run became dead weight — but it is still wired in and
still executes.

## Re-verified today, not carried forward on trust

Every symbol the archived change named is still present in
`tinyassets/runtime/assigned_queue_consumer.py` (1,393 lines): `_serving_runtime` (10
occurrences), `_pump_automation`, `_record_pump_preconditions`,
`_worker_model_for_provider`, `supervisor_heartbeat_filename`, `_safe_worker_id`,
`_runtime_provider_name` (2 each). `tinyassets/branch_tasks_v2.py` (1,863 lines) is alive
with 13 modules reading it. The retired vocabulary is still emitted:
`api/automations.py:287` writes `"status": "retired_fleet_era"`, `api/status.py:628`
still publishes an `epoch2_operational` key, and `api/cloud_automations.py:315-317`
still calls `_epoch2_operational_snapshot`.

## Why it is worth a file rather than a checkbox

Three costs, none of which a reader would guess from the code:

1. **Every consumer tick evaluates a retired concept** and records `no_serving_runtime`
   per serving universe plus `consumer_not_applicable:assigned_cloud_automation` for the
   surviving `bt2_…` rows (`assigned_queue_refusals` on the droplet, 2026-08-30T02:29Z).
   A refusal that is structural reads like a fault.
2. **`get_status` describes a fleet that does not exist** — `epoch2_operational` worker
   counts. A status surface that reports dead infrastructure is worse than silent.
3. **It is the largest single subtraction available.** The archived change measured
   **−18,361 production lines and −12,863 test lines** across four slices
   (`archive/2026-09-26-retire-activation-layer/design.md:382`, taken against the tree on
   2026-08-29), with the foreground served path verified untouched: `runs.py` has zero
   references to `branch_tasks_v2`/Epoch2, `run_graph` goes through
   `foreground_run_provider`, `converse` through `providers.call` +
   `provider_serving_binding`, and `automations.py` imports
   `new_foreground_run_provider_session` directly — it never needed the queue-claim
   carrier.

## What the next session needs

The deletion map, symbol sweep, table inventory, `get_status` shape changes and the
four-slice order are all in
`openspec/changes/archive/2026-09-26-retire-activation-layer/design.md` — read it before
re-proposing, because the value is in §1c ("MUST NOT be deleted — foreground-load-bearing")
and §3 (references outside the candidate set), not in the line count. Re-propose it as a
change when somebody will actually run it; archiving was the right call for an unstarted
plan, not a judgement on the work.

Delete this file when the layer is gone: `no_serving_runtime` stops appearing in
`assigned_queue_refusals` after deploy, and `epoch2_operational` leaves `get_status`.
