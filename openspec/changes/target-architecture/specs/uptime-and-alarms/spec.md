## ADDED Requirements

### Requirement: One execution owner behind replaceable frontends; deploys fail no requests

The control plane SHALL run exactly one execution owner at a time, under a
lease fenced by generation. The execution owner covers the agent loop, the turn
journal writer and its reconciliation, the scheduler, triggers, the outbox
pump, metering and the storage allocator. Every owner-side mutation SHALL check
the lease generation. Reconciliation SHALL run only after the lease is
acquired. Frontends SHALL hold no turn ownership, and SHALL be replaced
blue-green. While the owner hands over, frontends SHALL queue requests rather
than fail them. A handover SHALL drain the old owner first: it stops admitting,
finishes in-flight turns up to the drain bound, journals the rest, cancels
outstanding box executions and releases the lease. Schema-changing cutovers
SHALL be declared maintenance windows under the cutover exclusion protocol.

#### Scenario: A deploy during a chat turn
- **WHEN** a deploy runs while a user's turn is streaming
- **THEN** the turn either finishes on the old owner or is journaled and reconciled after the handover, no live turn is settled as interrupted, and no request fails

#### Scenario: A stalled old owner cannot write
- **WHEN** an old owner resumes after the new owner acquired the lease at a higher generation
- **THEN** its next mutation is refused

### Requirement: A fenced warm standby in a second region

A standby cell and box host SHALL run in a second region or provider. They
SHALL restore platform state continuously, keep their tunnel connectors
stopped, and restore box disks from off-region backups on first wake.
Promotion SHALL first fence every primary execution host, meaning the cell host
and any separate box host, by powering them off and blocking auto-restart
through a credential held only by CI. Only then SHALL it start the standby. If
fencing cannot be confirmed, promotion SHALL stop and page a human. Failback
SHALL be manual. The stated recovery point SHALL be about one second for
platform state, and the last box backup for box files.

#### Scenario: Fencing fails
- **WHEN** promotion cannot confirm that a primary host is powered off
- **THEN** the standby is not started, and a page is sent

### Requirement: The restore drill runs weekly from off-region copies, including boxes

The DR drill SHALL run weekly on a schedule. It SHALL restore into a fresh host
from off-region copies only, using a fresh template environment with the pinned
image, and SHALL NOT copy the primary host's environment or secrets. It SHALL
assert that the public canary goes green, and that a sample of boxes restores
with matching content checksums. A failed drill SHALL page.

#### Scenario: The drill restores from off-region
- **WHEN** the weekly drill runs
- **THEN** it restores platform state and sampled boxes from off-region storage into a fresh host without the primary's secrets, and the canary goes green
