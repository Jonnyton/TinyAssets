## REMOVED Requirements

### Requirement: The supervisor keeps one daemon subprocess alive with backoff, producer restart, auth quarantine, and graceful drain
**Reason**: The cloud-worker supervisor (`tinyassets.cloud_worker`) is the host-run fleet. The
founder principle of 2026-08-29 (PLAN.md, Cross-Cutting Principles) forbids any execution outside
a user's universe under that user's control; production has run no worker since the fleet was
switched off, and the daemon's own consumer executes due work on each universe's current serving
assignment instead.
**Migration**: Delete `tinyassets/cloud_worker.py` and the four `worker*` services in
`deploy/compose.yml`; relocate `_worker_model_for_provider` and `supervisor_heartbeat_filename`
into the consumer module. No data migration -- there are no worker rows to preserve.

### Requirement: The container healthcheck asserts liveness, not mere process existence
**Reason**: The healthcheck (`tinyassets.cloud_worker_healthcheck`) exists only for the retired
worker containers. The daemon container keeps its own healthcheck.
**Migration**: Delete `tinyassets/cloud_worker_healthcheck.py` with the compose services.

### Requirement: Host-singleton and fleet idle-cycle coordination fail safe
**Reason**: Fleet idle-cycle coordination has no fleet to coordinate.
**Migration**: None; the daemon is the only executor.

### Requirement: Stale retired-fleet reconciliation is dry-run first
**Reason**: `reconcile-stale-fleet.yml` reconciled rows written by the fleet; with the fleet
deleted nothing writes them.
**Migration**: Delete the workflow; the retired rows it targeted are retired explicitly by
`user-owned-automations` task 3.3.

### Requirement: Apply is bound to the reviewed plan
**Reason**: Part of the retired-fleet reconciliation workflow above.
**Migration**: Deleted with it.

### Requirement: Only stale retired-cloud-capacity tasks are cancelled
**Reason**: Part of the retired-fleet reconciliation workflow above.
**Migration**: Deleted with it.

### Requirement: Only stale unowned cloud-worker runtimes are retired
**Reason**: Part of the retired-fleet reconciliation workflow above.
**Migration**: Deleted with it.

## ADDED Requirements

### Requirement: The daemon's own consumer executes due automations on the current serving assignment
The daemon SHALL execute due user-owned automations itself, resolving each universe's current
provider assignment and credential custody at run time; it SHALL NOT require a registered
executor runtime identity, a fleet heartbeat, or a worker container to do so.

#### Scenario: Due automation after a daemon restart
- **WHEN** the daemon restarts with a new process identity and an automation comes due
- **THEN** the run launches on the universe's current assignment without any runtime re-registration
