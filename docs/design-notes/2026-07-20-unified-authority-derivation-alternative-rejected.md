> **Status: ALTERNATIVE — NOT ADOPTED.** This is the total-unification design
> (one `Authority[T]` constructor spanning every surface), authored as the
> Codex-family half of a cross-family design pair. The host did **not** select
> it: forcing WorkOS identity, content hashes, and ledger settlement through one
> platform-signing constructor was judged a false unification — it would make the
> platform re-sign facts an external root or a hash already proves, and would
> require a migration that infers identity from adjacent tables. The adopted
> design is
> [`2026-07-20-unified-authority-derivation-approved.md`](2026-07-20-unified-authority-derivation-approved.md).
>
> Kept because its threat analysis and surface inventory are the rationale for
> the three-mechanism split, and a future reader should be able to check why the
> simpler-sounding option was rejected. Do not build from this document.

# Unified Authority Derivation Design

Evidence basis: read-only static inspection of `feat/patch-loop-leasestore-fix2` on 2026-07-20. Runtime activation, production reachability, and S5 filesystem-tamper exposure are marked **UNVERIFIED** where repository evidence does not prove them.

## 1. Principle

An authority decision may accept, execute, settle, merge, enroll, or complete only from an in-memory `Authority[T]` produced either by cryptographically verifying immutable signed bytes against a release-pinned trust root and exact expected bindings, or by freshly re-executing a registered authoritative platform probe; database rows, events, projections, caches, request fields, and receipts may only reject, narrow, rate-limit, deduplicate, or record the decision. The invariant is testable in both directions: preserving every mutable row while deleting the signed artifact or blocking the platform probe must make acceptance impossible; preserving the artifact/probe while widening any mutable copy must leave the accepted scope unchanged or cause rejection.

CAS determines which valid transition wins; CAS or terminal row state does not itself prove that the transition was authorized. Durable replay requires a signed terminal attestation.

## 2. Signed-artifact taxonomy

### Common envelope

New TinyAssets-issued artifacts use the existing RFC 8785/JCS → SHA-256 → domain-separated Ed25519 pattern already implemented in [execution_capsule.py:590](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/runtime/execution_capsule.py:590) and [execution_capsule.py:609](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/runtime/execution_capsule.py:609):

```python
class SignedEnvelopeV1(TypedDict):
    payload: dict[str, object]
    integrity: {
        "canonicalization": Literal["RFC8785-JCS"]
        "hash_algorithm": Literal["sha256"]
        "payload_sha256": str
        "signature_algorithm": Literal["ed25519"]
        "key_purpose": str
        "key_id": str
        "signature_b64": str
    }
```

Every artifact has its own domain separator, schema version, key purpose, exact-field validation, binding validator, and time policy. Trust-root activation and revocation come from a deploy-published, root-signed manifest—not a database `active` column. Private signing keys remain outside application databases and are purpose-separated so one compromised signer does not authorize every domain.

