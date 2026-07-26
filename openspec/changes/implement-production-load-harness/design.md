## Context

`harden-production-load-evidence` already owns the cross-capability evidence
semantics: scenario ownership, immutable manifests, three terminal verdicts,
substrate honesty, recomputable metrics, invariant oracles, fault timelines,
reconciliation, and same-environment baselines. Its tasks 2.1-2.5 explicitly
call for this dependent implementation change.

The landed `tests/load/operator_admission_v2.py` is useful owner-local
evidence, not a shared protocol. It runs a dedicated-machine SQLite/process
workload with synthetic actors and no provider adapter, but it does not produce
the complete common manifest, fingerprint, authorization, isolation, cleanup,
resource, or digest-tree proof. It remains an adapter candidate owned by
`operator-request-trigger-contract`.

Broad active `tests/` claims currently prevent runtime implementation. This
change is therefore target-only until those owners narrow or release their
claims. It may name the future files, but it does not reserve or edit them.

## Goals / Non-Goals

**Goals:**

- Make evidence bytes, digests, validation, recomputation, and rollups
  deterministic and independently reviewable.
- Make missing, malformed, unsafe, shaped, mock, or incomplete evidence fail
  closed without turning unavailable infrastructure into a false pass.
- Preserve capability-local ownership of workloads and release thresholds.
- Prevent secrets, private payloads, raw identities, ambient provider
  authority, and arbitrary filesystem paths from entering retained evidence.
- Make the current provider-free connector/storage baseline runnable only
  after its identity, authorization, isolation, abort, canary, and cleanup
  gates are real.

**Non-Goals:**

- Implement or claim runtime files in this planning lane.
- Choose a permanent load generator or centralize capability adapters.
- Define catalog, market, PostgreSQL, Realtime, fleet, or settlement
  thresholds.
- Run load against the public connector, create test users, reset data, invoke
  a model/provider, or spend requester/maintainer quota.
- Treat protocol conformance, mock execution, or an empty scenario selection
  as capacity evidence.
- Settle private-data custody. Each scenario names its accepted custody mode;
  shared evidence contains synthetic/pseudonymized facts only.

## Decisions

### 1. The shared package is a protocol kernel, not an umbrella workload

The future `tests/load/_protocol/` package owns closed schema decoding,
canonical bytes, digest verification, registry loading, immutable publication,
fingerprint validation, recomputation interfaces, and rollup. It exposes small
pure boundaries to capability adapters. It does not import an adapter, choose
a scenario, schedule traffic, or supply owner thresholds.

The initial implementation write set is the package, one focused conformance
test module, and `tests/load/README.md`. Owner-local harnesses adopt it later
through separately claimed changes.

The reference shape stays small:

- `schema.py` owns closed JSON shapes, enums, stable codes, and registry and
  manifest validation;
- `artifacts.py` owns RFC 8785 bytes, SHA-256, rooted artifact verification,
  and exclusive publication;
- `environment.py` accepts only explicitly injected safe facts and reports
  missing required fingerprint fields;
- `rollup.py` owns pure scenario and aggregate evaluation;
- one focused test module and protocol-only README prove the contract.

The public Python surface is limited to registry load, manifest validation and
canonical bytes, exclusive write, artifact verification, safe fingerprint
collection, and rollup evaluation. A future refactor may split modules only
when this bounded surface proves insufficient.

### 2. Canonical bytes use a closed integer-safe data model

Protocol documents use RFC 8785 JSON Canonicalization Scheme bytes through the
existing direct `rfc8785` dependency, with exact schema identifiers, ASCII
object keys and identifiers, bounded depth/member/array/scalar/byte counts,
duplicate-key rejection, and integers for counts, timestamps, durations,
sizes, and latency samples. NaN/Infinity, unknown fields, caller-selected
paths, and unbounded strings are rejected.

The manifest digest is the lowercase SHA-256 of canonical manifest bytes. The
digest is carried by the containing record/path rather than inside the
self-hashed object. Every referenced artifact has its own media type, byte
length, SHA-256, and relative logical name in the manifest.

V1 pins:

| Item | Exact value |
|---|---|
| Manifest schema | `tinyassets.production-load-evidence/v1` |
| Registry schema | `tinyassets.production-load-registry/v1` |
| Command registry | `tinyassets.production-load-command-registry/v1` |
| Argv schema | `tinyassets.production-load-argv-schema/v1` |
| Selection | `tinyassets.production-load-selection/v1` |
| Pre-traffic gate set | `tinyassets.production-load-gate-set/v1` |
| Dispatch attempt set | `tinyassets.production-load-dispatch-attempt-set/v1` |
| Dispatch ref set | `tinyassets.production-load-dispatch-ref-set/v1` |
| Bundle index | `tinyassets.production-load-bundle-index/v1` |
| Aggregate | `tinyassets.production-load-aggregate/v1` |
| Validation result | `tinyassets.production-load-validation-result/v1` |
| Safety disposition | `tinyassets.production-load-safety-disposition/v1` |
| Trust set | `tinyassets.production-load-trust-set/v1` |
| Authenticated receipt | `tinyassets.production-load-receipt/v1` |
| Blocking-code registry | `tinyassets.production-load-blockers/v1` |
| Verdict | `passed`, `failed`, `not_run` |
| Substrate | `real`, `shaped`, `mock` |
| Owner oracle | `held`, `violated`, `unevaluable` |
| Reconciliation class | `expected`, `loss`, `duplicate`, `unexplained` |
| Access class | `public`, `internal`, `restricted` |
| Custody mode | `host`, `private_universe_brain`, `vault`, `platform_held` |
| Identifier grammar | `[a-z][a-z0-9_-]{0,127}` |
| Owner blocker grammar | `owner.<capability>.<code>` with capability kebab-case and code `[a-z][a-z0-9_]{0,62}` |
| JSON document limits | 1,048,576 bytes, depth 16, 128 members/object, 10,000 items/array, 4,096 UTF-8 bytes/string |
| Registry entries | at most 10,000 |
| Manifest artifact leaves | at most 512 |
| JSONL event | at most 16,384 bytes before its final LF |
| Artifact leaf | at most 2,147,483,648 bytes |
| Bundle bytes | offline cap 1,073,741,824 bytes; live cap from authenticated authorization; absolute ceiling 8,589,934,592 bytes |
| Integer domain | JSON safe integers `[-9007199254740991, 9007199254740991]`; counts/times/durations/sizes are non-negative |

The delta spec owns the complete normative V1 record grammar: every registry,
command, bundle-index, manifest/nested record, aggregate, trust set,
authenticated receipt, event, fault timeline, and reconciliation field has an
exact type, nullability, bound, ordering, uniqueness, digest, reference, and
temporal rule. Registry history is one-way: the scenario registry pins only its
accepted predecessor; the command registry pins the scenario-registry digest;
the manifest and authorization pin both, avoiding a digest cycle.
Each scenario entry also pins one accepted custody mode and backend-policy
digest; every artifact leaf must match that mode and policy, so leaf
self-declaration cannot substitute for owner-approved custody and retention.
History-aware publication receives the prior registry before accepting a
classification change. The manifest pins its bundle index, and the index
defines exhaustive run membership without scanning unrelated global CAS
objects.

Scenario blockers and malformed-protocol errors are disjoint enums. Missing
evidence paired with its legitimate `not_run` blocker is a valid blocked
scenario; present-but-invalid evidence or missing evidence under a claimed
pass/fail returns the spec's first stable protocol error. After authenticated
traffic starts, valid authenticated evidence of residue or foreign-state
mutation is a conforming owner failure with durable lockout. Missing, malformed,
or unauthenticated cleanup/abort/lockout proof is instead nonconformant:
capacity is null and safety is `unknown_locked`. Invalid evidence is never
normalized into a trusted failure result.

Stored JSON bytes must equal their RFC 8785 re-encoding. Canonical JSONL is one
independently guarded and JCS-canonical object followed by exactly one LF; BOM,
CRLF, blank lines, missing final LF, and trailing bytes are invalid.

For sorted non-negative integer samples `x` of length `n > 0`, percentile
`p` is nearest-rank `x[ceil(p*n)-1]`; V1 computes p50, p95, and p99, and max is
`x[n-1]`. Empty samples cannot report percentiles. Golden fixtures cover
`n=1`, percentile rank boundaries, repeated values, and safe-integer limits.

Bundles publish leaves at
`artifacts/sha256/<digest[0:2]>/<digest>` and manifests at
`manifests/sha256/<digest[0:2]>/<digest>.json`. Logical names never determine a
filesystem path.

