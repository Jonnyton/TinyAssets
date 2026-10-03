# Design: the activation-layer map

Measured against origin/main on 2026-08-29 by the Explore lane that scoped task 3.3 of
`user-owned-automations`; every span below is a line range on THAT tree. Line numbers rot —
re-verify each span on the tree you cut, and correct it here in place.

# Fleet-era activation layer — dependency map

Read-only analysis. Worktree `C:\Users\Jonathan\Projects\wf-automations`, branch
`claude/automations`, HEAD `b6b6f8b7`, 2026-08-29. Nothing was modified.

Scope: `openspec/changes/user-owned-automations/` D1, D6 step 4, task 3.3 —
"The fleet-era activation layer retires after the new path is proven live:
continuations, executor audiences, runtime pinning, enrollment manifest."

Working tree carries uncommitted work: `tinyassets/automations.py` (934 lines, new,
untracked) and `tinyassets/runtime/assigned_queue_consumer.py` (+108/-12). Line
numbers below are the WORKING TREE unless marked HEAD.

---

## 0. Bottom line

**The foreground served path is safe from the entire deletion set — verified, not
assumed.** `tinyassets/runs.py` contains ZERO references to `branch_tasks_v2` or
Epoch2; `execute_branch_async` (`tinyassets/runs.py:3301`) is an in-process thread
runner. `run_graph` goes `tinyassets/api/runs.py:73` -> `foreground_run_provider`.
`converse` goes `tinyassets/universe_intelligence.py:26` -> `providers.call` +
`provider_serving_binding`. Neither touches the activation layer, the epoch2
queue, or `background_served_provider`.

**The new `automations.py` path also bypasses the carrier entirely** —
`tinyassets/automations.py:704` imports `new_foreground_run_provider_session`
directly. This is the single most important structural fact for slicing:
`background_served_provider.py` is NOT needed by the new path, despite the
proposal listing it as "kept, re-pointed."

---

## 1. Module inventory

### 1a. Deletable in full (the activation layer proper) — 13,679 lines

| Module | Lines | Production importers | Test importers |
|---|---|---|---|
| `tinyassets/cloud_automation_continuation.py` | 3015 | `agent_runtime_provider_execution.py`, `api/cloud_automations.py`, `background_served_provider.py`, `cloud_automation_runtime.py`, `cloud_automation_setup.py`, `runs.py`, `runtime/assigned_queue_consumer.py`, `storage/agent_runtime_provider_outcome.py`, `storage/provider_work_authority.py`, `fantasy_daemon/__main__.py` | 9 files |
| `tinyassets/background_branch_authority_service.py` | 2102 | `background_served_provider.py`, `cloud_automation_continuation.py`, `cloud_automation_runtime.py`, `cloud_automation_setup.py`, `storage/background_branch_authority.py`, `storage/provider_work_authority.py` | 5 files |
| `tinyassets/background_branch_authority.py` | 1477 | + `runtime/assigned_queue_consumer.py`, `user_owned_cloud_automation.py`, `storage/cloud_automation_continuation.py` | 8 files |
| `tinyassets/storage/background_branch_authority.py` | 1393 | same cluster | 8 files |
| `tinyassets/storage/cloud_automation_control.py` | 1199 | `api/cloud_automations.py`, `cloud_automation_*`, `runtime/assigned_queue_consumer.py`, `storage/cloud_automation_continuation.py` | 4 files |
| `tinyassets/cloud_automation_control.py` | 1103 | same | 4 files |
| `tinyassets/storage/cloud_automation_continuation.py` | 1003 | same cluster + `runs.py` | 9 files |
| `tinyassets/api/cloud_automations.py` | 742 | `universe_server.py` (route registration) | 3 files |
| `tinyassets/cloud_automation_runtime.py` | 626 | `runtime/assigned_queue_consumer.py:660`, `fantasy_daemon/__main__.py` | 4 files |
| `tinyassets/user_owned_cloud_automation.py` | 591 | `api/cloud_automations.py`, `cloud_automation_continuation.py`, `cloud_automation_control.py`, `cloud_automation_setup.py`, `storage/cloud_automation_control.py` | 3 files |
| `tinyassets/cloud_automation_setup.py` | 337 | `api/cloud_automations.py` | 2 files |
| `tinyassets/storage/cloud_automation_inputs.py` | 91 | `api/cloud_automations.py`, `cloud_automation_setup.py` | 1 file |

