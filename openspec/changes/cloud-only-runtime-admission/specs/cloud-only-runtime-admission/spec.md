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

### Requirement: The cached provenance observation is readable without re-observation
The platform SHALL expose the executing process's already-resolved provenance
observation through a non-mutating read that never invokes the resolver, never
initializes the observation cache, and never performs network or metadata I/O.
An observation that has not been resolved, that failed, or that was inherited
across a process-identity change SHALL read as an explicit `unknown` verdict;
`unknown` SHALL NOT be reported as cloud, SHALL NOT be reported as enforcement,
and SHALL NOT trigger a fresh resolution.

The read SHALL be exposed on the existing authenticated release-facts endpoint
as an optional field carrying only a sanitized fixed schema — verdict, a stable
reason token, booleans and the observation mode. It SHALL NOT carry an instance
identifier, an expected identifier, a hash of either, a network address, a
filesystem path or any secret. It SHALL be emitted only when the request's
already-resolved identity is the operational probe principal; every other
authenticated principal SHALL receive exactly the fields it receives today, and
unauthenticated requests SHALL remain rejected. No authentication rule,
permission or principal SHALL be widened to serve it.

The field SHALL be optional in the response schema: a consumer that does not
receive it SHALL treat provenance as unknown rather than inferring a verdict.
Consumers SHALL NOT infer from this endpoint the freshness of the running
binary, the current container incarnation, the state of workers other than the
one that answered, hardware attestation, or credential or data custody. A
diagnostic reporter of this field SHALL print only values the protocol defines,
matched exactly from the response it already fetched — an allowlist of known
values, never of token shapes, and with no normalization applied before
matching. Missing, mistyped and unrecognized values SHALL all report as
unknown, and the reporter SHALL NOT change the deployment gate's existing exit
semantics.

#### Scenario: A health read never resolves provenance
- **WHEN** the release-facts endpoint is read while the process has resolved no
  observation
- **THEN** no resolver, metadata client or network read is invoked
- **AND** the reported verdict is an explicit unknown, not cloud.

#### Scenario: A cached observation is stable across repeated reads
- **WHEN** a process resolves its startup observation once and the endpoint is
  read twice afterwards
- **THEN** both reads report the same cached verdict
- **AND** the resolver is invoked exactly once in total.

#### Scenario: An inherited observation does not read as the parent's verdict
- **WHEN** the observation object was resolved under a different process
  identity and is then read
- **THEN** the read reports unknown rather than the inherited verdict.

#### Scenario: Only the operational probe principal sees the field
- **WHEN** an authenticated principal other than the operational probe reads the
  endpoint
- **THEN** the response carries exactly the fields it carried before this change
- **AND** an unauthenticated request is still rejected.

#### Scenario: A malformed or missing reported value is unknown, never a pass
- **WHEN** the diagnostic reporter receives a response whose provenance field is
  absent, of the wrong type, or carries unexpected values
- **THEN** it prints unknown for those values and leaks no identifier
- **AND** the gate's pass, fail and cannot-determine exit codes are unchanged.

#### Scenario: A well-formed value the protocol does not define is refused
- **WHEN** a reported value is shaped like a valid token but is not a value the
  protocol defines — an identifier embedded in a reason, an unrecognized
  verdict, a mode asserting enforcement, or a value carrying trailing
  whitespace or a line break
- **THEN** the reporter prints unknown for it rather than echoing it.

### Requirement: Task claim admission enforces provenance on the non-optional refusal path
Assigned-task claim admission SHALL evaluate resolved provenance within the
same transaction that transfers ownership, and SHALL bind that evaluation to the
refusal predicate every claim traverses. It SHALL NOT depend on an optional
authority callback, so a caller that supplies no callback SHALL NOT thereby opt
out of the gate. Provenance evidence SHALL be resolved before the write
transaction is opened, and only the resulting trusted, process-owned value SHALL
be evaluated inside the compare-and-swap; no network request SHALL be issued
while the database write lock is held. Pre-claim consumer checks MAY remain as
diagnostics but SHALL NOT be the only enforcement.

The startup-origin observation SHALL resolve once per process before execution
authority is exercised. Admission SHALL reuse the immutable process-owned result
without per-operation network reads. A refused result SHALL NOT silently upgrade;
a restarted process SHALL resolve anew. Existing live lease, registration expiry
and per-universe authorization checks SHALL remain in force independently.

#### Scenario: Metadata outage after admitted startup does not create request-time polling
- **WHEN** an admitted process handles later operations and metadata becomes unreachable
- **THEN** no request-time metadata call is made, while live operation authority checks still apply.

#### Scenario: Restart cannot inherit old process evidence
- **WHEN** a new process starts after a previous process was admitted
- **THEN** it resolves its own bounded evidence and refuses if that evidence cannot be established.

