## ADDED Requirements

### Requirement: The daemon carries no fleet-era activation layer
The daemon's consumer SHALL evaluate only user-owned automations and schedules when it ticks. It
MUST NOT consult a per-universe executor runtime, a cloud-automation control row, a background
branch binding, or a host enrollment manifest to decide whether work may run, and it MUST NOT
record a refusal for the absence of any of those. Legacy rows of the retired layer SHALL be
marked retired with an explicit reason before their tables are dropped, and the owner's list
surface SHALL show them as retired until then.

#### Scenario: A serving universe with no fleet-era runtime ticks clean
- **GIVEN** a universe with a current serving assignment and one active automation
- **AND** no fleet-era runtime descriptor or control row exists for it
- **WHEN** the consumer ticks
- **THEN** the automation runs when due and the refusal ledger holds no `no_serving_runtime`
  and no `consumer_not_applicable:assigned_cloud_automation` entry for that universe

#### Scenario: Legacy rows are retired explicitly, then dropped
- **GIVEN** `background_branch_bindings` and `cloud_automation_controls` rows that authorize a
  retired staging principal
- **WHEN** the retirement migration runs on boot
- **THEN** every row is marked `retired` with reason `fleet_era_activation_layer_retired_2026-08-29`
- **AND** the daemon log records the count
- **AND** `write_graph target=automation operation=list` shows each as `retired` until the tables
  are dropped in a later commit that grep proves has no daemon reader

#### Scenario: Status reports the carrier as unavailable rather than as an empty fleet
- **GIVEN** the queue-claim carrier has been deleted
- **WHEN** `get_status` is read for a universe
- **THEN** `epoch2_operational` is the `available: false` form
- **AND** no `compatible_worker_count` of zero is reported

## REMOVED Requirements

### Requirement: Claimed-task execution binds enqueue authority to the physical queue universe
**Reason**: Claimed-task execution is the fleet-era queue-claim carrier (`branch_tasks_v2`,
`background_served_provider`, `runtime/claimed_branch_execution`). The daemon's own consumer now
executes due automations through the foreground session directly
(`tinyassets/automations.py` → `new_foreground_run_provider_session`), deriving authority from the
universe's current serving assignment at run time; nothing enqueues claimed tasks any more.
**Migration**: Slice 3 of `design.md` deletes the three carrier modules and the consumer's
`_try_claim` / `_execute`; surviving importers are re-pointed. No data migration — remaining
`bt2_*` task rows are refused as `consumer_not_applicable` today and are dropped with the tables.