Every production importer of every row above is INSIDE this set, except
`runs.py`, `agent_runtime_provider_execution.py`,
`storage/agent_runtime_provider_outcome.py`, `storage/provider_work_authority.py`,
`fantasy_daemon/__main__.py`, and `universe_server.py` — each a single import
site, listed as a surgical edit in slice 2.

### 1b. Deletable with the carrier (slice 3) — 3,345 lines

| Module | Lines | Production importers |
|---|---|---|
| `tinyassets/branch_tasks_v2.py` | 1802 | `api/universe.py`, `background_served_provider.py`, `cloud_automation_continuation.py`, `daemon_registry.py`, `daemon_server.py`, `runtime/assigned_queue_consumer.py:18`, `runtime_reconcile.py`, `scoped_reset.py`, `storage/provider_work_authority.py`, `storage/request_admissions.py`, `work_targets.py`, `fantasy_daemon/__main__.py`, `fantasy_daemon/branch_registrations.py` |
| `tinyassets/background_served_provider.py` | 1206 | `branch_tasks_v2.py`, `provider_assignment.py`, `providers/router.py`, `runtime/assigned_queue_consumer.py:460,896,983` |
| `tinyassets/runtime/claimed_branch_execution.py` | 337 | `background_served_provider.py`, `runtime/assigned_queue_consumer.py:25`, `fantasy_daemon/__main__.py` |

`background_served_provider.py` is threaded through the audience layer at ~20
call sites (`:17,66,67,144,145,152,240,244,249,250,325,328,329,443,444,449,521,
522,527,833,841`). It is NOT separable from `background_branch_authority*` as
written — which is fine, because nothing on the new path needs it.

### 1c. MUST NOT be deleted — foreground-load-bearing

- **`tinyassets/provider_work_authority.py` (1962)** — `foreground_run_provider.py:15`
  imports 9 symbols: `ProviderInvocationCarrier`, `ProviderUniverseWorkAuthority`,
  `ProviderUniverseWorkReceipt`, `ProviderUniverseWorkRoot`,
  `ProviderWorkAuthorityWriteOutcome`, `ProviderWorkBindingRoot`,
  `ProviderWorkBindingSeed`, `ProviderWorkBindingService`,
  `ProviderWorkExecutionClaim`. Also `providers/router.py:33`,
  `provider_serving_binding.py:33`, `provider_assignment.py`.
- **`tinyassets/storage/provider_work_authority.py` (2737)** —
  `provider_serving_binding.py:41` imports `SQLiteProviderWorkAuthorityStore`.
  Also `foreground_run_provider.py`, `provider_assignment.py`, `providers/base.py`,
  `providers/router.py`, `agent_runtime_invocation.py`.
  Fleet-era surface is EXACTLY ONE METHOD: `validate_worker_runtime_in_transaction`
  (`:2666-2714`, 49 lines), the only reader of `author_runtime_instances`
  (`:2686`). Exactly two callers, both inside the deletion set:
  `cloud_automation_continuation.py:1707`, `storage/cloud_automation_control.py:916`.
  Clean cut — it dies with them.
- **`tinyassets/daemon_registry.py` (987)** — MIXED. 454 of 987 lines are the
  runtime-instance half (slice 4); the other 533 (`create_daemon:269`,
  `list_daemons:368`, `get_daemon:430`, `summon_daemon:442`,
  `update_daemon_behavior:801`, `daemon_control_status:857`, `banish_daemon:906`)
  serve `daemon_brain.py`, `daemon_wiki.py`, `api/universe.py`, `tinyassets_tray.py`.
