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

#### Scenario: Unadmitted process resolves to refusal, never to a fallback class
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

#### Scenario: Direct claim by an unadmitted process is refused
- **WHEN** an unadmitted process calls the assigned-task claim directly with a
  valid consumer lease and a ready, pending cloud task, bypassing the consumer
  loop's pre-check
- **THEN** no task is claimed and a refusal reason is recorded.

#### Scenario: Admitted process claims and records the resolved class
- **WHEN** an admitted cloud process claims a ready cloud task
- **THEN** the claim succeeds and the recorded executor class is the resolved
  value, not a literal stamped by the caller.

### Requirement: Runtime registration is admitted, instance-bound and not replayable
Runtime registration SHALL write the resolved provenance rather than a constant,
SHALL bind the admitted cloud instance identity and the process boot epoch, and
SHALL be re-validated when read. The existence of a registration row SHALL NOT
by itself confer execution or serving authority.

#### Scenario: Unadmitted registration is refused
- **WHEN** an unadmitted process requests a runtime slot
- **THEN** registration refuses and no cloud-worker registration row is written.

#### Scenario: A stale registration cannot be replayed
- **WHEN** a registration row admitted for one cloud instance and boot epoch is
  later read by a process that is unadmitted, or admitted to a different
  instance or boot epoch
- **THEN** authority is refused on read and the row grants nothing.

### Requirement: Serving startup, foreground and served execution refuse when unadmitted
Serving startup SHALL assert provenance before accepting any platform traffic
and SHALL exit rather than serve when unadmitted; there SHALL be no local or
degraded serving mode. Foreground conversation turns and served background
provider execution SHALL refuse before spawning any provider process.

#### Scenario: Unadmitted serving startup does not serve
- **WHEN** the serving process starts unadmitted
- **THEN** it exits non-zero without binding a platform listener or accepting a
  request.

#### Scenario: Unadmitted foreground or served turn spawns no provider
- **WHEN** a foreground conversation turn or a served background turn is
  requested on an unadmitted runtime
- **THEN** the turn refuses and no provider subprocess or model relay is started.

### Requirement: The platform has no code path that publishes off-cloud public ingress
The platform daemon, tray and packaged plugin runtime SHALL NOT contain a code
path that enrolls a Cloudflare tunnel connector, runs a named tunnel, or
publishes a quick/ephemeral public tunnel URL. The capability SHALL be removed
rather than gated on an environment variable or credential availability, because
a connector that receives a public request and then refuses it has already
consumed that request's share of public availability. Detection after the fact
SHALL NOT be treated as prevention.

#### Scenario: No shipped code path can enroll a connector
- **WHEN** the daemon, tray or packaged plugin runtime is started off cloud with
  valid local Cloudflare credentials and the production tunnel name available
- **THEN** no connector is enrolled and no public URL is published, because no
  shipped entry point offers that capability.

#### Scenario: An environment variable cannot re-arm local ingress
- **WHEN** every environment variable previously gating local tunnel startup is
  set truthy
- **THEN** no tunnel process is started.

### Requirement: Public ingress is admitted at the origin as a backstop, not by credential possession
The origin SHALL refuse tunnel-forwarded platform traffic when unadmitted,
independently of how the request was routed. Possession of a tunnel credential,
a public hostname or a proxied DNS record SHALL NOT admit platform work.

#### Scenario: Forwarded request to an unadmitted origin is refused
- **WHEN** a request arrives at an unadmitted origin through a valid public
  tunnel connector
- **THEN** the origin refuses before any universe work, model relay or storage
  write.

### Requirement: Recovery and retirement never re-home work to an unadmitted runtime
Watchdog, release reconciliation, drain and stale-runtime retirement paths SHALL
leave work pending when no admitted cloud successor exists. Temporary,
emergency, development-labelled and fallback re-homing to an unadmitted runtime
SHALL be refused, including momentarily.

#### Scenario: No admitted successor leaves work pending
- **WHEN** a stale cloud runtime is retired and the only reachable candidate
  runtime is unadmitted
- **THEN** the work remains pending, no assignment is transferred, and a refusal
  reason is recorded.

### Requirement: Free acceptance uses the user's own authorization, not a borrowed credential
Acceptance SHALL include a brand-new user who completes that user's own
OpenRouter OAuth PKCE authorization in their own browser, returns through the
automatic callback, approves an eligible free model, and receives a first actual
tool-capable response served end to end on an admitted cloud runtime. Key
copying, borrowed or founder subscriptions, account-specific patches, and any
automatic change to an existing user's workflow SHALL NOT be used. A
"zero-setup" or "no-credential-required" provider SHALL NOT be asserted as the
mechanism.

#### Scenario: New user's first answer runs on their own authorized free model
- **WHEN** a brand-new user authorizes OpenRouter through OAuth PKCE, the
  callback returns automatically, and the user approves an eligible free model
- **THEN** their first tool-capable response is produced on an admitted cloud
  runtime using that user's own grant, and no founder or third-party
  subscription is consumed.

#### Scenario: A borrowed credential does not satisfy acceptance
- **WHEN** a first answer is produced from any credential the user did not
  themselves authorize
- **THEN** acceptance is not satisfied and the result is recorded as a failure.

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

#### Scenario: Missing permission is an unknown, never a pass
- **WHEN** a credential is absent, lacks the required read scope, or the provider
  API returns a non-success status
- **THEN** the affected fact is reported as a typed `unknown` with a reason code
  and the overall verification does not report success.

#### Scenario: Verification mutates nothing and leaks nothing
- **WHEN** verification runs
- **THEN** it issues read-only requests only, performs no infrastructure change,
  and its output contains no raw API body, credential, address, hostname,
  connector identifier or user data.

### Requirement: Observation-only stages are reported as incomplete
Record-only stages SHALL report the cloud-only boundary as not closed. While
the resolver or the custody preflight runs in record-only mode, observations SHALL
NOT be presented as enforcement, as proof of the founder boundary, or as an
absolute security guarantee. Closure SHALL require the refusal sites to be
active and a deployed commit to be confirmed in production.

#### Scenario: Record-only mode does not report a closed boundary
- **WHEN** the resolver or the preflight is running in record-only mode
- **THEN** any status it reports states that enforcement is not active and the
  boundary is not closed.