| Surface | Authoritative artifact | Signer and authoritative moment |
|---|---|---|
| **S2 execution** | Existing `ExecutionCapsuleV1`; existing `LeaseGrantV2`; existing device-signed `ExecutionResultV1`; new `CompletionAttestationV1`. | Capsule: platform capsule key when exact job, daemon, source, lease/fence, image, and policy are finalized. Grant: lease-grant key inside the winning lease CAS after verifying the capsule and S3 principal. Result: enrolled device key after execution. Completion: completion key immediately before the winning completion CAS, persisted atomically with that CAS. The first three cryptographic formats already exist at [execution_capsule.py:1072](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/runtime/execution_capsule.py:1072), [lease_store.py:1612](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/runtime/lease_store.py:1612), and [execution_result.py:509](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/runtime/execution_result.py:509). |
| **S3 WorkOS user identity** | `WorkOSIdentityAuthority`: an ephemeral authority derived directly from the verified WorkOS JWT; do not re-sign it. | WorkOS signs the JWT with its RS256 key. TinyAssets verifies issuer, `kid`, signature, expiration, audience, subject, and permissions through JWKS on each request. This verification exists today, but its return type loses provenance by returning a plain `Identity` at [workos_provider.py:125](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/auth/workos_provider.py:125). |
| **S3 daemon enrollment** | `OwnerEnrollmentApprovalV1` followed by `DeviceEnrollmentAttestationV1`. | Identity-attestation key signs owner approval when a verified WorkOS identity approves the exact enrollment, installation, device public keys, and key thumbprint. After device proof succeeds, the same purpose-separated issuer signs the final daemon ID, owner, key bytes, thumbprint, epoch, scopes, and validity. Today completion instead promotes mutable enrollment columns into `enrolled_daemons` at [daemon_enrollment.py:545](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/api/daemon_enrollment.py:545) and [daemon_enrollment.py:592](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/api/daemon_enrollment.py:592). |
| **S3 challenges/tokens/requests** | `DaemonChallengeV1`, `DaemonAccessAttestationV1`, and ephemeral `DeviceRequestAuthority`. | Token key signs a bounded challenge when created. After challenge and device-signature verification, it signs a ≤5-minute access attestation containing daemon, owner, device-key ID, epoch, scopes, audience, `jti`, issue and expiry times. Each request still carries the device signature over method/path/query/headers/body hash/timestamp/nonce. Challenge/token/nonce rows are replay, rate-limit, and revocation vetoes only. Today an opaque token becomes authoritative through an inserted token row at [daemon_enrollment.py:747](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/api/daemon_enrollment.py:747), [daemon_enrollment.py:850](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/api/daemon_enrollment.py:850), and [daemon_enrollment.py:872](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/api/daemon_enrollment.py:872). |
| **S4 B2 API** | No new independent artifact. It composes `Authority[DeviceEnrollmentAttestation]`, `Authority[ExecutionCapsule]`, `Authority[LeaseGrant]`, and `Authority[ExecutionResult]`. | S4 may select/poll using mutable state, but only a verified S3 principal plus verified capsule may cause `LeaseGrantIssuer` to sign a lease. Request fields can narrow those bindings. S4 currently accepts a plain `AuthenticatedLeasePrincipal` at [execution_jobs.py:64](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/api/execution_jobs.py:64). |
| **GitHub review/merge** | `GitHubApprovalAttestationV1` plus fresh `GitHubPullAuthority`. | Review-attestation key signs only after a registered GitHub probe observes an `APPROVED` review by the connected owner at the exact repository, PR, and head SHA. Immediately before merge, GitHub is re-read for current head, review, author type, merge state, and rules. The attestation makes queued work durable; it never replaces the final GitHub re-execution. The live worker already re-executes GitHub at [runs.py:3940](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/runs.py:3940) and [runs.py:4017](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/runs.py:4017), but no durable signed approval artifact exists. |
| **Market claim/ownership** | `ClaimOwnershipAttestationV1`. | Market-claim key signs within the winning claim/escrow CAS after verified actor identity and payment/escrow prerequisites. Bind claim ID, goal/gate/rung, claimant, immutable staker, amount/currency, escrow reference, version/fence, settlement-policy hash, issue time, and expiry where applicable. Today positive ownership comes from `claimed_by`/`bonus_staker_id` rows at [market.py:3485](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/api/market.py:3485). |
| **Market settlement** | `SettlementAttestationV1`. | Settlement key signs after combining verified claim ownership, verified result/outcome, current claim fence, and actual ledger/payment execution. Bind payee, amount, currency, claim artifact digest, outcome artifact digest, transfer ID, and settlement time. Today release selects the staker from mutable fields at [market.py:3635](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/api/market.py:3635). |
| **S5 blob authority** | `BlobReferenceAttestationV1`. | Blob-reference key signs when `mark_referenced` successfully binds blob ref, digest, size, owner, daemon, job, lease, fence, confidentiality/storage class, committed time, and `referenced_at`. Platform-hosted blobs are re-hashed first. Owner-controlled blobs require verified device possession proof without fetching private plaintext. The JSON binding is currently read as authority at [blob_refs.py:554](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/runtime/blob_refs.py:554), while `referenced_at` is a mutable update at [blob_refs.py:599](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/runtime/blob_refs.py:599). Filesystem-tamper exposure remains **UNVERIFIED**. |
| **Adjacent source approval** | `SourceApprovalAttestationV1`. | Source-approval key signs after a verified host/owner approves the exact node/version, source hash, sandbox-policy hash, capability class, and expiry/revocation epoch. Hash equality alone proves equality, not approval; the current runtime gate trusts `approved` plus `approved_source_hash` at [graph_compiler.py:1467](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/graph_compiler.py:1467). |
| **Adjacent completed-run consumers** | `RunOutcomeAttestationV1`. | Run-completion key signs the run ID, branch/version, final status, output digest, evaluator/evidence digests, completion time, and execution authority chain when terminal completion wins. Gate claims and canonical ranking consume these attestations, not `runs.status`. Current counting reads unsigned completed rows at [quality_leaderboard.py:501](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/api/quality_leaderboard.py:501) and [quality_leaderboard.py:511](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/api/quality_leaderboard.py:511). |

