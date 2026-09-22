## ADDED Requirements

### Requirement: Platform runtime provenance is resolved once and fails closed
The platform SHALL resolve the executing process's cloud provenance through one
resolver whose result is the only source of executor class and runtime
registration. Absent, unreadable or mismatched evidence SHALL resolve to
not-cloud and SHALL cause refusal; it SHALL NOT fall back to a host, tray,
local or degraded class. Hostname, machine alias, container name, compose
label, env-var naming and possession of a deployed checkout SHALL NOT be
evidence. Evidence SHALL be a cloud instance fact that a copied checkout does
not carry, matched against the instance recorded by the deployment.

#### Scenario: Unattested process resolves to refusal, never to a fallback class
- **WHEN** the cloud instance fact is unreachable, or is reachable but does not
  match the deployment-recorded instance
- **THEN** provenance resolves to not-cloud with a recorded refusal reason
- **AND** no host, tray, local or degraded executor class is produced.

#### Scenario: Local labels and aliases do not manufacture provenance
- **WHEN** a process sets every environment variable the deployed container
  sets, aliases its hostname to the public hostname, and matches container and
  compose labels
- **THEN** provenance still resolves to not-cloud.

### Requirement: Task claim admission enforces provenance inside the claim transaction
Assigned-task claim admission SHALL evaluate resolved provenance within the
same transaction that transfers ownership, so that a caller invoking the claim
directly cannot acquire a task. Pre-claim consumer checks MAY remain as
diagnostics but SHALL NOT be the only enforcement.

#### Scenario: Direct claim by an unattested process is refused
- **WHEN** an unattested process calls the assigned-task claim directly with a
  valid consumer lease and a ready, pending cloud task, bypassing the consumer
  loop's pre-check
- **THEN** no task is claimed and a refusal reason is recorded.

#### Scenario: Attested process claims and records the resolved class
- **WHEN** an attested cloud process claims a ready cloud task
- **THEN** the claim succeeds and the recorded executor class is the resolved
  value, not a literal stamped by the caller.

### Requirement: Runtime registration is attested, instance-bound and not replayable
Runtime registration SHALL write the resolved provenance rather than a constant,
SHALL bind the attested cloud instance identity and the process boot epoch, and
SHALL be re-validated when read. The existence of a registration row SHALL NOT
by itself confer execution or serving authority.

#### Scenario: Unattested registration is refused
- **WHEN** an unattested process requests a runtime slot
- **THEN** registration refuses and no cloud-worker registration row is written.

#### Scenario: A stale registration cannot be replayed
- **WHEN** a registration row attested for one cloud instance and boot epoch is
  later read by a process that is unattested, or attested to a different
  instance or boot epoch
- **THEN** authority is refused on read and the row grants nothing.

### Requirement: Serving startup, foreground and served execution refuse when unattested
Serving startup SHALL assert provenance before accepting any platform traffic
and SHALL exit rather than serve when unattested; there SHALL be no local or
degraded serving mode. Foreground conversation turns and served background
provider execution SHALL refuse before spawning any provider process.

#### Scenario: Unattested serving startup does not serve
- **WHEN** the serving process starts unattested
- **THEN** it exits non-zero without binding a platform listener or accepting a
  request.

#### Scenario: Unattested foreground or served turn spawns no provider
- **WHEN** a foreground conversation turn or a served background turn is
  requested on an unattested runtime
- **THEN** the turn refuses and no provider subprocess or model relay is started.

### Requirement: Public ingress is admitted at the origin, not by credential possession
The origin SHALL refuse tunnel-forwarded platform traffic when unattested,
independently of how the request was routed. Possession of a tunnel credential,
a public hostname or a proxied DNS record SHALL NOT admit platform work.

#### Scenario: Forwarded request to an unattested origin is refused
- **WHEN** a request arrives at an unattested origin through a valid public
  tunnel connector
- **THEN** the origin refuses before any universe work, model relay or storage
  write.

### Requirement: Recovery and retirement never re-home work to an unattested runtime
Watchdog, release reconciliation, drain and stale-runtime retirement paths SHALL
leave work pending when no attested cloud successor exists. Temporary,
emergency, development-labelled and fallback re-homing to an unattested runtime
SHALL be refused, including momentarily.

#### Scenario: No attested successor leaves work pending
- **WHEN** a stale cloud runtime is retired and the only reachable candidate
  runtime is unattested
- **THEN** the work remains pending, no assignment is transferred, and a refusal
  reason is recorded.

### Requirement: Cloud-only service is proved by a free-provider first answer
Acceptance SHALL include a brand-new user reaching a first answer using only a
free, zero-setup provider, served end to end on attested cloud runtime, with no
borrowed subscription and no automatic change to any existing user workflow.

#### Scenario: New user's first answer is cloud-attested and free-only
- **WHEN** a brand-new user sends a first message with no credential deposited
- **THEN** the answer is produced on an attested cloud runtime using a free
  provider, and no founder or third-party subscription is consumed.

### Requirement: Cloud custody invariants are verified read-only from hosted CI
Custody controls that application code cannot enforce SHALL be verified by
read-only cloud API reads executed on trusted hosted CI: the expected droplet
identity, the set of connectors serving the public tunnel, and the public DNS
target. Verification SHALL emit only
identifiers and booleans, SHALL NOT print credential values, SHALL NOT require
write scopes, and SHALL NOT introduce a new MCP tool, provider account or
privileged agent.

#### Scenario: A connector outside the expected droplet fails verification
- **WHEN** an active tunnel connector originates from an address outside the
  verified droplet address set
- **THEN** verification fails and reports the mismatch without printing any
  credential.

#### Scenario: Verification cannot run from an untrusted host
- **WHEN** the verification is attempted outside the trusted hosted CI runner
- **THEN** it does not execute and no cloud credential is exercised.
