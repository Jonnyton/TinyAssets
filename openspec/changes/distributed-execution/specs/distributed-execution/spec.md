# Distributed execution

This delta extends the canonical as-built `distributed-execution` capability.
It does not replace the shipped `runner/v1` and detached-diagnostic
requirements, and it does not claim the requirements below are implemented
until their tasks land.

## ADDED Requirements

### Requirement: The first apply slice is dark, fake-only, and production-denied

The first apply slice SHALL provide a final-shaped signed-authority contract
spine only through a test-owned fake composition root. It SHALL NOT register a
production route, dispatch a provider, resolve a credential, call `run_graph`,
consume an admission or queue claim, create a GitHub effect, move money, enroll
a live daemon, select market capacity, deploy, or supply a real sandbox backend.
Completing this slice SHALL NOT be represented as completing V1.

The fake root SHALL require an explicit test sentinel and test-owned temporary
state. Construction in production or unknown runtime mode, registration with a
production app/router, use of a non-test durable path, or injection of a
caller-selected issuer/key/verifier SHALL fail before signing, leasing,
dispatching, or persisting authoritative state. No production path SHALL fall
back to the fake root.

#### Scenario: focused tests traverse the dark spine

- **WHEN** a focused test builds the fake root with the explicit test sentinel
  and submits canonical test capsule, grant, candidate, blob, and terminal facts
- **THEN** it can exercise verification, fencing, completion, and replay through
  final-shaped contracts
- **AND** no provider, credential, queue, graph, route, deployment, GitHub,
  enrollment, market, or money adapter is invoked

#### Scenario: production cannot construct the fake root

- **WHEN** production or unknown runtime code attempts to construct or register
  the fake composition root
- **THEN** construction fails with a stable configuration error before any
  authority record or lease is created
- **AND** there is no unsigned, unavailable-to-fake, or fake-key fallback

### Requirement: M1, M2, and M3 share evidence shape but not authority constructors

Positive authority SHALL be re-derived at the decision point through exactly
one honest mechanism: M1 platform signature verification, M2 exact-content
re-derivation, or M3 fresh external verification. Mutable rows, events,
projections, receipts, requests, caches, descriptors, and leases MAY narrow,
reject, rate-limit, deduplicate, or record a decision but SHALL NOT create or
expand positive authority.

All three mechanisms MAY return a sealed `Verified[T]` evidence shape, but each
mechanism SHALL mint it only after its own verification. M2 and M3 SHALL NOT
route through the M1 `RecordVerifier`; an M1 signature over a digest SHALL NOT
substitute for reading and hashing the M2 content; a stored M3 result SHALL NOT
substitute for fresh external confirmation.

#### Scenario: signed blob metadata is not blob proof

- **WHEN** a valid M1 record names a blob digest but the resolved bytes do not
  hash to that digest
- **THEN** M2 verification refuses to mint `Verified[BlobRef]`
- **AND** the valid M1 signature does not authorize candidate acceptance

#### Scenario: a cached external receipt cannot mint M3 evidence

- **WHEN** a mutable row says an external protected action succeeded but fresh
  external confirmation is unavailable or contradictory
- **THEN** no M3 `Verified` evidence is minted
- **AND** the row may only keep the action pending or rejected

### Requirement: Verified evidence is sealed and minted only after verification

`Verified[T]` SHALL be frozen, final, non-subclassable, non-copyable,
non-pickleable, and unavailable to ordinary direct construction. Only reviewed
M1, M2, and M3 mechanism adapters SHALL receive the package-private mint
capability. Evidence SHALL identify its mechanism, domain/purpose, evidence
digest, and verifier or trust-set identity without treating those diagnostic
fields as authority by themselves.

Test fakes SHALL exercise the same mechanism adapters using test-owned facts;
they SHALL NOT bypass verification by directly invoking the mint capability.

#### Scenario: consumer code cannot self-assert verified authority

- **WHEN** ordinary consumer or test code attempts direct construction,
  subclassing, copying, pickling, or token-free minting of `Verified[T]`
- **THEN** the attempt fails
- **AND** an authority sink accepts evidence only from a successful
  mechanism-specific verifier

