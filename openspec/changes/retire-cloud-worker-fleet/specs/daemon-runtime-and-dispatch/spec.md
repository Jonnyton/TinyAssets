## ADDED Requirements

### Requirement: Daemon queue execution is credential-driven and fail-closed
Before claiming a pending BranchTask, the daemon SHALL resolve the physical queue universe's current provider assignment and sole serving agent binding, verify the assigned credential is available, and bind an immutable credential snapshot to all LLM calls in that branch run. It SHALL never use a platform, host, market, or alternate-provider credential for the task.

#### Scenario: Runnable task uses its universe assignment
- **WHEN** a pending task belongs to a universe with one current serving binding and usable assigned credential
- **THEN** the daemon claims the task and every LLM node uses only that credential

#### Scenario: Missing assignment holds pending work
- **WHEN** a pending task's universe has no current usable assigned serving credential
- **THEN** the daemon leaves the task pending with `hold_reason` equal to `no_requester_owned_executor`
- **AND** it does not invoke a provider or claim the task

#### Scenario: Later assignment releases the hold
- **WHEN** a previously held task's universe gains a current usable serving credential
- **THEN** the daemon clears the hold marker and the task becomes eligible for ordinary deterministic dispatch

#### Scenario: One held task does not block runnable work
- **WHEN** the highest-scored task is held and another pending task has an available assigned credential
- **THEN** the dispatcher selects the highest-scored runnable task

### Requirement: Production container ownership is worker-free
The canonical production compose and deploy fence SHALL recognize only the default `daemon`, `tunnel`, and `logs` services plus the profile-gated `slack-agent`; it SHALL define no cloud-worker service, worker provider pin, worker healthcheck, worker route input, or worker auth-home materialization.

#### Scenario: Canonical compose has no fixed workers
- **WHEN** the production compose file is inspected or rendered without optional profiles
- **THEN** no `worker`, `worker-codex-2`, `worker-claude-1`, or `worker-claude-2` service exists
- **AND** the daemon remains the queue-capable runtime

#### Scenario: Deploy fence rejects a stray worker
- **WHEN** deployment ownership discovery finds a container executing the retired cloud-worker module
- **THEN** the fence refuses deployment as a stray writer instead of accepting it as canonical

## MODIFIED Requirements

### Requirement: Host-singleton and idle-cycle coordination fail safe
Two file-lock coordination primitives SHALL keep the daemon runtime safe. `tinyassets.singleton_lock` SHALL enforce a single host daemon instance via an OS-exclusive file lock that is the ground truth, with a PID sidecar as a human-readable breadcrumb; a PID sidecar without a held OS lock SHALL be treated as stale and overwritten on acquisition. `tinyassets.idle_cycle` SHALL dedupe the no-work heartbeat cycle for the daemon with a run lock plus a freshness stamp and SHALL fail OPEN—degrading to a possibly-duplicate cycle, never a stalled heartbeat—when lock or stamp I/O fails. Neither primitive SHALL imply or enumerate a provider-shaped worker fleet.

#### Scenario: A second host instance cannot acquire the lock
- **WHEN** a second process attempts to acquire the singleton lock while another live process holds it
- **THEN** acquisition fails and reports the holding PID from the sidecar

#### Scenario: A stale PID sidecar is overwritten
- **WHEN** a PID sidecar exists but no process holds the paired OS lock
- **THEN** acquisition succeeds and the sidecar is overwritten with the new PID

#### Scenario: Idle-cycle coordination I/O failure fails open
- **WHEN** the idle-cycle run lock or stamp I/O errors
- **THEN** the slot is granted so the heartbeat cannot stall

## REMOVED Requirements

### Requirement: The supervisor keeps one daemon subprocess alive with backoff, producer restart, auth quarantine, and graceful drain
**Reason**: The cloud-worker supervisor and fixed worker processes are retired.
**Migration**: The canonical daemon owns queue cycles and resolves task credentials directly.

### Requirement: The container healthcheck asserts liveness, not mere process existence
**Reason**: The worker container and its dedicated heartbeat healthcheck no longer exist.
**Migration**: Keep daemon/tunnel/log health checks and queue/status canaries.
