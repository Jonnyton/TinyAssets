# cloud-only-runtime-admission Specification

## Purpose
Define process-owned application admission for cloud platform serving and the
covered execution boundaries. Application admission is neither hardware
attestation nor proof of exclusive credential custody or all-worker coverage.

## Requirements

### Requirement: Process admission uses bounded cloud evidence, not local labels
The platform SHALL resolve cloud provenance from the fixed internal metadata
source matched against typed expected-instance state prepared by deployment in
the canonical data volume. Missing, malformed, unreachable, redirected,
oversized or mismatched evidence SHALL refuse admission. Environment values,
hostnames, boot identifiers, copied checkouts and registration rows SHALL NOT
substitute for that evidence. Test injection SHALL NOT create a production
configuration bypass.

#### Scenario: A copied deployment cannot admit itself through labels
- **WHEN** a process has deployment-like labels but lacks matching cloud evidence
- **THEN** its provenance is not-cloud and the guarded platform boundaries refuse.

#### Scenario: Expected identity is prepared before candidate startup
- **WHEN** the deployment cannot freshly prepare and install expected identity
- **THEN** it stops before replacing the running candidate; an old file is not a pass.
- **AND** successful preparation remains separate from the mutable release receipt.

### Requirement: Admission is process-owned and reused without request-time probing
The observation SHALL resolve once per process and preserve a refused result
for that process lifetime. Restart or a process-identity change SHALL require
fresh observation. Its non-mutating peek SHALL perform no metadata, filesystem
or network I/O, and SHALL not initialize the observation. Unobserved or inherited
state SHALL be unknown and not admitted. Per-operation authority checks SHALL
remain independent and live.

#### Scenario: Metadata fails after admitted startup
- **WHEN** an admitted process handles another request after metadata becomes unavailable
- **THEN** admission uses the process observation without another metadata request
- **AND** current lease and universe-authority checks still apply.

#### Scenario: A refused process stays refused
- **WHEN** metadata later becomes reachable in the lifetime of a refused process
- **THEN** the cached refusal does not silently upgrade.

### Requirement: Assigned claims enforce admission within the mandatory transaction check
Assigned-task claims SHALL resolve observation before opening their write
transaction and read only cached admission within the mandatory claim predicate.
Omitting the optional authority callback SHALL NOT bypass admission. No metadata
request SHALL run under the claim write lock. Refused work SHALL remain pending
and report the stable `platform_not_cloud` reason through existing diagnostics.

#### Scenario: Direct assigned claim without an authority callback
- **WHEN** an unadmitted process directly attempts an otherwise valid assigned claim
- **THEN** no claim is acquired, even without an optional authority callback.

### Requirement: Legacy cloud activation claims and resumes enforce admission
The Epoch2 adapter's cloud-activation claim and resume paths SHALL resolve
observation before entering their store transaction and check only cached
admission in the mandatory lifecycle predicate. A persisted cloud descriptor
SHALL NOT substitute for process admission. Existing generic and non-cloud
activation semantics SHALL remain unchanged; preserving those storage operations
SHALL NOT grant platform serving or provider-execution authority.

#### Scenario: A stored cloud descriptor cannot authorize a legacy claim
- **WHEN** an unadmitted process presents a valid cloud activation and descriptor
- **THEN** its claim is refused and the task remains pending.

#### Scenario: Admitted cloud lifecycle ordering is preserved
- **WHEN** an admitted process claims or resumes a valid cloud activation
- **THEN** observation resolution completes before the store transaction begins
- **AND** the lifecycle predicate reads only the cached observation.

### Requirement: Worker registration and existing-row eligibility require process admission
`ensure_daemon_runtime` SHALL require admission before reading or creating its
cloud-worker slot. Existing exact-worker eligibility SHALL check cached process
admission before considering the stored row. A restored or copied registration
SHALL grant no execution authority. Existing ownership, model binding, expiry,
incarnation and worker-matching requirements SHALL remain in force.

Publishing or refreshing a non-null queue descriptor SHALL require admission
before reading the registration, including an unchanged-descriptor fast return.
Clearing a descriptor SHALL remain allowed as revocation with the existing exact
worker checks; it SHALL NOT publish or renew execution capacity.

#### Scenario: Stored registration cannot admit an unadmitted process
- **WHEN** an unadmitted process presents an existing worker registration
- **THEN** exact-worker eligibility refuses rather than inheriting the row's authority.

#### Scenario: An unadmitted process cannot extend a descriptor lifetime
- **WHEN** an unadmitted process attempts to publish or refresh a queue descriptor
- **THEN** the operation refuses with `platform_not_cloud` and leaves the descriptor unchanged.