### 3. Publication is atomic, write-once, and rooted

The writer accepts one operator-selected evidence root that has already passed
the run authorization boundary. Every derived path is a library-built
relative identifier. It rejects absolute paths, `..`, alternate streams,
symlinks, junctions/reparse points, hard-link surprises, duplicate logical
names, and files that escape or change beneath the root.

Publication holds an accepted root handle, rejects linked/reparse roots and
components, uses no-follow/exclusive creation when available, and reverifies
object identity plus link count before commit. A filesystem that cannot prove
those properties cannot publish durable V1 evidence; a live run using it is
`not_run`. The manifest binds a canonical bundle index whose members equal its
exhaustive sorted artifact leaves; unrelated global CAS objects are not extras.

Raw artifacts are closed, flushed, hashed, and published before the completed
manifest. Final publication is exclusive and atomic. An existing identical
digest is idempotent; different bytes at the same address are corruption.
Corrections create a new run with `supersedes`; no finalized byte is edited.

### 4. The validator recomputes universal math and verifies owner results

Validation reloads the pinned schema and registry versions, re-canonicalizes
the manifest, verifies every reachable digest and byte count, rejects missing
or extra referenced evidence, and recomputes:

- attempted, offered, sent, admitted, rejected, timed-out, cancelled,
  committed, claimed, delivered, settled, lost, and duplicate populations
  where the owning scenario declares them;
- p50, p95, p99, and maximum latency from integer raw samples with operation,
  units, sample counts, and denominators;
- planned-send versus actual-send/receive timing needed to expose coordinated
  omission and client-side queueing; and
- scenario verdict and failure-first aggregate from typed, digest-bound owner
  result records.

Capability owners execute their predicates, threshold comparisons, fault
injection and interpretation, reconciliation semantics, and same-environment
baseline comparisons against raw evidence. They provide typed
`held|violated|unevaluable`, threshold, fault, reconciliation, and baseline
result records plus the source-evidence digests. The shared kernel verifies
shape, completeness, digests, universal algebra, and rollup; it does not
implement or reinterpret owner semantics.

Stable error codes identify the first invalid protocol condition and never
echo raw caller values or exception text.

Missing required fingerprint, denominator, fault, reconciliation, or baseline
evidence does not become a malformed document when a structurally valid
`not_run` manifest records the exact blocker. It invalidates any claimed
`passed`; evaluation yields `not_run` unless independently retained evidence
already proves a required invariant violation, in which case it yields
`failed`.

### 5. Environment and generator limits are evidence

The fingerprint binds exact source SHA, clean/dirty state and diff digest,
image/rollout/config identity, protocol and scenario versions, operator,
command/arguments, seed, clocks and synchronization evidence, topology,
region, database/pool/queue/Realtime/network facts, participant resources,
and substrate class. A dirty run is not automatically invalid, but cannot
claim equivalence unless the owner predeclared and the manifest binds the diff.

Commands are retained as an argv array, never an interpolated shell string.
Repository paths are repo-relative; accepted evidence/output roots use stable
logical IDs plus configuration digests rather than absolute host paths.
Secret-bearing arguments are structurally forbidden, not redacted after
capture.

Owner adapters record arrival model, warm-up/ramp/steady/cool-down phases,
offered and achieved throughput, generator queue delay, retry/backoff, payload
size class, connections/streams, hot-key mix, client topology, and timestamped
CPU, memory, swap, handles/files, threads/processes, sockets, database
connections/locks/pool wait, queue/outbox depth, disk, network, and runtime
pause measurements. A saturated or clock-unsynchronized generator cannot prove
the platform's capacity.

V1 locates the mandatory minimum in one closed generator-health record with
fixed integer units: offered/achieved operations, queue delay ns, CPU ppm,
memory bytes, network bytes, socket/connection counts, dropped events, clock
skew, sampling facts, and raw evidence digests. Owner rules still decide
saturation thresholds.

Raw operation events distinguish one logical operation from its contiguous
retry attempts. Offered/achieved are logical-operation counts; attempted/sent
and downstream load are per-attempt counts. Per-attempt pseudonyms, indexes,
backoff, and planned/actual timing make retry amplification recomputable.