- **`tinyassets/storage/automation_activations.py` (783)** — NOT in the candidate
  set and MUST SURVIVE. Shared with the whole `agent_runtime_*` family
  (`agent_invocation_authority.py`, `agent_runtime_activation.py`,
  `agent_runtime_command.py`, `agent_runtime_invocation.py`,
  `agent_runtime_principal.py`, `agent_runtime_provider_execution.py`,
  `storage/agent_runtime_invocation.py`, `storage/request_admissions.py`).
  Owns `automation_activations` (`:130`). Carries a legacy read of
  `cloud_automation_controls` at **`:661-668`** inside the transition helper: if
  the table exists and `desired_state != "active"`, it returns `None`. Excise
  when the table goes, or every activation silently returns `None`.

### 1d. Dead already

- **`tinyassets/runtime_reconcile.py` (323)** — ZERO production importers. Only
  `tests/test_runtime_reconcile.py` and a CLI entry at `:260`. The
  `_runtime_reconcile_digest` hits in `daemon_server.py:1375,1423` and
  `daemon_registry.py:153` are a same-named local helper, not this module.

### 1e. New path (keep, this is the replacement)

`tinyassets/automations.py` (934). Owns `automations` (`:78`) and
`automation_attempts` (`:103`) — D2's `(automation_id, due_at)` fence.
Depends on: `scheduler` (`:517,639`), `api/branches` (`:559,818`), `daemon_server`
(`:560,679,729`), `provider_assignment` (`:561,680`),
`runtime/assigned_queue_consumer` (`:562` `assigned_queue_consumer_enabled`,
`:851` `_error_reason`), `config` (`:703`), **`foreground_run_provider` (`:704`)**,
`providers.base` (`:705`), `providers.call` (`:706`), `branches` (`:728`),
`runs` (`:767,884`), `storage/assigned_queue_refusals` (`:800`).
Consumes NOTHING from the activation layer.

Consumer wiring: `_submit_due_automations:368`, `_run_automations:427`,
`_reap_finished:356`. Uses only `_reap_finished`, `_paused:450`, `_record_reason:499`,
`_error_reason:119`.

---

## 2. Storage tables and get_status

### Tables owned by the deletion set

| Table | Defined at |
|---|---|
| `cloud_automation_slice_triggers` | `storage/cloud_automation_control.py:38` |
| `cloud_automation_terminal_receipts` | `storage/cloud_automation_control.py:61` |
| `cloud_automation_controls` | `storage/cloud_automation_control.py:75` |
| `cloud_automation_continuations` | `storage/cloud_automation_continuation.py:40` |
| `cloud_execution_continuations` | `storage/cloud_automation_continuation.py:51` |
| `background_branch_bindings` | `storage/background_branch_authority.py:45` |
| `background_branch_attempts` | `storage/background_branch_authority.py:59` |
| `background_branch_authority_owners` | `storage/background_branch_authority.py:74` |
| `author_runtime_instances` | **`daemon_server.py:182`** (NOT `daemon_registry.py`) |

Kept: `provider_work_bindings/receipts/execution_claims`,
`provider_invocation_reservations` (`storage/provider_work_authority.py:139,152,169,180`)
— foreground. `automation_activations` (`storage/automation_activations.py:130`)
— agent-runtime family. `assigned_queue_refusals`
(`storage/assigned_queue_refusals.py:12`) — D5's single refusal home, already
written by the new path.

### get_status fields that change shape

`get_status` = `tinyassets/api/status.py:1012` (also `universe_server.py:2807`,
`fantasy_daemon/api.py:993`).

**`supervisor_liveness` SURVIVES** — computed from BranchTask lease fields
(`api/status.py:509 _compute_supervisor_liveness_uncached`; emitted `:1506`), not
from the activation layer. Two members go permanently empty:
- `running_tasks_lease[].executor_worker_id` — `api/status.py:667,703`
- `running_tasks_lease[].executor_runtime_id` — `api/status.py:668,704`

