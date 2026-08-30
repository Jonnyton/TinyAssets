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

<!-- The four reconciliation requirements below sync with task 3.3, not 1.2: the
workflow that scheduled them is deleted, but `python -m tinyassets.runtime_reconcile
stale-fleet` still exists as the operator CLI that retires the old rows. Synced
2026-08-29 with 1.2: the two deletions above and the MODIFIED requirement below. -->
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

## MODIFIED Requirements

### Requirement: Host-singleton and same-data-dir idle-cycle coordination fail safe
Two file-lock coordination primitives SHALL keep the runtime safe under concurrency. `tinyassets.singleton_lock` SHALL enforce a single host daemon instance via an OS-exclusive file lock that is the ground truth, with a PID sidecar as a human-readable breadcrumb; a PID sidecar without a held OS lock SHALL be treated as stale and overwritten on acquisition. `tinyassets.idle_cycle` SHALL dedupe the no-work heartbeat cycle across any daemon processes sharing one data directory with a run lock plus a freshness stamp, skipping when another process is mid-cycle or has a fresh stamp, and SHALL fail OPEN — degrading to a possibly-duplicate cycle, never a stalled heartbeat — when its lock or stamp I/O fails. As-built note (2026-08-29): the host-run worker fleet this originally coordinated is deleted; the daemon is the only executor and the primitive stays in `fantasy_daemon` for whatever processes share the directory.

#### Scenario: a second host instance cannot acquire the lock
- **WHEN** a second process attempts to acquire the singleton lock while another live process holds it
- **THEN** acquisition fails and reports the holding PID from the sidecar

#### Scenario: a stale PID sidecar is overwritten
- **WHEN** a PID sidecar exists but no process holds the paired OS lock
- **THEN** acquisition succeeds and the sidecar is overwritten with the new PID

#### Scenario: a fresh foreign idle-cycle stamp is skipped
- **WHEN** a daemon process attempts the idle cycle while a different process's stamp is within the freshness window
- **THEN** it declines the slot and does not run a duplicate no-work cycle

#### Scenario: idle-cycle coordination I/O failure fails open
- **WHEN** the idle-cycle run lock or stamp I/O errors
- **THEN** the slot is granted (fail open) so the heartbeat cannot stall

## ADDED Requirements

### Requirement: The daemon's own consumer executes due automations on the current serving assignment
The daemon SHALL execute due user-owned automations itself, resolving each universe's current
provider assignment and credential custody at run time; it SHALL NOT require a registered
executor runtime identity, a fleet heartbeat, or a worker container to do so.

#### Scenario: Due automation after a daemon restart
- **WHEN** the daemon restarts with a new process identity and an automation comes due
- **THEN** the run launches on the universe's current assignment without any runtime re-registration