### Requirement: Signed execution records use immutable domain contracts

Every signed execution record SHALL use RFC 8785/JCS canonical JSON,
JSON-type-strict validation, bounded integers, canonical lowercase digests, and
an exact purpose-specific domain separator in the signature preimage. The
domain contract SHALL classify every payload field as row-bound,
specialized-validated, or documented inert. Unknown domains, versions, fields,
unclassified fields, and caller-supplied binding exceptions SHALL fail closed.

The final-shaped record set SHALL include:

- a platform-signed capsule binding owner, audience daemon, job, capsule,
  attempt/generation, source, policy, limits, and time bounds;
- a platform-signed grant binding owner, daemon, job, capsule digest, lease,
  generation/fence, capability ceiling, expiry, and idempotency;
- a device-signed candidate binding owner, daemon/device, job, capsule, lease,
  generation/fence, result digest, canonical blob set, status, and idempotency;
  and
- a platform-signed terminal record binding job, capsule, lease,
  generation/fence, accepted candidate/result/blob-set digest, terminal state,
  and idempotency.

A valid device signature SHALL prove possession only. Candidate acceptance
SHALL still require the exact M1 grant plus fresh M2 content proofs.

#### Scenario: caller cannot unbind an authority field

- **WHEN** a caller asks the verifier to ignore owner, daemon, job, capsule,
  lease, generation, fence, result, or another signed field
- **THEN** verification refuses the request because the domain contract is
  immutable
- **AND** no caller-controlled `unbound_fields` equivalent exists

#### Scenario: cross-domain signature reuse fails

- **WHEN** canonical bytes signed for a capsule domain are presented as a grant,
  candidate, or terminal record
- **THEN** verification fails on the domain-separated signature input
- **AND** no authority is created

### Requirement: Generation floors and fences survive mutable-state restore

Each claim SHALL allocate a monotonically increasing generation/fence within
the durable job evidence namespace. The acceptance floor SHALL include the
highest fence persisted in the append-only evidence ledger. Restoring or
editing a mutable current-state row to an older generation SHALL NOT revive a
superseded grant, candidate, completion, or replay result.

Candidate and completion decisions SHALL compare owner, daemon, job, capsule,
lease, generation, fence, and idempotency across independently verified facts.

#### Scenario: restored superseded generation fails closed

- **GIVEN** a later generation has been durably evidenced
- **WHEN** the mutable job or lease projection is restored to an earlier
  apparently-active generation and a correctly signed old record is replayed
- **THEN** the durable generation floor rejects it
- **AND** no candidate or terminal state is accepted

### Requirement: Idempotency and replay verify authoritative facts first

Every authority transition SHALL bind a stable idempotency key into its
canonical record. Retrying byte/content-identical verified evidence SHALL
return the same receipt. Reusing a key with different verified content SHALL
fail closed.

Terminal replay SHALL verify domain, schema, signature, bindings,
generation/fence, and content before considering a row terminal. It SHALL
ignore unverifiable junk for positive authority, collapse byte/content-identical
valid attestations, and reject two distinct valid terminal facts as stored-state
corruption. Mutable terminal columns SHALL remain projections only.

#### Scenario: junk row cannot veto a valid replay

- **GIVEN** one valid terminal attestation and one unverifiable inserted row
- **WHEN** replay runs after restart
- **THEN** it re-derives the same verified terminal fact from the valid
  attestation
- **AND** the junk row grants no authority and does not create a false conflict

#### Scenario: two distinct valid terminal facts fail closed

- **GIVEN** two separately valid terminal attestations for incompatible facts
- **WHEN** replay runs
- **THEN** replay raises stored-state corruption
- **AND** it chooses neither fact by row order, timestamp, or mutable status

### Requirement: Blob acceptance uses fresh M2 proof and one lock order

Candidate acceptance SHALL resolve each exact blob under the physical storage
root, read its bytes, recompute size and digest, and mint
`Verified[BlobRef]` only after the proof succeeds. Completion SHALL consume
fresh verified proofs rather than raw references or mutable blob-index rows.