**`epoch2_operational`** (`api/status.py:557` init, `:777-780` fill, built in
`api/universe.py:1587 _epoch2_operational_snapshot`) — four keys lose meaning:

1. **`compatible_worker_count`** -> always `0`. `_classify_epoch2_workers`
   (`api/universe.py:1238`) is built entirely on `list_runtime_instances` reading
   `author_runtime_instances` (`api/universe.py:1272-1274`), filtered to
   `status == "provisioned"` (`:1281`). Set at `api/universe.py:1562`; null-form
   `api/universe.py:1451`.
2. **`capacity_rejections`** (`api/universe.py:1580`) -> the gate-attribution
   histogram loses its input. Only emitted `if capacity_evidence and not workers`,
   so it silently stops appearing rather than going empty.
3. **`capacity_evidence_available`** (`:1578`) / **`operational_counts_authoritative`**
   (`:1582`) -> vacuous.
4. **`consumer_pump`** (`api/universe.py:1572-1576`) -> SURVIVES and is the correct
   home for the new refusals, but keys change from `universe:<id>:<principal_id>`
   to the automation form the new consumer writes
   (`universe:<id>:automations`, `assigned_queue_consumer.py:412`).

Warnings that lose their trigger: `api/status.py:792,847,899`.

---

## 3. Symbol sweep — references OUTSIDE the candidate set

**`runtime_instance_id`** — `api/universe.py` (28, incl. `:1279`), `runs.py` (22),
`fantasy_daemon/__main__.py` (10), `contribution_events.py` (5),
`bid/settlements.py` (5), `attribution/schema.py` (4), `bid/node_bid.py` (3),
`api/market.py` (3). Tests: `test_daemon_registry.py` (38),
`test_fantasy_daemon_epoch2_dispatch.py` (20), `test_runtime_reconcile.py` (19),
`test_dispatcher_queue.py` (6), `test_contribution_events_emit.py` (6),
`test_node_bid.py` (5), `test_api_universe.py` (5), `test_supervisor_liveness.py` (4),
`test_attribution_schema.py` (4). Docs:
`docs/design-notes/2026-05-02-daemon-registry-substrate.md`.

**`executor_worker_id`** — `fantasy_daemon/__main__.py` (8), `branch_tasks.py` (7),
`api/status.py:667,703`. Tests: `test_fantasy_daemon_epoch2_dispatch.py` (7),
`test_supervisor_liveness.py` (3), `test_branch_tasks.py` (1). Spec:
`openspec/specs/daemon-runtime-and-dispatch/spec.md` (1) — normative, must be
REMOVED in the delta.

**`author_runtime_instances`** — `daemon_server.py` (16, DDL at `:182`),
`scoped_reset.py` (2), `reset.py` (1), `daemon_brain.py` (1),
`storage/provider_work_authority.py:2686`. Tests: `test_runtime_reconcile.py` (7),
`test_fantasy_daemon_epoch2_dispatch.py` (2), `test_scoped_identity_reset.py` (1),
`test_reset_universes.py` (1).

**`BackgroundBranchExecutorAudience`** — NO production references outside the
candidate set. Tests only: `test_cloud_automation_continuation.py` (11),
`test_cloud_automation_api.py` (9), `test_background_branch_authority_service.py` (8),
`test_user_owned_cloud_automation.py` (2),
`test_background_budget_finalization_e2e.py` (2). Archived change docs (2).

**`cloud_automation_controls`** — **`storage/automation_activations.py:661-668`**
ONLY. Everything else is docs/specs.

**Enforcement gates that pin the above:**
- `scripts/check_background_authority_inventory.py` pins exact call sites:
  `:117,123` and `:394` (`tinyassets/runtime/assigned_queue_consumer.py`),
  `:441-442` (`daemon_registry.py` `def get_daemon(` / `def list_runtime_instances(`).
  Goes red the moment those functions move. Test: `test_background_authority_inventory.py`.
