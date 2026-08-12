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

Deploy quiescence SHALL preserve every queued row byte-for-byte and treat queued work as valid daemon-owned state, not as a fleet risk to cancel. The preservation baseline SHALL be sampled only after controlled writers are quiesced. The deploy observer SHALL publish its exact expected container contract; cleanup verification SHALL compare against that contract rather than a hardcoded fleet count and SHALL validate the active immutable image. Docker Compose schema rendering SHALL be a tested acceptance gate. Fluent log forwarding SHALL keep an explicit readable local cache large enough for the hourly offsite collector's default window, and cleanup/pruning SHALL target only script-owned scratch space and canonical TinyAssets archive names.

#### Scenario: Canonical compose has no fixed workers
- **WHEN** the production compose file is inspected or rendered without optional profiles
- **THEN** no `worker`, `worker-codex-2`, `worker-claude-1`, or `worker-claude-2` service exists
- **AND** the daemon remains the queue-capable runtime

#### Scenario: Deploy fence rejects a stray worker
- **WHEN** deployment ownership discovery finds a container executing the retired cloud-worker module
- **THEN** the fence refuses deployment as a stray writer instead of accepting it as canonical

#### Scenario: Deploy preserves pending and running queue state
- **WHEN** the writer-free deploy fence quiesces the prior daemon while queue rows exist
- **THEN** the before and after queue inventories are identical
- **AND** no row is cancelled, terminalized, or assigned a false executor hold by deployment machinery

### Requirement: Host daemon singleton fails safe
`tinyassets.singleton_lock` SHALL enforce one host daemon instance via an OS-exclusive file lock as ground truth, with a PID sidecar as a human-readable breadcrumb. A PID sidecar without a held OS lock SHALL be treated as stale and overwritten on acquisition. The singleton SHALL NOT imply provider-shaped daemon capacity.

#### Scenario: A second host instance cannot acquire the lock
- **WHEN** a second process attempts to acquire the singleton lock while another live process holds it
- **THEN** acquisition fails and reports the holding PID from the sidecar

#### Scenario: A stale PID sidecar is overwritten
- **WHEN** a PID sidecar exists but no process holds the paired OS lock
- **THEN** acquisition succeeds and the sidecar is overwritten with the new PID

## REMOVED Requirements

### Requirement: Host-singleton and fleet idle-cycle coordination fail safe
**Reason**: The fleet-wide idle-cycle lock/stamp is retired with the fixed fleet; the daemon singleton remains specified separately.
**Migration**: Run queue cycles in the one canonical daemon and rely on its host singleton.

### Requirement: The supervisor keeps one daemon subprocess alive with backoff, producer restart, auth quarantine, and graceful drain
**Reason**: The cloud-worker supervisor and fixed worker processes are retired.
**Migration**: The canonical daemon owns queue cycles and resolves task credentials directly.

### Requirement: The container healthcheck asserts liveness, not mere process existence
**Reason**: The worker container and its dedicated heartbeat healthcheck no longer exist.
**Migration**: Keep daemon/tunnel/log health checks and queue/status canaries.