Candidate and completion mutations SHALL acquire the physical blob-root
coordinator before the SQLite transaction. Coordinator identity SHALL derive
from physical directory identity rather than normalized path spelling and
SHALL fail closed when identity cannot be established. The blob index SHALL be
reloaded, validated, mutated, and atomically persisted as operation-local state
under that lock. Evidence-table SQL, columns, constraints, indexes, triggers,
and namespace SHALL be exactly validated and SHALL never be auto-repaired.

#### Scenario: aliases cannot bypass blob serialization

- **WHEN** two writers address the same physical blob root through supported
  case, separator, extended-path, junction/symlink, or UNC/drive aliases
- **THEN** they acquire the same coordinator before either SQLite transaction
- **AND** both updates complete without split index state, deadlock, or
  `database is locked`

#### Scenario: stale index cannot resurrect collected authority

- **WHEN** one instance holds an old in-memory index while another collects a
  binding and commits a newer index
- **THEN** the stale instance reloads under the shared physical-root lock
- **AND** it cannot persist the removed binding or mint blob proof from it

### Requirement: Trust roots and signer custody precede production authority

Production M1 verification SHALL use purpose-separated public keys from a
signed, release-pinned trust manifest. Production private keys SHALL remain
outside control-plane and user-code memory behind non-exporting,
schema-specific signer capabilities. Every returned signature SHALL be locally
reverified before authoritative persistence.

No caller request, environment-selected raw key, mutable database row, worker
descriptor, queue claim, admission receipt, auth grant, or provider credential
SHALL select the active M1 key. WorkOS identity SHALL remain M3 and SHALL NOT be
platform re-signed.

Until trust-manifest distribution, rotation, revocation, custody, and the sole
production composition root are implemented and approved, every production
execution-authority route SHALL remain absent or fail closed.

#### Scenario: missing production custody cannot fall back to test keys

- **WHEN** production authority is requested before a valid pinned trust set
  and signer capability are available
- **THEN** the request fails before grant or completion
- **AND** no test key, generated local key, caller key, unsigned record, or
  mutable-row authority is used

### Requirement: Admission, scheduling, provider-attempt, and B2 evidence remain distinct

The system SHALL keep admission, scheduling, provider-attempt, and B2
execution evidence in non-promotable authority domains.

Request admission receipts, epoch-2 tasks, #1697 worker descriptors, internal
scheduling leases/heartbeats, provider-attempt receipts, B2 signed execution
grants/leases, device-signed candidates, and platform-signed terminal records
SHALL use distinct types and authority domains. They MAY narrow or reject one
another only through an explicit verified decision. None SHALL mint, widen,
substitute for, wrap as, or promote another artifact's positive authority.

The #1697 descriptor fields (`queue_protocol_version=2`, capability,
build/config SHA, boot ID, worker ID, runtime instance ID, universe, and
90-second liveness) SHALL remain server/release derived and preserved during
later integration. A valid descriptor or won epoch-2 scheduling claim SHALL
not create owner, provider, credential, payment, execution, candidate, or
terminal authority.

#### Scenario: scheduling winner without B2 grant cannot execute

- **GIVEN** a live matching #1697 descriptor, a valid admission receipt, and a
  won epoch-2 internal scheduling lease
- **WHEN** no valid owner/daemon/job/capsule/lease/generation/fence B2 grant is
  presented
- **THEN** no external execution lease, provider call, candidate acceptance, or
  terminal receipt is created
- **AND** the already-running internal reservation remains governed only by its
  own heartbeat, cancellation, terminal, expiry, and recovery lifecycle
- **AND** no internal lifecycle transition promotes it into B2 execution
  authority

#### Scenario: provider-attempt receipt cannot become execution authority

- **WHEN** a valid provider-attempt receipt names a provider result
- **THEN** it may supply result-local observability or learning evidence
- **AND** it cannot mint a B2 grant, credential, payment right, accepted
  candidate, or terminal fact

### Requirement: Backend admission is bound outside the frozen runner wire