A signer must never “sign whatever is in the row” during a read or migration. That launders mutable state into authority. Signing is allowed only at the authoritative moment above, after verified prerequisites or a registered platform probe.

## 3. Shared enforcement primitive

### Module home

Create `tinyassets/authority/` and add it to PLAN’s Brain/authority substrate. `tinyassets/auth/` remains HTTP authentication; generalized authority does not belong there.

```text
tinyassets/authority/
  __init__.py          # exported contracts only
  core.py              # sealed Authority[T], require/narrow/combine
  artifacts.py         # SignedEnvelopeV1 and ArtifactSpec
  ed25519.py           # extracted JCS/SHA-256/PyNaCl helpers
  trust_roots.py       # release-pinned key-purpose manifest
  platform_probe.py    # registered, ephemeral re-execution adapters
  boundaries.toml      # authority-sink and effect-call registry
scripts/check_authority_boundaries.py
tests/test_authority_core.py
tests/test_authority_boundaries.py
```

The existing JCS and PyNaCl helpers move from `execution_capsule.py` into `authority/ed25519.py`; temporary re-exports preserve internal imports during migration. No new crypto dependency is needed.

### Concrete API

```python
T = TypeVar("T")
U = TypeVar("U")

@dataclass(frozen=True)
class AuthorityEvidence:
    source: Literal["signed_artifact", "external_signature", "platform_reexecution"]
    artifact_kind: str
    subject_digest: str
    binding_digest: str
    verified_at: datetime
    expires_at: datetime | None
    key_purpose: str | None
    key_id: str | None
    trust_manifest_version: str | None
    platform_adapter_id: str | None
    evidence_chain: tuple["AuthorityEvidence", ...] = ()

class Authority(Generic[T]):
    __slots__ = ("__payload", "__evidence", "__seal")

    # Requires a module-private identity seal. No public constructor,
    # deserializer, pickle support, from_dict, copy-with, or replace method.

@dataclass(frozen=True)
class ExpectedBindings:
    values: Mapping[str, JsonScalar]

def verify_signed(
    raw: bytes,
    *,
    spec: ArtifactSpec[T],
    trust_roots: TrustRootSet,
    expected: ExpectedBindings,
    now: datetime,
) -> Authority[T]: ...

def verify_external_signature(
    raw: str | bytes,
    *,
    verifier: ExternalSignatureVerifier[T],  # WorkOS/JWKS
    expected: ExpectedBindings,
    now: datetime,
) -> Authority[T]: ...

def reexecute_platform(
    probe: RegisteredPlatformProbe[T],       # e.g. GitHub only
    *,
    expected: ExpectedBindings,
    now: datetime,
) -> Authority[T]: ...

def require_authority(
    authority: Authority[T],
    *,
    artifact_kind: str,
    expected: ExpectedBindings,
    now: datetime,
) -> T: ...

def narrow_or_reject(
    authority: Authority[T],
    *,
    reject: bool,
    reason: str,
) -> Authority[T]:
    # Returns the exact same object or raises; cannot alter/widen payload.
    ...

def combine_authority(
    *parts: Authority[object],
    spec: CompositionSpec[U],
    now: datetime,
) -> Authority[U]:
    # All prerequisites required; bindings must agree; scope is intersection.
    ...
```

Only `verify_signed`, `verify_external_signature`, `reexecute_platform`, and `combine_authority` can mint the private seal. `combine_authority` retains the full evidence chain and may only intersect scopes or deterministically derive values from already-authoritative inputs.

`reexecute_platform` does not accept an arbitrary callback. Adapters are statically registered and reviewed; they may query a PLAN-designated authoritative external platform or deterministically recompute from `Authority` inputs and release-pinned code. They may not read a local row to manufacture a positive fact. Re-execution authorities are short-lived and non-serializable.

Persist the signed envelope, never `Authority[T]`. Every load re-verifies signature, key purpose, trust-manifest version, exact schema, time, and expected bindings.

### Authority sinks

Irreversible or security-sensitive functions become explicit sinks:

```python
@authority_sink(
    decision="github.merge",
    requires=("github.approval.v1", "github.pull-current.v1"),
)
def execute_github_merge(
    approval: Authority[GitHubApproval],
    current_pull: Authority[GitHubPull],
    *,
    vetoes: VetoSet,
) -> MergeReceipt: ...
```

The decorator performs runtime type/kind/freshness/binding checks before the function body. Similar sinks cover:

- lease issue and completion;
- daemon enrollment, token issuance, and authenticated requests;
- blob reference acceptance;
- source execution;
- gate-claim creation;
- staking, refund, and settlement;
- canonical replacement;
- GitHub review, auto-merge, and manual merge.

Mutable state reaches a sink only as a `VetoSet`. It cannot contribute owner IDs, head SHAs, result IDs, policy selectors, payees, or accepted status.

### Structural test/lint gate

`scripts/check_authority_boundaries.py` is a required CI lint, also invoked from `tests/test_authority_boundaries.py` so normal pytest cannot omit it. It fails when:

1. `_mint_authority`, the private seal, or internal constructor is imported outside `authority/core.py`.
2. An `@authority_sink` lacks the declared `Authority[...]` parameters.
3. A sink imports SQLite/storage/event/projection modules, calls `.execute()`, or indexes known mutable authority fields such as `status`, `approved`, `claimed_by`, `bonus_staker_id`, `workflow_outcome`, `head_sha`, `accepted_result_id`, or `referenced_at`.
4. A registered irreversible effect—GitHub merge/review, payment/settlement, token issue, source execution, or terminal CAS—is called outside its declared authority sink.
5. `Authority` is serialized, pickled, reconstructed from a dict, or copied with replaced payload/evidence.
6. A new ignore lacks an owner, reason, and expiry and is not in the checked allowlist.

Runtime tests must also reject a duck-typed fake, raw dict, SQLite row, copied object, wrong artifact kind, wrong key purpose, wrong domain separator, stale artifact, mismatched binding, revoked trust key, or stale platform probe.

### Provenance probe on the primitive

Every verifier or issuer must answer:

- What exact immutable bytes are signed or re-executed?
- Who controls the signing/probe authority?
- Where is its trust root pinned?
- At what authoritative moment is the artifact created?
- Which subject, generation, scope, content digest, policy and expiry are bound?
- Can any caller, row, cache or event substitute one of those fields?
- Can the same artifact authorize another domain because a key/domain separator was reused?

The current S2 issuer does not yet completely pass this probe: its capsule verification key is injected through a protocol object, while no production composition root pins that input to a platform trust root ([PLAN.md:128](/C:/Users/Jonathan/Projects/wf-s2-fix2/PLAN.md:128), [lease_store.py:1612](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/runtime/lease_store.py:1612)). `TrustRootSet.resolve("execution-capsule", key_id)` must replace that injected `active` record before S4 wiring.

### Reset-by-multiplicity on the primitive

Each decision gets these mandatory adversarial tests:

- Keep all rows/events/projections/receipts; remove or corrupt every signed envelope: deny.
- Keep all rows; block the registered platform API: a re-execution-only decision denies or remains pending.
- Keep the signed envelope; widen owner, scope, head, result, payee, status or policy columns: unchanged authority or reject.
- Insert convincing duplicate events/rows with no signature: audit/DoS only.
- Reset all database projections but keep the signed artifact: re-derive the same authority.
- Serialize and reload the signed envelope: re-verification is mandatory.
- Combine two valid authorities with conflicting owner/generation/head: reject, never union.
- Rotate keys while requests are concurrent: old artifacts follow the signed trust-manifest overlap window; retired keys cannot be revived by DB mutation.

This leaves exactly two positive reconstruction paths: signature verification and registered re-execution. Every other copy is disposable.

## 4. Per-surface application map