Every result-defining leaf binds producer identity class or pseudonym,
implementation name/version/digest, source class, sequence/time basis, and
source-attestation digest. A production pass requires accepted independent
capture sources, including a service-side receipt/log for cross-checkable
counts. One producer's internally consistent request, response, and summary
records remain shaped or `not_run`.

### 6. Privacy and authority fail closed

The protocol schema has no prompt, page body, email, raw account/user/universe
identifier, bearer, cookie, refresh token, grant set, credential, provider home,
local-model endpoint, or arbitrary environment field. Durable correlation IDs
are deployment-scoped pseudonyms produced outside the protocol package under
an accepted PRF scheme/version/domain and key-fingerprint contract; a plain
hash is not accepted. Counts, hashes, and small distributions are
access-classified and sensitive low-cardinality values are suppressed,
bucketed, or confined to an enforced restricted backend. An access label is
valid only when its backend policy/version, retention expiry, export/delete
behavior, and access-control proof are digest-bound.

Commands use registered IDs and versions with closed argv schemas. Arbitrary
positional/query values and shell fragments are rejected. Dirty source identity
covers the effective executed tree, including relevant untracked/generated
code, without retaining diff content.

V1 result-defining raw evidence is restricted to canonical JSON documents and
closed-schema JSONL events that the validator can inspect. An opaque diagnostic
artifact may be content-addressed, but it cannot satisfy a required privacy or
recomputation gate until its media type has a separately accepted versioned
scanner. Generic forbidden-key checks are defense in depth, not a claim that
arbitrary semantic secrets can be detected.

Capability adoption changes—not the shared kernel—own sanitized child
environments, dispatch tripwire execution, egress constraints, and non-secret
provider-attempt evidence. The protocol validates their typed, digest-bound
isolation and tripwire receipts and fails conformance when required receipts
are absent or contradictory. Host authorization selects `provider_free`,
requester BYOC, or accepted-market authority. The latter modes bind the exact
non-maintainer authority digest; every mode binds a maintainer-authority
exclusion digest. Provider-attempt receipts cover the whole traffic/drain
interval and distinguish authorized, unauthorized, and maintainer-authority
attempt counts without retaining provider credentials or raw user identity.

### 7. Live authorization abort and cleanup receipts are typed dependencies

A live authorization record shape binds the run ID, exact environment identity
and URL, time window, maximum request/concurrency/connection/data envelope,
provider-authority mode and digest, maintainer-authority exclusion, test
identities, allowed endpoints, scenario versions, operator, abort thresholds,
and canary coordination. Isolation, abort, canary, tripwire, and cleanup
records are immutable and digest-bound to that authorization.

Every receipt is an authenticated envelope over canonical payload bytes and
binds an accepted versioned trust set, trust domain, issuer/key, algorithm,
payload digest, and authenticator. Revocation is explicit input. Capture
independence means distinct accepted trust domains, not different producer
labels. The owner enforces one-time authorization and emits an authenticated
nonce-consumption or append-only-ledger witness; the offline kernel verifies
that witness and never infers replay safety from a nonce string.

A distinct operator-domain opt-in receipt proves the local second opt-in.
Traffic start binds a canonical pre-traffic gate set containing authorization,
nonce, opt-in, isolation, network identity, and canary-start refs. Sorted
dispatch receipts reconcile exactly to sent attempt events. Authenticated
traffic stop closes the interval only after every dispatch has released its
resources; provider-attempt and canary receipts must cover from no later than
start through no earlier than that stop, so monitoring cannot end while
connections or requests still drain. Every dispatch starts before
authorization expiry, its half-open send interval ends no later than expiry,
and every actual send is strictly before expiry. Starting a receipt before
expiry never authorizes post-expiry work. A pre-run zero-attempt receipt cannot
prove run-wide quota isolation.

Dispatch attempt/ref sets make multi-generator closure deterministic, including
a valid empty set after immediate stop. Run-wide request/data sums and
overlapping rate/concurrency/connection intervals are checked against the
authorization envelope. Each receipt's maximum in-flight overshoot is treated
as active for its whole drain interval and overlapping overshoot maxima are
summed against the one run-wide allowance, so splitting load across receipts
cannot evade any cap.

