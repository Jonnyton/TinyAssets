## MODIFIED Requirements

### Requirement: Workspace jobs are admitted and settled through their own ledger kind with the maximum charge reserved before the wire

The engine SHALL reserve the runtime-controlled maximum transport byte charge
before workspace network activity, keeping existing per-universe rolling-byte,
lease, pool, retained-storage and lock checks. It SHALL reconcile downward only
from trustworthy measurement, retaining the maximum for an unknown or interrupted
transfer. Workspace job-count rows SHALL remain observations and SHALL NOT
independently refuse work based on jobs per hour. No caller-supplied packet
ceiling SHALL decide quota consumption.

Push and discard SHALL preserve their deterministic operation identity and
idempotent reservations. A zero-byte discard SHALL NOT be refused merely because
earlier workspace starts exhausted the retired jobs count. Generic execution and
effect admission remain separate existing controls. Workspace transfer bytes
SHALL remain separate from generic delivered-result byte accounting; workspace
effect nodes still consume the generic effect-node dispatch count.

#### Scenario: More than ten light operations
- **WHEN** eleven authorized workspace operations have sufficient actual resource capacity
- **THEN** the eleventh is admitted without an independent jobs-per-hour refusal and the observational count records eleven

#### Scenario: A retried push does not duplicate its reservation
- **WHEN** the same identified push reservation is requested again
- **THEN** its existing reservation is returned without adding another workspace job/byte record

#### Scenario: The hourly workspace bytes are exhausted
- **WHEN** a new checkout's runtime-controlled reservation would exceed the existing transfer window
- **THEN** it is refused before transport with workspace_quota_exceeded and the actual byte constraint

#### Scenario: Two checkouts compete for remaining bytes
- **WHEN** two checkouts concurrently request more combined bytes than remain
- **THEN** only a fitting reservation commits and the other is refused atomically

#### Scenario: Cleanup after ten starts
- **WHEN** more than ten jobs are recorded and an authorized zero-byte discard is requested
- **THEN** the observational jobs total does not block cleanup

#### Scenario: Unknown transfer remains conservative
- **WHEN** checkout fails and no trustworthy transfer measurement exists
- **THEN** its existing maximum byte reservation remains; a deleted or small local tree is not proof of zero transferred bytes