- `tests/test_execution_authority_import_boundary.py:80-84` importlib-imports
  `tinyassets.runtime.assigned_queue_consumer` and `tinyassets.branch_tasks_v2`
  by name. Red at slice 3.

---

## 4. Deletion order — 4 slices

Each slice keeps the foreground path and the new daemon consumer working.

### Slice 1 — cut the legacy pump from the consumer
**No file deletions. Production −560 lines available** (of `assigned_queue_consumer.py`'s 1015).

Remove, measured spans:
- `_serving_runtime:542-584` (43)
- `_publish_heartbeat:585-654` (70)
- `_pump_automation:655-783` (129)
- `_record_pump_preconditions:784-874` (91)
- `_worker_model_for_provider:60-82` (23)
- `supervisor_heartbeat_filename:48-59` (12)
- `_safe_worker_id:43-47` (5)
- `_runtime_provider_name:136-143` (8)
- `_run` call sites `:273-299`
- (`_try_claim:453-490` (38) and `_execute:875-1015` (141) defer to slice 3)

Slice-1 subtotal: **381 lines**.

Surgical edits in survivors: none outside the consumer.
Gate to fix SAME COMMIT: `scripts/check_background_authority_inventory.py:117,123,394`.
Tests edited not deleted: `test_loop_telemetry.py:33,170`,
`test_assigned_queue_consumer_live_worker.py:25,123` (both use
`supervisor_heartbeat_filename`).
Env leaving: none.

### Slice 2 — delete the activation layer
**Production −13,679 (12 files). Tests −10,671 (7 files).**

Files deleted: the 12 rows of section 1a.

Surgical edits in surviving files:
- `storage/provider_work_authority.py` — delete
  `validate_worker_runtime_in_transaction:2666-2714` (49 lines). Both callers die
  in this slice.
- `storage/automation_activations.py:661-668` — excise the `cloud_automation_controls`
  lookup, ELSE every activation silently returns `None`.
- `universe_server.py` — drop the `api.cloud_automations` route registration.
- `runs.py` — drop its `storage/cloud_automation_continuation` import.
- `agent_runtime_provider_execution.py`, `storage/agent_runtime_provider_outcome.py`,
  `storage/provider_work_authority.py` — drop `cloud_automation_continuation` imports.
- `fantasy_daemon/__main__.py` — drop `cloud_automation_runtime` +
  `cloud_automation_continuation` imports.
- `background_served_provider.py` — drop `background_branch_authority*` and
  `build_request_task_attempt_key` imports (or fold slices 2 and 3 together if the
  claim loop is going anyway — cleaner).

Tables dropped: `cloud_automation_controls`, `cloud_automation_slice_triggers`,
`cloud_automation_terminal_receipts`, `cloud_automation_continuations`,
`cloud_execution_continuations`, `background_branch_bindings`,
`background_branch_attempts`, `background_branch_authority_owners`.
Per task 3.3, retire the 16 `background_branch_bindings` + 9
`cloud_automation_controls` rows as explicit retired rows with reason BEFORE
dropping.

Tests deleted (10,671 lines): `test_cloud_automation_api.py` 1790,
`test_cloud_automation_continuation.py` 2738, `test_cloud_automation_control.py` 704,
`test_background_branch_authority.py` 1297,
`test_background_branch_authority_service.py` 1950,
`test_background_branch_authority_store.py` 1372,
`test_user_owned_cloud_automation.py` 820.

Env leaving the catalog: `TINYASSETS_REQUESTER_PROVIDER_ENROLLMENTS_JSON`
(sole production site `provider_work_enrollment.py`; 8 refs in
`test_provider_work_enrollment.py`).

### Slice 3 — retire the queue-claim carrier
**Production −3,345 (3 files) + −179 consumer. Tests −1,349 (3 files).**

Files deleted: `background_served_provider.py` 1206,
`runtime/claimed_branch_execution.py` 337, `branch_tasks_v2.py` 1802.
Consumer: `_try_claim:453-490` (38) + `_execute:875-1015` (141).

Surgical edits in survivors: `work_targets.py`, `scoped_reset.py`,
`runtime_reconcile.py`, `storage/request_admissions.py`, `daemon_registry.py`,
`daemon_server.py`, `api/universe.py`, `fantasy_daemon/__main__.py`,
`fantasy_daemon/branch_registrations.py` all import `branch_tasks_v2`.
`api/universe.py:1255-1258` (`WorkerClaimDescriptor`, `_descriptor_is_live`) goes
with `_classify_epoch2_workers:1238`.
**THIS IS WHERE get_status SHAPE CHANGES** — collapse `epoch2_operational` to the
`available: false` form (`api/universe.py:1431 _unavailable_epoch2_summary`)
rather than report misleading zeros for `compatible_worker_count`.

Tests deleted (1,349): `test_background_served_provider.py` 804,
`test_background_budget_finalization_e2e.py` 369,
`test_claimed_branch_execution.py` 176.
Tests edited: `test_execution_authority_import_boundary.py:80-84` (importlib by
name — red here), `test_branch_tasks_v2.py` 3054, `test_assigned_queue_consumer.py` 481,
`test_assigned_queue_consumer_live_worker.py` 590 (`consumer_pump` shape
`:500,530,571`), `test_unified_execution.py`,
`test_distributed_execution_authority.py`, `test_request_admission_store.py`,
`test_request_admission_surface.py`, `test_scoped_identity_reset.py`,
`test_submit_request_wiring.py`, `tests/load/operator_admission_v2_fixture.py`.

Env leaving: `TINYASSETS_WORKER_MODEL` (sole site was
`assigned_queue_consumer.py:68`, removed in slice 1).

### Slice 4 — runtime-instance half of the registry
**Production −777 (323 file + 454 pruned). Tests −843.**

Files deleted: `runtime_reconcile.py` 323 (no production importer at all).

Prune `daemon_registry.py`, 454 of 987 lines, measured spans:
`StaleCloudWorkerRuntimeRetirementPlan:40-49` (10),
`_runtime_heartbeat_is_stale:50-88` (39),
`plan_stale_cloud_worker_runtime_retirement:89-157` (69),
`_runtime_from_author_runtime:236-268` (33),
`ensure_daemon_runtime:489-537` (49),
`set_worker_queue_descriptor:538-628` (91),
`_control_result:707-731` (25),
`control_runtime_instance:732-800` (69),
`list_runtime_instances:919-932` (14),
`runtime_matches_worker_provider:933-962` (30),
`provider_capacity_warning:963-987` (25).

Callers to re-point FIRST (all outside the candidate set):
- `api/universe.py:2594` `_action_daemon_list`
- `api/universe.py:2628` `_latest_runtime_id_for_daemon`
- `api/universe.py:2761` `_action_daemon_banish`
- `api/universe.py:2792` `_action_daemon_runtime_control`
- `fantasy_daemon/api.py:2504`
- `daemon_server.py:1525` (its own `list_runtime_instances`)
- `tinyassets_tray.py` (`provider_capacity_warning`, 2 sites)

Also drop the `author_runtime_instances` DDL (`daemon_server.py:182`) and its
readers in `scoped_reset.py` (2), `reset.py` (1), `daemon_brain.py` (1).

Tests deleted: `test_runtime_reconcile.py` 843.
Tests edited: `test_daemon_registry.py` 802, `test_dispatcher_queue.py`,
`test_api_status.py`, `test_supervisor_liveness.py:926` (`capacity_rejections`),
`test_daemon_dashboard.py`, `test_fantasy_daemon_epoch2_dispatch.py` 1499,
`test_background_authority_inventory.py`.

Env leaving: none (see 5.2/5.3).

### Totals

| Slice | Production | Tests |
|---|---|---|
| 1 — consumer pump | −381 | 0 (2 edited) |
| 2 — activation layer | −13,679 | −10,671 |
| 3 — queue-claim carrier | −3,524 (3,345 + 179) | −1,349 |
| 4 — registry runtime half | −777 | −843 |
| **Total** | **−18,361** | **−12,863** |

Slices 2+3 alone = 17,024 production lines, matching the design doc's "~15k lines"
risk estimate.

---

## 5. Corrections to the change documents

**5.1 `design.md` mis-cites the boot-unique consumer id.** It says
`assigned_queue_consumer.py:129`. That line is inside `_error_reason`'s body in
BOTH HEAD and the working tree. The real assignment is
**`assigned_queue_consumer.py:179-181`**:
`boot = uuid.uuid4().hex` / `self.boot_id = boot` /
`self.consumer_id = f"worker_assigned_{boot}"`. Same line numbers in HEAD.

The other four design citations verified CORRECT:
- `cloud_automation_runtime.py:233` — the `runtime_matches_worker_provider` call. OK.
- `storage/provider_work_authority.py:2709` — `runtime_row["provider_name"] ==
  binding.provider`, inside `validate_worker_runtime_in_transaction:2666`. OK.
- `daemon_registry.py:933-960` — `runtime_matches_worker_provider`. OK (ends 962).
- `storage/cloud_automation_continuation.py:352` — the `provider_binding_id`
  equality is actually at `:356`; the enclosing tuple starts at `:351`. Close.

**5.2 `proposal.md` says `UNIVERSE_SERVER_HOST_USER` "leaves the catalog." It
cannot.** Three live non-fleet consumers:
- `api/market.py:413` — host identity for the paid market
  (`(os.environ.get("UNIVERSE_SERVER_HOST_USER") or "host").strip()`), documented
  `:426,3742`
- `api/status.py:1082`
- `idle_cycle.py:125`

It is also normative in `openspec/specs/paid-market-economy/spec.md` (2 refs).
Removing it breaks the paid-market surface. Catalog entry:
`docs/reference/environment-variables.md:28`. Tests depending on it:
`test_dispatcher_queue.py` (10), `test_payments_escrow_mcp.py` (2),
`test_idle_cycle_single_flight.py` (2), `test_api_status.py`,
`test_gate_bonuses_mcp.py`, `test_operator_priority_authority.py`,
`test_patch_request_incentives.py`.

**5.3 Same issue, smaller: `TINYASSETS_WORKER_*` is not uniformly fleet-only.**
`TINYASSETS_WORKER_ID` is read by `idle_cycle.py:125`, `work_targets.py:425`,
`fantasy_daemon/__main__.py:223,456,1089`,
`fantasy_daemon/branch_registrations.py:229`, and documented in
`branch_tasks.py:606`. Only **`TINYASSETS_WORKER_MODEL`**
(`assigned_queue_consumer.py:68`) is genuinely fleet-only.

Net: of the three env groups the proposal retires, only
`TINYASSETS_REQUESTER_PROVIDER_ENROLLMENTS_JSON` and `TINYASSETS_WORKER_MODEL`
can actually leave.

**5.4 Three modules missing from the candidate set:**
- `tinyassets/user_owned_cloud_automation.py` (591) — despite the name it is
  fleet-era (imports `BackgroundBranchExecutorClass`, `ProviderWorkBindingState`).
  Deletes in slice 2.
- `tinyassets/storage/cloud_automation_inputs.py` (91) — deletes in slice 2.
- `tinyassets/storage/automation_activations.py` (783) — must SURVIVE, needs the
  `:661-668` excision.

**5.5 The candidate set named `storage/provider_work_authority.py` as a deletion
candidate. It is foreground-load-bearing** and must be pruned, not deleted (see
1c). Same for `daemon_registry.py`.