The shared kernel validates those records and their required relationships. It
does not resolve endpoints, start or stop traffic, perform cleanup, or enforce
a lockout. A separately accepted `live-mcp-connector-surface` adoption change
owns those actions and depends on scoped reset, two ordinary real test
subjects, the private alias roster, fingerprint key, host-approved environment
and envelope, and a provider-free path.

The phase matrix is closed: a missing or stale gate before traffic is
`not_run`; malformed or tampered evidence is protocol-invalid rather than a
capacity verdict; and unauthorized or maintainer-authority provider attempt,
tenant bleed, envelope breach, abort crossing, foreign mutation, residue,
required reconciliation loss,
canary-monitor loss, or generator-control loss after traffic starts is
`failed`. Saturation, unachieved offered load, or clock loss is `not_run`
unless independent evidence already proves a required server invariant
violation. Owner dispatch receipts bind pre-dispatch envelope enforcement,
maximum in-flight overshoot, and drain behavior; the shared package only
validates them.

Once an authenticated traffic-start receipt exists, missing or invalid stop,
coverage, cleanup, required abort, or required durable-lockout proof makes the
bundle invalid, nulls its capacity verdict, and returns a separate
`unknown_locked` safety disposition. Authenticated violation/residue evidence
returns `failed_locked`.
Safety disposition never participates in capacity aggregation. Lockout
transitions are monotonic and authenticated; clear requires a later sequence
bound to the current lock, a recovery receipt, zero-residue proof, and
foreign-state stability.

### 8. Protocol green and capacity green remain separate

Offline conformance can pass before a real substrate exists. Every required
unavailable production scenario emits `not_run` with versioned blocking codes.
Mock or shaped runs can reveal a real failure but cannot pass a production
scenario. Aggregates retain all constituent digests and substrate classes.

## Risks / Trade-offs

- **[Schema becomes a second domain model]** → Keep adapter data opaque behind
  named references; centralize evidence shape only.
- **[Canonicalization is underspecified]** → Use closed JSON, integer units,
  exact limits, duplicate rejection, and golden bytes/digests.
- **[Evidence can be rewritten or path-swapped]** → Root all paths, reject
  link/reparse traversal, publish exclusively, and reverify the full digest
  tree.
- **[Summaries hide failures]** → Recompute raw populations and latency,
  preserve unsuccessful operations, and reject success-only denominators.
- **[The generator is the bottleneck]** → Record offered/achieved load,
  client queueing, resources, clocks, and multi-generator loss.
- **[Tests spend founder/provider quota]** → Sanitize environments, bind
  provider-free/requester-BYOC/accepted-market authority explicitly, constrain
  egress, and abort on any unauthorized or maintainer-authority attempt.
- **[Cleanup becomes broad deletion]** → Depend on scoped reset's closed-world
  plan and fail on foreign/shared/obligated state or residue.
- **[Conformance is marketed as capacity]** → Keep independent verdicts and
  make missing real scenarios `not_run`.

## Migration Plan

1. Obtain strict and independent review of this target-only dependent change.
2. After broad `tests/` claims release or narrow, expand STATUS Files and
   implement the protocol kernel plus offline conformance tests.
3. Adapt owner-local harnesses only through their own claimed changes.
4. File a separately accepted `live-mcp-connector-surface` adoption change for
   the provider-free current connector/storage baseline after identity/reset
   and host environment authorization land.
5. Owner changes emit `not_run` packets for unavailable real substrates and
   provider-invoking paths and eventually provide one approved real adapter
   packet.
6. In one landing lane after both changes and real owner-adapter evidence are
   complete, archive/sync `harden-production-load-evidence` first to create the
   canonical capability, strict-validate, then archive/sync
   `implement-production-load-harness` to add implementation requirements and
   strict-validate the canonical capability and all OpenSpec again. Neither
   change may archive alone.

Before an owner adopts it, rollback is deletion of unused protocol code.
Finalized evidence remains immutable. Owner adoption changes define abort,
cleanup, and durable lockout execution; this shared kernel validates their
records only.

## Open Questions

- What exact artifact retention window and custody mode will the host approve
  for synthetic raw events and environment/resource traces?
- Which source-control dirty-state policy is acceptable for local
  conformance versus production-equivalent capacity claims?
- Does the future first baseline retain the historical 2,000-session research
  target, or will the host approve a different connector envelope?
- Which current broad `tests/` owners can narrow their Files cells first so the
  shared package becomes claimable without collision?