### Requirement: Platform serving and provider boundaries refuse unadmitted execution
Platform server startup and its serving lifespan SHALL require admission before
starting platform services or serving traffic. The canonical server entrypoint
SHALL exit nonzero on refusal, including stdio, without a degraded local mode.
Foreground-run and served-background provider authority and launch boundaries
SHALL refuse before provider execution and derive their cloud executor class
from admitted observation rather than an unconditional label. Existing
user-bound permissions SHALL not be widened by cloud admission.

The agent-runtime provider execution service SHALL also derive its executor
class from cached admitted observation within its authority transaction. An
unobserved or refused process SHALL mint no provider receipt, execution claim or
invocation reservation, and SHALL invoke no provider. Reading an already-settled
outcome SHALL NOT cause another provider invocation.

#### Scenario: Unadmitted canonical server startup
- **WHEN** the server is launched without admission
- **THEN** it exits with code78 and sanitized `platform_not_cloud` refusal before serving.

#### Scenario: Foreground or served-background provider call is unadmitted
- **WHEN** an unadmitted process reaches either covered provider boundary
- **THEN** it refuses before spawning the provider or using its execution authority.

#### Scenario: Unadmitted direct agent-runtime provider execution
- **WHEN** an otherwise-ready invocation reaches the execution service on an unadmitted process
- **THEN** it refuses with `platform_not_cloud`, creates no provider-authority rows, and makes no provider call.

### Requirement: Origin admission is an outer cached-only backstop
The outer origin wrapper SHALL refuse unadmitted HTTP with503, no-store and only
the sanitized `platform_not_cloud` error, and SHALL close unadmitted websockets
with1011. No public or authenticated route SHALL bypass this guard. Lifespan
SHALL pass to the guarded startup path. Request handling SHALL never initialize
provenance. An origin refusal SHALL NOT be described as prevention of off-cloud
tunnel enrollment or as exclusive tunnel-token custody.

#### Scenario: Unobserved origin receives a release-facts request
- **WHEN** a request reaches an origin with no process observation
- **THEN** it returns503 without release data or a metadata read.

### Requirement: Assigned consumer startup and polling gate recovery work
An enabled assigned consumer SHALL require process admission before credential
scavenging or coordinator startup and before polling performs maintenance,
capacity publication, automatic submissions or task recovery. Disabled consumers
SHALL retain their no-start/no-poll behavior. No admitted successor SHALL mean
pending work remains unexecuted rather than a personal-desktop fallback.

#### Scenario: Unadmitted consumer cannot perform recovery
- **WHEN** an enabled unadmitted consumer starts or polls
- **THEN** it refuses before performing recovery or starting its coordinator.

### Requirement: Readback describes application guards without claiming custody
The authenticated pulse field SHALL follow the named-canary contract in
live-mcp-connector-surface. `application_admission` and `enforced=true` SHALL
describe the installed guard policy, not credential custody, hardware
attestation, binary freshness or proof about every worker. Missing observations
SHALL never be counted as cloud-boundary acceptance.

#### Scenario: A guard-policy report is not full cloud-boundary proof
- **WHEN** the answering process reports enforced application admission
- **THEN** consumers do not infer exclusive custody or completion of free-user onboarding.

### Requirement: Explicit stale-fleet retirement is admitted maintenance
The explicit stale-fleet retirement tool SHALL require process cloud admission
at its apply write boundary, before constructing the write store or writing a row, and SHALL
raise the single sanitized `platform_not_cloud` refusal otherwise. Its read-only
dry run SHALL remain ungated. The existing reviewed-plan confirmation (plan
digest plus both exact counts) and the per-row compare-and-set fences SHALL
remain in force. An admitted operator retirement SHALL cancel exactly the
approved stale tasks and retire exactly the approved stale runtimes; it assigns,
re-homes and mints nothing, so it SHALL NOT be treated as an admitted successor
for any pending task. The command-line entrypoint SHALL report the refusal
through its existing sanitized JSON error channel with exit status 2, printing
no plan output and no traceback.

#### Scenario: Unadmitted confirmed apply mutates nothing
- **WHEN** an unadmitted process applies a stale-fleet plan whose digest and
  both counts match the freshly rebuilt plan
- **THEN** it refuses before constructing the write store, the approved task
  remains pending, its runtime remains provisioned, and the entrypoint exits 2
  with only the sanitized refusal on stderr.

#### Scenario: Unadmitted dry run still reports the plan
- **WHEN** an unadmitted process runs the read-only dry run
- **THEN** it succeeds, prints the plan, and mutates nothing.