| Surface | Current read | Replacement |
|---|---|---|
| **S2 grant** | `_verified_lease_grant()` verifies a signature but returns an unbranded `dict` at [lease_store.py:574](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/runtime/lease_store.py:574). | Return `Authority[LeaseGrantV2]`; consumers obtain fields only through `require_authority`. |
| **S2 candidate** | `_verify_stored_candidate()` re-verifies the device result but returns a `dict` at [lease_store.py:802](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/runtime/lease_store.py:802). | Return `Authority[ExecutionResultV1]`, bound to the `Authority[LeaseGrantV2]`. |
| **S2 completion** | Current fix‑9 re-verifies the candidate, revalidates blobs, derives the result ID, and uses fenced CAS; inserted events are audit-only ([lease_store.py:1471](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/runtime/lease_store.py:1471), [lease_store.py:1538](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/runtime/lease_store.py:1538), [lease_store.py:1551](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/runtime/lease_store.py:1551)). Terminal replay currently rejects rather than trusts the row. | `complete_result(grant, result, blob_authorities, request_vetoes)` accepts only composed authorities. Persist `CompletionAttestationV1` in the winning CAS; replay verifies that attestation. Row status remains reject-only. |
| **S3 WorkOS** | JWT verification produces a plain `Identity`, losing the fact that it came from verified WorkOS claims ([workos_provider.py:125](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/auth/workos_provider.py:125)). | `resolve_token_authority() -> Authority[Identity]`; middleware and all authority sinks require it. Public response shapes remain unchanged. |
| **S3 enrollment** | `status`, `owner_user_id`, device keys and thumbprint are read from `daemon_enrollments`, then copied into `enrolled_daemons` ([daemon_enrollment.py:154](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/api/daemon_enrollment.py:154), [daemon_enrollment.py:545](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/api/daemon_enrollment.py:545)). | Complete enrollment only from `Authority[OwnerEnrollmentApproval]` plus verified device proof; emit `DeviceEnrollmentAttestationV1`. |
| **S3 token/request** | Token existence and identity come from a `daemon_access_tokens` join; device resolution trusts stored key bytes, epoch and revocation ([daemon_enrollment.py:872](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/api/daemon_enrollment.py:872), [daemon_enrollment.py:893](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/api/daemon_enrollment.py:893)). | Verify `DaemonAccessAttestationV1`, then verify the request signature using the key inside the signed enrollment attestation. Rows supply only replay/rate/revocation vetoes. |
| **S4 claim/heartbeat** | `grant_job_lease()` accepts a plain protocol principal and raw capsule binder at [execution_jobs.py:64](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/api/execution_jobs.py:64). Production route wiring is **UNVERIFIED**; the static audit found only test call sites ([systemic audit:20](/C:/Users/Jonathan/Projects/TinyAssets/output/s2-gate/codex-systemic-event-authority-audit.md:20)). | Require `Authority[DeviceRequest]` and `Authority[ExecutionCapsule]`; issue `Authority[LeaseGrant]`. Heartbeat may only narrow the signed generation and requires the grant issuer to sign the new expiry. |
| **S5 blob** | `validate_reference()` trusts a mutable JSON binding’s committed state, ownership and size; platform objects are rehashed, but owner-controlled objects are not ([blob_refs.py:554](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/runtime/blob_refs.py:554)). | `verify_blob_reference() -> Authority[BlobReferenceBinding]`; completion requires this authority for every signed result reference. `failed_at`/retention rows are vetoes. S5 filesystem threat remains **UNVERIFIED**. |
| **GitHub queue** | The chat merge action checks projection `workflow_outcome` and `head_sha`, then inserts a manual-merge outbox row ([review_queue_actions.py:608](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/api/review_queue_actions.py:608), [review_queue_actions.py:618](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/api/review_queue_actions.py:618), [review_queue_actions.py:629](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/api/review_queue_actions.py:629)). | Queue an attestation digest only after verifying `GitHubApprovalAttestationV1`; projection mismatches may reject but cannot authorize enqueue. |
| **GitHub worker** | The actual worker already re-reads GitHub and requires an effective connected-owner approval at the exact head before merge ([runs.py:3940](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/runs.py:3940), [runs.py:3977](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/runs.py:3977)). Thus row forgery can enqueue/DoS, but DML-only merge remains **UNVERIFIED**, not established. | Replace `_owner_approval_confirmed() -> bool` with `reexecute_platform(GitHubApprovalProbe) -> Authority[GitHubApproval]`; merge requires it plus a fresh `Authority[GitHubPull]`. Preserve the final GitHub merge call’s expected SHA. |
| **Market run→claim** | `claim_from_branch_run` accepts `run.status == completed` and takes the rung recommendation from the row output at [market.py:2994](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/api/market.py:2994) and [market.py:3099](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/api/market.py:3099). | Require `Authority[RunOutcomeAttestation]`; derive rung/evidence only from its signed output digest and verified artifact. |
| **Market stake/settle** | Stake ownership uses `claim.claimed_by`; settlement uses `bonus_staker_id` with legacy fallback to `claimed_by` ([market.py:3485](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/api/market.py:3485), [market.py:3635](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/api/market.py:3635)). | Require `Authority[ClaimOwnershipAttestation]`; settlement combines it with verified actor, outcome, current fence and payment execution. Remove the `claimed_by` fallback after migration. |
| **Source approval** | Runtime checks an unsigned boolean and matching source hash at [graph_compiler.py:1467](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/graph_compiler.py:1467). | Require `Authority[SourceApprovalAttestation]`; source hash equality remains a binding check, not proof of approval. |
| **Canonical dispatch** | Leaderboard security thresholds count unsigned completed-run rows at [quality_leaderboard.py:511](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/api/quality_leaderboard.py:511). | Aggregate verified `RunOutcomeAttestationV1` artifacts; incomplete/missing attestations reduce counts only. Canonical replacement becomes an authority sink. |