Distributed execution SHALL maintain a release-pinned
`BackendProfileBindingV1` registry that binds an exact backend identity and
release digest to its protocol version, supported workload/profile pairs,
supported inner request/result schemas and `JobCapability` values, closed
guarantee-property set, fixed owner-reference verifiers, preflight and
actual-launch evidence verifiers, and trust-set identity. A request, worker,
queue row, provider/backend response, environment variable, mutable diagnostic,
or caller-selected value SHALL NOT create, select, modify, or widen a binding.

The exact closed `os_isolated` guarantee-property identifiers SHALL be
`kernel_process_boundary`, `filesystem_default_deny`,
`network_default_deny`, `cpu_limit`, `memory_limit`, `process_limit`,
`wall_time_limit`, `output_limit`, `platform_secrets_absent`,
`undeclared_devices_absent`, `bounded_cleanup`, and
`request_bound_evidence`. A `vm_isolated` binding SHALL prove that entire set
plus `guest_kernel_boundary` and `host_devices_default_deny`. Unknown property
identifiers SHALL deny. Admission SHALL use proved property-set inclusion;
`os_isolated`, `vm_isolated`, or another label SHALL be derived shorthand only
and SHALL NOT substitute for the property set.
Policy, projection, egress, credential, and authority objects SHALL remain
owner-defined opaque reference/digest pairs. This capability SHALL bind fixed
verifiers for those pairs but SHALL NOT define their taxonomies, reveal their
contents, or claim a complete compatibility matrix.

Pre-launch admission SHALL resolve the trusted logical
`ExecutionRequirement`, its owner-defined reference/digest pairs, the exact
release-pinned backend binding, and the exact planned launch configuration. It
SHALL obtain fresh authenticated `BackendPreflightEvidenceV1` covering the
binding/release, capability self-test, planned-configuration digest, and
freshness interval. Preflight evidence SHALL prove only current capability and
the exact planned configuration; it SHALL NOT attest a future process,
enforcement event, cleanup, result, or complete guarantee set.

For an existing runner job, distributed execution SHALL canonicalize the
unchanged `runner-job/v1` request and seal a purpose-separated
`ExecutionAdmissionCapsuleV1` that binds at least the exact inner `job_id`,
inner request schema/digest, logical requirement contract/digest, backend
binding digest, planned-launch digest, preflight-evidence digest,
independently verified authority-evidence digest, issuance/expiry, capsule ID,
and signing-key ID. The trusted transport SHALL carry that capsule and
preflight evidence beside—not inside—the inner request. The backend SHALL
verify the seal, expiry, and every binding before launch.

The outer admission capsule SHALL authenticate admission facts only. It SHALL
NOT mint, wrap, replace, or widen provider, B2, credential, scheduling,
payment, or effect authority. Ordinary provider work SHALL retain the
#1784-owned `ProviderInvocation` carrier; accepted-market work SHALL retain the
B2/B13 carrier; runner-backed work SHALL use the admission sidecar only in
addition to its independently required authority evidence.

These four records SHALL define the runner-backed instantiation. Ordinary
provider and accepted-market owners SHALL bind equivalent request-specific
evidence through their native carriers and SHALL NOT invent a runner `job_id`
or reuse the runner sidecar.

After launch, the selected backend SHALL emit authenticated
`BackendExecutionEvidenceV1` under the verifier and trust set fixed by the
binding. That evidence SHALL bind the admission-capsule digest, inner `job_id`,
backend execution identity, binding digest, actual-launch digest, inner-result
digest, proved property identifiers, a sorted tuple of exact
`(property_id, evidence_ref, evidence_digest)` entries, timestamps, and
cleanup-evidence reference/digest. Distributed execution SHALL
recompute the inner-result digest and verify every binding and
property-specific proof before any output becomes a successful runner, graph,
NodeBid, provider, or fallback result.

`RUNNER_PROTOCOL_VERSION`, `JOB_REQUEST_SCHEMA_VERSION`,
`JOB_RESULT_SCHEMA_VERSION`, `SandboxJobRequest`, `SandboxJobResult`,
`EnforcementReceipt`, every `JobCapability`, and the capability/action mapping
SHALL remain unchanged. `RunnerCapabilities`, `isolation_enforced`, installed
executable probes, `EnforcementReceipt`, tier labels, queue/admission receipts,
and a valid admission seal without verified actual-launch evidence MAY reject
or diagnose but SHALL NOT prove the complete guarantee set.

