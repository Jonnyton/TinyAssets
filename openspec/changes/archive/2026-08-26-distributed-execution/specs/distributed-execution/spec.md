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

### Requirement: Backend bindings and request-bound evidence are sealed outside runner/v1

Distributed execution SHALL own four immutable versioned records outside the
frozen runner wire:

- M1-signed static `BackendProfileBindingV1`, schema
  `execution-backend-profile/v1`, SHALL bind the signing key, binding ID,
  activation generation, backend implementation and release digest, protocol,
  one execution profile, supported job capabilities and guarantee property
  IDs, planned-configuration schema, preflight and launch-evidence contract
  IDs/digests, producer identity, authenticity mechanism, evidence-key custody,
  reviewed verifiers, trust set, revocation reference/digest, and issue/expiry
  times. It SHALL NOT contain a current self-test result or a per-request
  planned configuration.
- Fresh `BackendPreflightEvidenceV1`, schema
  `execution-backend-preflight/v1`, SHALL bind one unguessable `admission_id`,
  `job_id`, full inner-request digest, profile-binding and backend-release
  digests, capability/self-test and planned-configuration digests, producer,
  verifier, trust set, revocation generation, observation time, and expiry.
- Purpose-separated M1-signed `ExecutionAdmissionCapsuleV1`, schema
  `execution-admission-capsule/v1`, SHALL bind signing key, capsule ID, the
  shared `admission_id`, `job_id`, inner schema and full request digest,
  complete trusted execution requirement by value/digest, profile-binding,
  preflight, and planned-configuration digests, B2/B13 authority reference,
  digest, and generation, and issue/expiry times.
- Authenticated `BackendLaunchEvidenceV1`, schema
  `execution-backend-launch-evidence/v1`, SHALL bind evidence/admission IDs,
  capsule and full request digests, `job_id`, actual backend execution ID,
  profile-binding and release digests, planned/actual configuration digests,
  result schema/digest, producer/authenticity/verifier/trust/revocation data,
  complete property set and one sorted
  `(property_id, evidence_kind, ref, digest)` tuple per property, start/finish
  times, and cleanup subject/reference/digest/observation time.

Trusted code SHALL encode the complete existing `SandboxJobRequest.to_wire()`
value as RFC 8785/JCS bytes and hash those exact bytes. Before admission it
SHALL decode those bytes and recursively compare the decoded value with the
source using JSON-type strictness, safe-integer bounds, and IEEE-754 bit
identity. A value that does not round-trip losslessly—including integral or
signed-zero floats such as `1.0`, `0.0`, and `-0.0`, a non-finite number, or an
unsafe integer—SHALL be rejected rather than aliased. The canonical bytes
SHALL cover schema, `job_id`, `idempotency_key`, `owner_scope`, `capability`,
derived `actions`, `payload`, `workspace_ref`, and `credential_grant_ref` and
SHALL be the only dispatched request representation. The backend SHALL verify
the digest before decoding and SHALL execute only the value decoded from those
same bytes, never the original Python object or a separately reserialized
request. Any mutation of the accepted canonical bytes SHALL invalidate the
capsule, preflight evidence, and launch evidence even when `job_id` is
unchanged.

The exact `os_isolated` property identifiers SHALL be
`kernel_process_boundary`, `filesystem_default_deny`,
`network_default_deny`, `cpu_limit`, `memory_limit`, `process_limit`,
`wall_time_limit`, `output_limit`, `platform_secrets_absent`,
`undeclared_devices_absent`, `bounded_cleanup`, and
`request_bound_evidence`. `vm_isolated` SHALL additionally require
`guest_kernel_boundary` and `host_devices_default_deny`. Unknown or missing
properties, duplicate proof tuples, and contract-disallowed evidence kinds
SHALL deny admission or output.

The trust-root-built composition SHALL resolve the active profile binding and
owner-defined requirement facts, derive the planned configuration, create a
fresh `admission_id`, and obtain authenticated preflight evidence before
minting the final capsule. Sharing `admission_id` SHALL avoid circular digest
construction: preflight binds request/configuration facts, while the later
capsule binds that preflight digest. Preflight SHALL fail after expiry,
revocation, binding replacement, request mutation, or reuse for another
admission. Capsule expiry SHALL be no later than binding, preflight, or
authority expiry.

Dispatch SHALL independently re-verify provider/B2 authority, generation,
expiry, and revocation at the decision point. A valid capsule SHALL NOT create,
promote, extend, or replace provider/B2 authority. A caller SHALL NOT provide
or select a signing key, verifier, binding, preflight result, requirement,
authority fact, or pre-verified record.

The active profile binding SHALL fix the launch-evidence producer identity,
authenticity mechanism, key-custody class, canonical contract, verifier, and
trust set. Model-controlled code, caller data, and result payloads SHALL NOT
choose them or mark evidence verified. Each required property SHALL have
exactly one canonical proof tuple. The verifier SHALL check request, capsule,
admission, execution, configuration, result, property, freshness, replay, and
cleanup bindings before exposing output. Replay SHALL be accepted only for a
byte-identical canonical record for the same admission and result; cross-
admission reuse or changed content under an existing `evidence_id` SHALL fail.
Cleanup proof SHALL name the actual execution subject and be observed after
finish.