#### Scenario: First enforcement starts with prepared expected identity
- **WHEN** an enforcement-capable candidate is started by deployment
- **THEN** expected identity is prepared and verified before startup, without prematurely publishing a successful release receipt.

#### Scenario: Redeployment preserves expected identity independently of success reporting
- **WHEN** a record-only candidate is redeployed or restarted, or deployment restores a compatible rollback target
- **THEN** expected identity remains available and matching, and receipt replacement does not erase it.

#### Scenario: Direct claim by an unadmitted process is refused
- **WHEN** an unadmitted process calls the assigned-task claim directly with a
  valid consumer lease, a ready pending cloud task, and no optional authority
  callback, bypassing the consumer loop's pre-check
- **THEN** no task is claimed and a refusal reason is recorded.

#### Scenario: Metadata resolution does not run under the write lock
- **WHEN** the cloud evidence source is unreachable and a claim is attempted
- **THEN** the evidence has already been resolved to a refusal value before the
  write transaction opened, and no outbound request is issued from within it.

#### Scenario: Admitted process claims and records the resolved class
- **WHEN** an admitted cloud process claims a ready cloud task
- **THEN** the claim succeeds and the recorded executor class is the resolved
  value, not a literal stamped by the caller.

### Requirement: Runtime registration is admitted and grants no provenance on its own
Runtime registration SHALL write the resolved provenance rather than a constant,
and authority SHALL be re-resolved when a registration is read. The existence of
a registration row SHALL NOT by itself confer execution or serving authority.

The process boot identifier SHALL be treated as an incarnation and liveness
marker only. It SHALL NOT be relied on as an identity, an ordered epoch, or
evidence of cloud origin, and no independent anti-replay guarantee SHALL be
claimed from it. Staleness SHALL continue to be governed by the existing
descriptor expiry, and no new storage schema or registry SHALL be introduced to
record the boot identifier.

#### Scenario: Unadmitted registration is refused
- **WHEN** an unadmitted process requests a runtime slot
- **THEN** registration refuses and no cloud-worker registration row is written.

#### Scenario: An existing row does not carry provenance
- **WHEN** a registration row written by an admitted cloud instance is later read
  by an unadmitted process
- **THEN** authority is refused because provenance is re-resolved on read, and
  the row itself grants nothing.

#### Scenario: Restarts and concurrent cloud workers are preserved
- **WHEN** an admitted cloud runtime restarts with a new boot identifier, or two
  admitted cloud workers run at the same time with different boot identifiers
- **THEN** both are admitted normally and neither is refused as a replay.

### Requirement: Serving startup, foreground and served execution refuse when unadmitted
Queue and registration admission SHALL NOT be relied on to cover foreground or
served provider execution, which do not traverse the assigned-task claim. Those
paths SHALL be covered by two boundaries only — serving startup, and the last
provider-authority boundary before a provider process is started.

Serving startup SHALL assert provenance before accepting any platform traffic
and SHALL exit rather than serve when unadmitted; there SHALL be no local or
degraded serving mode. Foreground conversation turns and served background
provider execution SHALL refuse before spawning any provider process, and the
executor class they record SHALL be the resolved value rather than a literal.

Per-universe, user-bound authority SHALL be preserved unchanged. Platform
provenance is an additional condition on the existing authority check and SHALL
NOT move, widen or narrow the authority a universe's owner holds.

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
NOT be presented as enforcement, as proof of the founder boundary, as
risk-free, or as an absolute security guarantee. Closure SHALL require the
refusal sites to be active and a deployed commit to be confirmed in production.

Custody and policy SHALL NOT be treated as established by a code label, an
identifier name, or a diagnostic that completed successfully. A check passing
against a local fixture or cloned data root SHALL NOT be reported as evidence
about production data, routing or credentials.

Implementation of the runtime resolver SHALL be gated on an actual executed
metadata diagnostic. No cloud fact SHALL be asserted from a verification that
has not yet run.

#### Scenario: Record-only mode does not report a closed boundary
- **WHEN** the resolver or the preflight is running in record-only mode
- **THEN** any status it reports states that enforcement is not active and the
  boundary is not closed.

#### Scenario: A local fixture pass is not a production claim
- **WHEN** the admission checks succeed against a developer fixture database or
  a cloned data root
- **THEN** the result is reported as a local self-consistency observation only,
  and no production authority, custody or data access is claimed from it.

#### Scenario: Unrun verification yields no cloud fact
- **WHEN** the bounded preflight has been written but has not yet produced an
  observation
- **THEN** no cloud fact is recorded from it and the runtime resolver
  implementation does not proceed on a predicted result.