Missing, stale, malformed, mismatched, unsupported, unknown, caller-controlled,
or unverifiable binding, reference, verifier, trust set, sidecar, preflight
record, planned configuration, property, or launch record SHALL fail closed
through the shared terminal `ExecutionAdmissionError` taxonomy. Invalid
actual-launch evidence SHALL use
`ExecutionAdmissionError(reason=backend_evidence_invalid)`, and no backend
output SHALL become success or fallback input. A backend failure after valid
dispatch with complete valid evidence SHALL remain a backend result rather
than an admission error.

Test-owned roots MAY exercise these records in dark verification. A production
admission capsule or evidence verifier SHALL remain unavailable until the
task-7.2 production trust-manifest distribution, purpose-separated signer
custody, rotation/revocation, and persistent-store boundary are explicitly
host-approved and implemented. Missing production custody SHALL NOT fall back
to a test key, generated local key, unsigned sidecar, or mutable registry row.

#### Scenario: a caller cannot choose a stronger binding

- **WHEN** a request, worker, queue row, provider response, environment value,
  or diagnostic names a backend/profile/property set different from the
  release-pinned binding selected by trusted admission
- **THEN** admission fails before launch with shared `ExecutionAdmissionError`
- **AND** no caller label or boolean upgrades the proved guarantee set

#### Scenario: the outer capsule binds the unchanged inner job

- **WHEN** trusted code admits an existing `runner-job/v1` source-exec request
- **THEN** the sealed outer capsule binds its exact `job_id`, schema, canonical
  request digest, logical requirement, backend binding, planned configuration,
  preflight evidence, and independent authority evidence
- **AND** the inner request/result schemas, `EnforcementReceipt`, capabilities,
  actions, and statuses remain unchanged

#### Scenario: preflight cannot attest the future execution

- **WHEN** fresh capability and self-test evidence matches the selected binding
  and exact planned launch configuration
- **THEN** pre-launch admission may authorize dispatch to proceed
- **AND** it does not prove actual enforcement, cleanup, result integrity, or
  the complete guarantee set

#### Scenario: actual-launch evidence is request-bound

- **WHEN** a backend returns output and execution evidence
- **THEN** distributed execution verifies the capsule, job, execution,
  binding, actual configuration, result digest, complete property set, and
  cleanup evidence before accepting output
- **AND** evidence copied from another job, capsule, configuration, backend,
  execution, or result fails closed

#### Scenario: diagnostic receipts cannot prove containment

- **WHEN** `RunnerCapabilities`, an installed-executable probe, or the inner
  `EnforcementReceipt` reports isolation or cleanup without valid bound
  `BackendExecutionEvidenceV1`
- **THEN** it grants no guarantee property and no successful output
- **AND** the run terminates through shared `ExecutionAdmissionError`

#### Scenario: admission binding does not promote authority

- **WHEN** an admission capsule and complete backend evidence are valid but the
  independently required provider or B2 authority is absent, stale, or wrong
- **THEN** no provider call, external execution lease, candidate, or terminal
  fact is created
- **AND** the admission records cannot be wrapped or promoted into that
  authority

#### Scenario: production cannot fall back to a test admission seal

- **WHEN** production dispatch is attempted before the approved production
  trust set, signer custody, and persistent-store boundary exist
- **THEN** admission fails before capsule creation or backend launch
- **AND** no test key, generated key, unsigned sidecar, or mutable binding row
  is used

#### Scenario: a VM label with weaker properties is rejected

- **WHEN** a binding says `vm_isolated` but lacks one base guarantee, a distinct
  guest-kernel boundary, or default-deny host-device passthrough
- **THEN** property-set inclusion fails before output acceptance
- **AND** the tier label cannot override the missing proof

### Requirement: Stale PRs are extracted onto current main, not integrated wholesale