## 5. LIVE vs unwired staging and uptime

| Surface | Classification | No-outage rollout | Host go/no-go |
|---|---|---|---|
| **S2** | **Unwired substrate.** Fix‑9 is the reference implementation and currently host-action pending ([STATUS.md:32](/C:/Users/Jonathan/Projects/wf-s2-fix2/STATUS.md:32)). | Convert internal dict verifiers to `Authority[T]`, add signed completion replay, and run the entire prior-forge matrix before any route is mounted. No compatibility path that trusts terminal rows/events. | Approval of PLAN change and capsule/grant/completion trust roots. No live flip yet. |
| **S4** | **Unwired substrate; production wiring UNVERIFIED.** | Rebuild its public adapter around S3/S2 authorities before mounting. Direct cutover is safe because there is no proven live consumer to preserve. | Go/no-go before first route mount and before pinning capsule trust roots in production. |
| **S5** | **Unwired substrate; filesystem threat outside DB-DML is UNVERIFIED.** | Add signed blob bindings before S4/S5 activation. Platform blobs may use fresh rehash; owner-private blobs require signed possession evidence. | Blob-key custody, owner-private proof policy, and first live activation. |
| **S3 WorkOS** | **LIVE by host classification.** The deploy workflow conditionally enables the WorkOS resource-server mode and audience binding at [deploy-prod.yml:450](/C:/Users/Jonathan/Projects/wf-s2-fix2/.github/workflows/deploy-prod.yml:450). | Additive shadow: one successful JWT decode emits both legacy `Identity` and `Authority[Identity]`; compare authorization decisions and expose mismatches. Then switch internal sinks—not OAuth endpoints or response shapes—to require authority. Missing authority fails writes closed while public reads remain up. Rollback may use the existing JWT verifier because it is already signature-derived. | Before shadow deploy and again before `AUTHORITY_WORKOS_ENFORCE=1`. |
| **S3 daemon enrollment/token** | Route activation is **UNVERIFIED** in this worktree, but it shares the live S3 boundary. | Replace the row-authoritative token design before route activation; do not dual-run legacy bearer-row authorization in production. | Before route activation and token-signing key provisioning. |
| **GitHub review/merge** | **LIVE/uptime-sensitive.** The design records a live recovery caller at [S4 GitHub design:158](/C:/Users/Jonathan/Projects/wf-s2-fix2/docs/design-notes/2026-07-16-s4-github-native-redirect.md:158), and the worker re-executes GitHub today. | Dual-write approval attestations after confirmed GitHub reviews while the existing GitHub re-execution remains authoritative. Shadow-verify queued attestations. Enforce both attestation and fresh GitHub probe. If the signer or GitHub is unavailable, leave the outbox pending; authoring/browsing stays available. Safe rollback is to the current GitHub re-execution—not to local projection authority. | Before signer deployment, dual-write, and enforcement flip. |
| **Market** | **Treat as LIVE/uptime-sensitive per host directive.** Repository activation is **UNVERIFIED** because `TINYASSETS_PAID_MARKET` defaults off at [node_bid.py:38](/C:/Users/Jonathan/Projects/wf-s2-fix2/tinyassets/producers/node_bid.py:38). | Dual-write attestations for every new claim/stake/settlement, shadow compare, then reconcile every open legacy position. Do not bulk-sign current rows. Each legacy position must be drained, re-consented by a verified owner, or reconstructed from an authoritative external payment probe. After enforcement there is no unattested fallback: signer outage leaves money pending, while reads and non-money control-plane surfaces remain up. | Required for legacy-position policy, any temporary settlement freeze, signing keys, payment reconciliation, and enforcement. |

