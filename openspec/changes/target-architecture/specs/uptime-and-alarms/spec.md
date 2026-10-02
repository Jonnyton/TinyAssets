## ADDED Requirements

### Requirement: Deploys cause no origin downtime

A production deploy SHALL start the idle colour and wait for its health check
before moving new requests to it. It SHALL then drain the old colour: no new
admissions, singleton duties released, in-flight turns and streams finished up
to the drain bound. A turn still running at the bound SHALL be journaled and
reconciled on the new colour. Scheduling, triggers, the outbox pump and
metering SHALL run only under a leadership lease fenced by generation, so two
colours never both run them. A restart-gap probe at 5-second resolution SHALL
record origin downtime per deploy.

#### Scenario: A deploy during a chat turn
- **WHEN** a deploy starts while a user's turn is streaming
- **THEN** the turn finishes on the old colour, new requests go to the new colour, and the probe records zero seconds of origin downtime

#### Scenario: Two colours never both schedule
- **WHEN** the old colour has not yet released the lease and the new colour starts
- **THEN** only the lease holder runs triggers, and no trigger fires twice

### Requirement: A fenced warm standby in a second region

A standby cell and box host SHALL run in a second region or provider. They
SHALL restore platform state continuously, keep their tunnel connector stopped,
and restore box disks from off-region backups on first wake. Promotion SHALL
first fence the primary, by powering it off and blocking its auto-restart
through a credential held only by CI, and only then start the standby. If
fencing cannot be confirmed, promotion SHALL stop and page a human. Failback
SHALL be manual. The stated recovery points SHALL be about one second for
platform state, and the backup interval for box files, at most one hour plus
at suspend when dirty.

#### Scenario: Fencing fails
- **WHEN** promotion cannot confirm the primary is powered off
- **THEN** the standby is not started, and a page is sent

### Requirement: The restore drill runs on a schedule from off-region copies, including boxes

The DR drill SHALL run weekly on a schedule. It SHALL restore into a fresh host
from the off-region copies only, never from the primary. It SHALL assert that
the public canary goes green, and that a sample of boxes restores with matching
content checksums. A failed drill SHALL page. This requirement supersedes the
manual-drill clause of "Nightly Two-Tier Backup And Manual Fresh-Host
Data-Restore Drill" when S1 syncs.

#### Scenario: The drill restores from off-region
- **WHEN** the weekly drill runs
- **THEN** it restores platform state and sampled boxes from off-region storage into a fresh host, and the canary goes green