Implementation SHALL port only reviewed behavior and non-vacuous mutation tests
from stale PRs onto current main. It SHALL NOT merge, rebase, or cherry-pick
wholesale #1472, #1491, #1477, #1478, #1479, #1481, or #1487. Each extraction
SHALL begin with a current-main failing test and SHALL record the exact source
PR/commit and current-main replacement.

Extraction order SHALL be: #1472 contract/test inventory; #1477 minimal M1/B2
primitives; #1479 immutable domain contracts; #1481 generation/evidence/replay;
#1487 blob/lock/table hardening; #1491 daemon key/thumbprint binding when its S3
sites exist; and #1478 recreated current-path CI gates after test names
stabilize. PR #1572 SHALL be excluded.

#### Scenario: stale lineage cannot overwrite current epoch-2 work

- **WHEN** a useful stale-PR test or contract is selected for extraction
- **THEN** it is recreated against current main with a failing-before/fixed-after
  proof
- **AND** unrelated runtime, queue, descriptor, mirror, deployment, status, and
  plan changes from the stale branch are not imported

### Requirement: The complete distributed-execution program remains an active obligation

The change SHALL retain vertical slices V1-V8, stages S0-S16, and backlog items
B01-B44 until each is implemented with its named proof or an explicitly
approved superseding decision carries the obligation and provenance forward.
Completing D0 or any vertical slice SHALL list what it closes and SHALL NOT
delete, defer out of the change, or describe later obligations as unnecessary
to the program.

V1 SHALL still require a real persisted authenticated signed-completion path;
V2 confined owner-daemon execution; V3 exactly-once reviewable GitHub PR open;
V4 live B2 and load proof; V5 source/private delivery; V6 public market B2; V7
live B3/private-market policy; and V8 protected merge plus adjacent authority
closure.

#### Scenario: D0 completion preserves the full ledger

- **WHEN** every dark-spine test passes
- **THEN** D0 may be reported complete
- **AND** V1-V8, S0-S16, and every unlanded B01-B44 item remain open with their
  next proof

### Requirement: Live activation requires integrated review and rendered proof

The system SHALL block live activation until every applicable integrated
review, authority, runtime, and user-surface gate has passed.

No production route, live enrollment, enforcement flip, credential/provider
execution, GitHub mutation, market/money behavior, deployment, or rendered
acceptance test SHALL proceed until the production trust/custody prerequisites
are approved, the integrated current-main candidate passes focused and
semantic mutation tests, both current model families review the same candidate,
and the applicable CPython 3.11, mirror, concurrency/load, and public canary
gates pass.

Final acceptance of a user-visible execution path SHALL use a rendered chatbot
conversation through the live connector and SHALL check post-fix real-user
clean-use evidence. If no clean use exists yet, a dated watch SHALL remain
instead of claiming proven live use.

#### Scenario: dark success cannot authorize live rollout

- **WHEN** D0 is green but production custody, integrated review, or live proof
  is absent
- **THEN** all production execution-authority routes remain absent or disabled
- **AND** the change is reported as dark contract progress only

### Requirement: Rollback never downgrades authority

Rollback SHALL never replace verified authority with a weaker mutable,
unsigned, fake, scheduling, or legacy authority source.

Before production persistence, D0 rollback MAY remove the test-only root,
fixtures, and unused dark modules while preserving the canonical shipped
runner and diagnostic behavior. After durable B2 evidence exists, rollback MAY
stop new claims and leave work pending but SHALL retain trust manifests,
generation floors, evidence ledgers, signatures, blob bindings, and terminal
attestations required for audit and replay.

Rollback SHALL NOT reset a fence, convert signed authority to row authority,
bulk-sign mutable legacy data, auto-repair an evidence ledger, fall back to fake
or unsigned mode, execute through the legacy JSON queue/platform worker, or
promote an internal scheduling lease into B2 authority.

#### Scenario: signer outage leaves work pending

- **WHEN** a production signer or external authority becomes unavailable during
  a staged rollout
- **THEN** new authority-dependent work remains pending or fails closed
- **AND** rollback does not widen authority or reinterpret mutable state as a
  successful grant or completion