### Common-mode uptime controls

- Authority verification uses local public keys and requires no signing service or KMS call.
- Signer failure is isolated per key purpose and surface. It never crashes the MCP server; the affected write/merge/settlement stays pending with a structured caveat.
- No global private authority key. Capsule, grant, completion, identity/token, GitHub, market, blob, run, and source-approval keys are purpose-separated.
- Enforcement flags live in release/deploy configuration, not mutable database rows.
- Post-cutover rollback cannot re-enable row authority. GitHub and WorkOS can fall back to their already-compliant platform/signature verification; market/S2/S5 must freeze the affected write.
- `get_status` exposes trust-manifest version, verify readiness, signer readiness, mismatch counts and oldest pending authority action without exposing secrets.
- Required load evidence: concurrent key rotation; signer outage/recovery; 1,000 S4 pollers; same-claim market settlement contention; GitHub outbox replay; and completion CAS with duplicate/forged rows. Exactly one signed terminal effect may win.

## 6. Dependency-ordered slice plan

| Slice | Deliverable and acceptance | Host approval |
|---|---|---|
| **0. PLAN/ADR and threat contract** | Add `tinyassets/authority/` to Brain/module shape; record the principle, positive-source rule, platform-probe registry, key hierarchy, reset tests, and rollback constraints. | **Required:** PLAN-level architecture. |
| **1. Authority core** | Implement sealed `Authority[T]`, envelope specs, extracted PyNaCl helpers, signed trust-root manifest, registered probe interface, runtime sink decorator, AST lint and primitive tests. No consumer behavior changes. | Key hierarchy, trust-manifest bootstrap, private-key custody. |
| **2. S2 reference migration** | Convert capsule/grant/result verification to authorities; pin capsule trust root; add atomic `CompletionAttestationV1`; retain event audit-only and row reject-only behavior. Run all fix‑9 and prior-forge tests plus concurrency. | Capsule/grant/completion key provisioning. |
| **3. S3 authority chain** | WorkOS shadow authority; signed enrollment approval/device credential/challenge/access token; device-request authority; rows reduced to veto/replay/rate state. | WorkOS shadow deploy, token schema/key custody, enforcement flip. |
| **4. S4 composition** | Change claim/heartbeat/candidate/completion interfaces to accept only S3/S2 authorities. No legacy principal or caller-supplied key path. Exercise 1,000-poller and lease/fence tests. | First live route activation. |
| **5. S5 blob binding** | Add `BlobReferenceAttestationV1`; platform rehash and owner-private possession paths; completion requires verified blob authorities; retention/failure state remains negative-only. | Owner-private proof policy and blob signer. |
| **6. GitHub live migration** | Dual-write and shadow-verify approval attestations; replace boolean GitHub probe with typed re-execution authority; enforce both typed approval and current pull authority. Preserve head-bound merge and pending semantics. | Dual-write and enforcement go/no-go; live deploy. |
| **7. Market live migration** | Dual-write ownership/settlement attestations; inventory open positions; drain/re-consent/reconstruct each; remove row and legacy `claimed_by` authority; enforce no-artifact/no-settlement. | **Mandatory:** legacy-money migration and enforcement decision. |
| **8. Adjacent systemic closure** | Signed source approvals and run outcomes; gate claims, canonical ranking, source execution and other irreversible consumers registered as authority sinks. | Behavior changes to approval and canonical-selection policy. |
| **9. System gate and rollout proof** | Run DML+INSERT forges across all surfaces, reset-by-multiplicity suite, key rotation, outage recovery, concurrency/load, live canaries, rendered chatbot tests for affected public surfaces, and post-fix clean-use watch. Remove shadow-only legacy code after evidence. | Final per-surface live cutovers and legacy removal. |

Implementation may begin on isolated/unwired slices after the PLAN and key-hierarchy decision. Every live shadow deployment, schema migration, signer introduction, enforcement flag, money migration, or route activation needs a separate host go/no-go. Independent security review is required before each live enforcement slice.

VERDICT: One sealed `Authority[T]` derived only from verified artifacts or registered platform re-execution can structurally eliminate row/event authority across all surfaces; the largest risk is turning signer custody and live legacy migration—especially market settlement—into a common-mode outage or compromise.