Preflight SHALL prove only current capability and exact planned configuration.
`RunnerCapabilities`, `isolation_enforced`, executable probes,
`EnforcementReceipt`, labels, queue/admission receipts, and the outer capsule
without valid launch evidence MAY veto or diagnose but SHALL NOT prove actual
execution. Missing or invalid actual-launch evidence SHALL raise
`ExecutionAdmissionError(reason=backend_evidence_invalid)` and SHALL NOT
produce a successful result, accepted candidate, or fallback input.

This outer contract SHALL NOT change `runner/v1`, request schema
`runner-job/v1`, result schema `runner-result/v1`, `SandboxJobRequest`,
`SandboxJobResult`, or `EnforcementReceipt`. `JobCapability` SHALL remain
exactly `source_exec`, `repo_read`, `repo_exec`, and `coding`, with its current
immutable action mapping. `inference_only` and `provider_cli` SHALL NOT become
runner capabilities. A backend without a reviewed binding and valid
request-bound evidence SHALL remain unavailable for execution admission.
Production constructors SHALL remain absent until task 7.2's external trust
distribution, purpose-separated custody, rotation/revocation, and persistent
store boundary are explicitly approved and implemented. Production SHALL NOT
fall back to test, generated, unsigned, or caller-supplied keys or evidence.

#### Scenario: pre-launch proof cannot attest a future execution

- **WHEN** a static profile binding and fresh request-bound preflight evidence
  prove every required mechanism and bind the exact planned configuration
- **THEN** pre-launch admission may establish capability and configuration
  support for that request
- **AND** it does not prove the future launch, enforcement, cleanup, or result

#### Scenario: same-job request substitution fails

- **WHEN** an attacker preserves `job_id` but mutates the schema,
  `idempotency_key`, `owner_scope`, capability/actions, payload,
  `workspace_ref`, or `credential_grant_ref`
- **THEN** the recomputed full inner-request digest differs
- **AND** the preflight record, capsule, and launch evidence all fail closed

#### Scenario: canonical numeric aliases cannot preserve a digest

- **WHEN** a caller uses `1` versus `1.0`, `0` versus `0.0` or `-0.0`, an
  unsafe integer, or another value that JCS cannot round-trip with identical
  JSON type and numeric bits
- **THEN** the non-lossless request is rejected before admission
- **AND** execution receives only the exact verified canonical bytes decoded
  after the digest check, never the original or a separately encoded object

#### Scenario: volatile readiness cannot hide in static policy

- **WHEN** a profile binding carries a current self-test result or per-request
  planned-configuration value
- **THEN** verification rejects the malformed static artifact
- **AND** only fresh admission-bound preflight evidence may carry those facts

#### Scenario: preflight replay and revocation fail closed

- **WHEN** preflight evidence is expired, revoked, from a replaced binding,
  request-mismatched, or reused for another admission
- **THEN** no execution admission capsule is minted or accepted

#### Scenario: caller cannot mint a self-consistent capsule

- **WHEN** a caller supplies a capsule, requirement, profile binding,
  preflight evidence, authority reference, signer, key, verifier, or mutually
  matching replacement digests
- **THEN** admission refuses because the outer capsule must be M1-minted from
  independently trusted state and verified against the exact request context
- **AND** no self-consistent caller substitution creates execution authority

#### Scenario: outer capsule preserves the frozen inner runner wire

- **WHEN** admitted `source_exec` work is dispatched through `SandboxRunner`
- **THEN** the sidecar records bind the complete inner request, requirement,
  profile, preflight, configuration, and authority to the unchanged inner wire
- **AND** the inner schemas remain `runner-job/v1` and `runner-result/v1`
- **AND** no admission field or new `JobCapability` is added

#### Scenario: returned evidence must prove the actual execution

- **WHEN** a backend returns output without valid launch evidence bound to the
  admitted capsule, inner `job_id`, planned configuration, actual execution,
  complete required property set, and result digest
- **THEN** admission fails with
  `ExecutionAdmissionError(reason=backend_evidence_invalid)`
- **AND** the output creates no successful runner result, accepted candidate,
  or fallback input

#### Scenario: copied or invented launch evidence fails

- **WHEN** launch evidence is copied across admissions, replayed with changed
  content, names an unbound producer or verifier, omits or duplicates a
  property proof, mismatches the result, or lacks post-finish cleanup proof
- **THEN** the reviewed verifier rejects it as `backend_evidence_invalid`

#### Scenario: admission never promotes invocation authority

- **WHEN** a capsule is valid but independent provider/B2 authority is
  missing, expired, revoked, or generation-stale at dispatch
- **THEN** execution is denied despite the valid capsule

#### Scenario: production cannot use a test evidence root

- **WHEN** approved production custody, trust distribution, or revocation state
  is unavailable
- **THEN** no profile binding, preflight evidence, capsule, or launch evidence
  is constructed through a test, generated, unsigned, or caller fallback

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
