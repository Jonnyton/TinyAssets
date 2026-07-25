## Context

Current main has two host-shaped identities:

1. `tinyassets/host_pool/client.py` posts a caller-supplied `owner_user_id`.
   The canonical host-pool spec requires repeated registration to create
   distinct rows. These rows are availability/capability sessions.
2. PR #1736's `tinyassets/desktop/onboarding.py` creates and persists a local
   `host-{uuid}` and passes it to `OriginClient.register_host`. The client-side
   authorization state machine and native account refresh-token custody exist,
   but `OriginClient` remains a Protocol and the PR explicitly leaves the
   production origin route unfinished.

Neither identifier proves a durable account-to-device relationship. Draft PR
#1746 needs a stable server-attested host principal before a requester-local
provider binding can be trusted, while paid/self-hosting needs the same
identity without conflating it with a liveness row.

## Goals / Non-Goals

**Goals:**

- Bind a verified platform account to a stable, opaque host principal.
- Require proof of possession of a host-local device key without collecting a
  hardware fingerprint.
- Preserve idempotent retry, multi-machine identity, revocation, key rotation,
  expiry, recovery, and non-enumerating reads.
- Keep stable identity separate from host-pool sessions and provider custody.
- Preserve zero-host durability and fail closed before a host advertises or
  receives authority.

**Non-Goals:**

- A new MCP verb, chatbot-visible secret setup route, or second account.
- Hardware attestation, device fingerprinting, geolocation, or private user
  content in the control plane.
- Account refresh-token storage or edits to PR #1736 desktop files.
- Provider-secret/native-reference custody or assignment-state ownership.
- Host-pool scheduling, capability pricing, provider routing, execution grants,
  market leases, settlement, or payment authority.
- Runtime implementation while current identity, host-pool, tray, and custody
  owners have not accepted the boundary.

## Decisions

### 1. Stable host principals and host sessions are different objects

`host_principal_id` is an opaque server-issued identifier for one verified
WorkOS subject and one device public key. It is stable across process restarts,
host-pool re-registration, capability changes, and ordinary account-token
refresh.

Existing host-pool `host_id` rows remain insert-always liveness/capability
sessions. Each authenticated production row records its `host_principal_id`
and `host_principal_generation`, but repeated registration still creates a new
row and exact deregistration still deletes only the selected session. Session
registration and heartbeat require a current-generation device proof. A
session row, heartbeat, tray-local UUID, caller-supplied owner, or capability
grant can never mint or substitute a stable host principal.

The legacy/dev no-auth registration path may remain available for isolated OSS
development, but its rows are explicitly unattested and ineligible for
provider custody, network/paid visibility, distributed execution, or any
authority that requires a verified host principal.

### 2. Account identity comes only from a dedicated validated request context

The production route accepts only the configured WorkOS issuer, the dedicated
`WORKOS_HOST_BINDING_RESOURCE` audience, and a required non-empty WorkOS
`sub`. The `aud` claim must contain exactly that one resource: a token that also
contains `WORKOS_MCP_RESOURCE` or any other audience is refused. The verified
`(issuer, sub)` pair is the sole ownership and uniqueness
axis. A WorkOS `org_id`, when present, must pass the canonical WorkOS
organization-ID validator and is recorded only as non-authoritative metadata;
organization membership changes never transfer, merge, or select a principal.
Personal accounts need no synthetic tenant key.

These origin routes require TLS and `Authorization: Bearer`; they never accept
account authority from cookies, query parameters, browser ambient state, or
MCP connector context. Challenge and mutation requests require
`application/json`, and cross-origin credentialed browser access is disabled.

The host-binding service uses a route-local validator and typed
`HostBindingIdentity` because today's global `Identity` does not retain verified
audience or authentication time. Step-up uses the validated WorkOS `auth_time`
claim proving interactive reauthentication, never access-token `iat`. Refresh and other non-interactive
grants cannot create or advance that time; a stale/missing claim forces a new
interactive reauthentication. The service refuses to start writers when the dedicated
resource is absent or audience validation has been disabled, including
`WORKOS_ALLOW_NO_AUDIENCE`, and never changes or reuses the global MCP
provider. The PR #1736 owner must send the RFC 8707 resource indicator during
authorization/token/refresh, validate the returned audience, and adapt
`OAuthConfig`, `OriginClient`, and onboarding state to the
challenge/proof/principal response protocol. It must initiate WorkOS
reauthentication when a step-up operation lacks a current validated
`auth_time`.

Enrollment requires a token with `host:enroll` and a verified authentication
time no more than five minutes old. Device-proven ordinary operations require
`host:manage`; private inventory additionally requires an authentication time
no more than five minutes old. Lost-key recovery requires the distinct
`host:recover` grant plus the same step-up window. These grants
come from the account authorization service. Personal-account and
organization role-to-scope provisioning must be proven before writers enable;
availability and validation of the interactive `auth_time` claim must also be
proven. Absence or ambiguity keeps writers disabled. An ordinary bearer token,
founder/admin identity, ambient environment identity, host process identity,
universe ACL, body-supplied subject, or maintainer identity is never a
substitute. Missing subject, wrong audience/issuer, disabled audience checking,
expired token, malformed `org_id`, or missing scope fails before challenge,
principal, session, or audit mutation.

### 3. Device proof is challenge-bound and replay-safe

The v1 policy is exactly Ed25519. A client generates a separate key for each
WorkOS subject and stores the private key through PR #1736's approved native
secret-store seam. The server accepts only a valid RFC 8037 public JWK with
exactly `kty=OKP`, `crv=Ed25519`, and `x`; `x` is canonical unpadded
base64url that decodes and round-trips to exactly 32 bytes. Signatures are
canonical unpadded base64url that decode and round-trip to exactly 64 bytes. It
derives the algorithm from the server policy/record, never from a request
header. Additional algorithms require a spec change and downgrade/confusion
tests.

All signed payloads use RFC 8785 JSON Canonicalization Scheme over I-JSON.
The decoder rejects duplicate member names, invalid Unicode, non-finite
numbers, and non-canonical key material before verification. The signed bytes
are the ASCII domain separator `tinyassets.host-principal-proof.v1` followed
by a NUL byte and the exact RFC 8785 bytes acted on by the server. Body binding is the
SHA-256 digest of the route's parsed-and-validated typed operation intent,
excluding challenge, nonce, signature, proof wrapper, and transport-only
fields, so the signed-body contract is not circular.

Registration is a two-step authenticated protocol:

1. The client requests a 32-byte CSPRNG challenge. The server binds its keyed
   identifier to verified issuer and subject, dedicated audience, public-key
   RFC 7638 thumbprint, exact uppercase HTTP method, a route-owned canonical
   path constant that never derives from `Host`/forwarded headers,
   canonical body digest, policy version, idempotency scope, issue time, and a
   five-minute expiry.
2. The response includes the exact canonical signing bytes encoded for
   transport, so the client decodes and signs rather than reimplementing JCS.
   The server re-derives and byte-compares those bytes, validates every binding,
   and verifies Ed25519 outside the database write lock. In a fixed-order
   transaction it CAS-consumes the challenge, acquires idempotency and then
   subject/key uniqueness, and inserts or returns the principal. Invalid proof
   never consumes the challenge.

Post-enrollment exact read, revoke, rotate, renew, session register/heartbeat/
deregister, and the new-key leg of recovery use a fresh server nonce and the
same `HostProofV1` canonicalization. Private self-inventory instead uses the
step-up account path defined below. The proof envelope binds verified issuer and
subject, `host_principal_id`, expected `host_principal_generation`, dedicated
audience, method, canonical external path, canonical body digest, nonce/JTI,
issued-at, expiry, and policy version. Proof lifetime is at most five minutes.
Every canonical path is a route-owned constant and never derives from
`Host`, `Forwarded`, or `X-Forwarded-*` input.
Nonce consumption is atomic and precedes mutation; replay cannot be authorized
by a bearer, idempotency record, or host session. This is a TinyAssets device
proof, not OAuth DPoP, hardware attestation, or RFC 9449 token binding.

Each subject may hold at most five live challenges. Challenge creation is
limited to ten requests per minute per verified subject and a secondary
thirty-per-minute source-network ceiling. Limit and authentication failures use
the same non-enumerating response shape and bounded timing class. Challenges
store no bearer, refresh token, signature, or raw request body.

The same challenge service issues post-enrollment nonces. Those nonces have the
same five-minute/one-use rules, at most five live per principal, and limits of
60 per minute per principal and 600 per minute per source network. Enrollment
and post-enrollment buckets are independent so heartbeat traffic cannot exhaust
enrollment, and every operation revalidates its bearer both when issuing the
challenge and when completing the operation.

#### Normative v1 operation and wire matrix

`POST /v1/host-proof-challenges` accepts
`HostChallengeRequestV1 {schema_version: "host-binding-v1", operation,
intent}` and returns
`HostChallengeV1 {schema_version: "host-binding-v1", challenge_id_b64u,
signing_input_b64u, expires_at, policy_version}`. Both encoded fields are
canonical unpadded base64url.
Every proof-requiring completion route accepts only
`HostProofSubmissionV1 {schema_version: "host-binding-v1",
challenge_id_b64u, signatures}` where `signatures` is
the exact closed role map required by the operation (`new` for enroll/recover,
`current` for ordinary operations, and `current` plus `new` for rotation); the stored
challenge binding supplies the typed intent, so the proof wrapper is excluded
from its digest. Every signature value is canonical unpadded base64url.
Rotation signs the same exact signing input with two distinct keys; missing,
extra, duplicate, swapped-role, same-key, or malformed signatures fail before
nonce consumption.
Successful principal-bearing operations return
`HostPrincipalResultV1 {schema_version: "host-binding-v1",
host_principal_id, host_principal_generation, status, expires_at,
policy_version}`. Refusals use
`HostBindingErrorV1 {schema_version: "host-binding-v1",
error: "host_binding_refused", retryable}`; `409` is
reserved for same-scope/different-intent conflict and `429` carries a bounded
`Retry-After`.

All operation routes require a fresh dedicated-audience token at challenge and
completion. The exact matrix is:

| Operation | Completion route | Additional bearer rule | Device proof |
|---|---|---|---|
| `enroll` | `POST /v1/host-principals` | `host:enroll`, auth age <=5m | new key |
| `inventory` | `GET /v1/host-principals` | `host:manage`, auth age <=5m | none; no challenge |
| `read` | `POST /v1/host-principals/{id}:read` | `host:manage` | current key/generation |
| `revoke` | `POST /v1/host-principals/{id}:revoke` | `host:manage` uses proof submission; step-up `host:recover` uses direct account intent | current key; none on recovery grant |
| `rotate` | `POST /v1/host-principals/{id}:rotate` | `host:manage` | current and new keys |
| `renew` | `POST /v1/host-principals/{id}:renew` | `host:manage` | current key/generation |
| `recover` | `POST /v1/host-principals/{id}:recover` | `host:recover`, auth age <=5m | new key |
| `session_register` | `POST /v1/host-sessions` | `host:manage` | current key/generation |
| `session_heartbeat` | `POST /v1/host-sessions/{id}:heartbeat` | `host:manage` | current key/generation |
| `session_deregister` | `POST /v1/host-sessions/{id}:deregister` | `host:manage` | current key/generation |

The closed intent variants are:

- `EnrollIntentV1 {idempotency_key_b64u, public_jwk, device_label?}` where the
  idempotency key decodes to 32 bytes and `device_label` is optional UTF-8,
  normalized NFC, and at most 64 characters;
- `PrincipalIntentV1 {host_principal_id, expected_generation}` for read;
- `RevokeIntentV1 {host_principal_id, expected_generation,
  idempotency_key_b64u, reason_code?}` with an allowlisted reason;
- `RotateIntentV1 {host_principal_id, expected_generation,
  idempotency_key_b64u, new_public_jwk}`;
- `RenewIntentV1 {host_principal_id, expected_generation,
  idempotency_key_b64u}`;
- `RecoverIntentV1 {host_principal_id, expected_generation,
  idempotency_key_b64u, new_public_jwk, device_label?}`;
- `AccountRevokeIntentV1 {schema_version: "host-binding-v1",
  host_principal_id, expected_generation, idempotency_key_b64u, reason_code?}`
  for the direct recent-`host:recover` path;
- `SessionRegisterIntentV1 {host_principal_id, expected_generation, provider,
  capability_id, visibility, price_floor, max_concurrent, always_active,
  idempotency_key_b64u}` with
  the current host-pool enums/ranges and no owner field;
- `SessionHeartbeatIntentV1 {host_principal_id, expected_generation,
  host_session_id}`.
- `SessionDeregisterIntentV1 {host_principal_id, expected_generation,
  host_session_id, idempotency_key_b64u}`.

Unknown fields, operations, enum values, and schema versions fail closed.
Challenge/completion route constants are signed exactly as the literal matrix
strings; `{id}` is also bound separately by the typed intent and must equal the
request path value. PR #1736 may share these versioned DTO definitions but may
not depend on server-private serializers.

Inventory accepts only `cursor` and `limit` query fields and returns
`HostInventoryPageV1 {schema_version: "host-binding-v1", items,
next_cursor?}` where each `HostInventoryItemV1` contains exactly principal ID,
status, generation, policy version, issue/expiry times, optional coarse
last-seen bucket, and optional bounded device label. Exact read returns
`HostPrincipalDetailV1` with exactly those fields plus the RFC 7638 thumbprint.
Recovery returns
`HostRecoveryResultV1 {revoked, replacement}` using two
`HostPrincipalResultV1` values. Session registration returns
`HostSessionResultV1 {host_session_id, host_principal_id,
host_principal_generation}`; heartbeat returns
`HostHeartbeatResultV1 {host_session_id, accepted_generation,
status: "active"}`; deregistration returns
`HostSessionDeregisterResultV1 {host_session_id, status: "deleted"}`. A no-device lost-key revoke uses direct
`AccountRevokeIntentV1` with the same 32-byte idempotency key and exact
generation under recent `host:recover`; it does not issue or accept a device
proof. All mutation idempotency scopes use the crash/retry rules below.

Heartbeat is the sole mutation intentionally exempt from durable idempotency.
After a fresh nonce/current-generation proof it sets only the exact session's
`updated_at = max(stored_updated_at, database_transaction_time)`. A
response-loss retry obtains a fresh nonce and may advance only that timestamp.
It cannot create/resurrect a session or change principal expiry/generation,
capability, visibility, price, concurrency, assignment, or other authority.

### 4. Idempotency and multi-machine behavior are explicit

The server enforces one principal for the exact
`(issuer, account_subject, device_key_thumbprint)` tuple and refuses reuse of
one device key across different subjects. Clients therefore generate a
separate key per account. Cross-account collision checks are internal and
non-enumerating; there is no public global thumbprint lookup. A different key
under one subject creates a distinct principal.

Registration idempotency keys contain exactly 32 CSPRNG bytes encoded as
canonical unpadded base64url and are scoped
to the verified subject, policy version, route, JWK thumbprint, and canonical
body digest. Only a server-keyed hash is stored. A changed body conflicts.
After response loss, a client obtains a fresh challenge and resubmits the same
idempotency scope. The fresh proof is always verified and consumed; then the
transaction returns the previously committed result without a second mutation.
An exact challenge replay always fails.

After proof verification, the database transaction CAS-consumes the fresh
challenge, acquires idempotency and subject/key uniqueness in that fixed order,
writes the principal plus idempotency result, and commits before a response is
sent.
A crash before commit leaves neither consumed authority nor a principal; a
crash after commit is recovered by the fresh-challenge idempotent retry.
Concurrent first registrations converge on the committed winner and exact
generation without split brain. Idempotency results expire after 24 hours and
never serve as account or device authority.

### 5. Activation, reads, revocation, and rotation are narrow

The stable principal lifecycle is `pending -> active -> revoked|expired`.
`revoked` and `expired` are terminal for that principal identifier; identifiers
are never recycled. Activation occurs only after challenge verification and
transactional persistence. A principal expires after 90 days. During its last
30 days, current device proof plus a current dedicated-audience token may renew
it for another 90 days. Expiry is terminal for that principal and requires
enrollment of a new principal. Terminal key reuse is denied for the exact
365-day tombstone window defined below and can never reactivate the old ID.

An exact host read returns only principal ID, status, generation, RFC 7638
thumbprint, issue/expiry times, and policy version after current account and
device proof. A step-up `host:manage` self-inventory may list only that
subject's principal IDs, status, generation, and timestamps so an
owner can find and revoke a lost device. It uses subject-bound opaque cursors,
25 rows by default, and 100 maximum; it never exposes keys, thumbprints,
provider/custody/session/capability data, or another subject. It may return the
optional bounded `device_label`, which is explicitly user content and is never
logged. An inventory
result grants neither device proof nor consumer authority. Internal consumers present separate service authority and may ask
only whether an exact `(principal_id, generation, subject)` tuple is active.

Revocation requires either current device proof or a step-up `host:recover`
grant for the same subject. It increments generation and atomically marks the
principal revoked. Attached sessions become ineligible at the next authority
check; every sensitive consumer must re-check immediately before starting or
committing protected work, so already queued/in-flight work cannot cross that
boundary on stale authority. Repeated revoke is idempotent.

In-place rotation requires current device proof, proof by the new Ed25519 key,
the exact expected generation, and a fresh rotation challenge covering both
thumbprints. The new key must have neither an active binding nor a live
anti-reuse tombstone. Success
atomically increments generation, replaces the public key, tombstones the old
thumbprint, and fences sessions/consumers carrying the prior generation.
Lost-key recovery never rotates in place. The recovery challenge binds the old
principal/generation, a 32-byte idempotency key, the new key, and optional
bounded device label. After new-key proof, one transaction consumes the
challenge, locks the recovery idempotency scope, revokes the old principal,
creates the new principal, and commits both generations before responding.
A pre-commit failure changes neither principal; response loss resumes with a
fresh challenge and the same idempotency scope and returns the committed pair.
`host:recover` authorizes this replacement enrollment without a separate
`host:enroll` scope, so a valid recovery cannot strand the owner between
revocation and replacement. Founder/admin identity and an ordinary bearer token
cannot recover it.

Authenticated host sessions and every authority-requiring consumer carry and
check `host_principal_generation`. Draft #1746 must carry both that generation
and its separate provider-assignment generation; neither a client response nor
a host-pool row is control-plane evidence.

### 6. Storage and observability are minimized and secret-free

The active durable record contains opaque principal ID, verified issuer and
subject, optional validated organization metadata, Ed25519 public JWK, its
standard RFC 7638 thumbprint, status/generation, optional bounded device label,
timestamps, policy
version, and non-content revocation reason code. It contains no WorkOS
bearer/refresh token, private key, provider secret/reference, universe data,
prompt, node, branch, or user content beyond that disclosed management label.

Logs, traces, metrics, errors, and audit receipts omit tokens, signatures,
public-key bytes, device labels, challenge material, idempotency keys, request bodies,
standard thumbprints, and organization metadata. Where correlation is
necessary, logs use a separately named server-HMAC pseudonym with a versioned
secret from the deployment secret catalog; rotation supports overlap for
verification but new events use only the current version. It is never returned
to clients or used as the RFC 7638 binding value.

Consumed/expired challenges are deleted within 24 hours and idempotency results
within 24 hours. On terminal revocation/expiry, the public key is erased within
30 days. A separately keyed, owner-free tombstone blocks that key for 365 days;
the principal identifier is never reused. After tombstone expiry, the same key
can enter only a new principal through a new step-up enrollment and can never
reactivate the old principal. Account export includes the owner's inventory
metadata but not internal pseudonyms. Account deletion immediately revokes
attached sessions and erases subject links, public keys, challenges, and
idempotency records within 30 days unless a user-visible legal hold applies;
the disclosed owner-free 365-day anti-reuse tombstone and non-linkable aggregate
metrics may remain. There is no hardware fingerprint, geolocation, public
inventory, or cross-account query surface.

### 7. Host-principal authority does not imply any downstream authority

An active host principal proves only that one verified account bound one
device key. It does not grant provider access, credential resolution, compute
eligibility, network or paid visibility, work claim/lease, universe access,
market participation, settlement, spending, or maintainer resources.

Every consumer composes its own authority. Draft PR #1746 additionally
validates provider/universe/scope/assignment generation; the host pool
additionally validates capability and visibility; distributed execution
additionally validates its signed owner/daemon/job/capsule/lease/fence chain.
Missing consumer authority fails closed.

### 8. Deployment is readers-first and concurrency-proven

Schema/storage support and readers deploy before any authenticated writer or
consumer requires `host_principal_id`. Legacy unattested rows remain readable
but never become attested by inference. No migration assigns stable principals
from caller-supplied owners or tray UUIDs.

Mixed-version readers tolerate null principal/generation only as explicitly
unattested legacy state. Old clients cannot enroll or receive verified-host
authority and no compatibility fallback accepts a tray UUID or MCP-audience
token. Rollback disables writers/consumers before schema rollback; new rows
remain readable and no generation is inferred or downgraded.

Activation requires deterministic concurrency proofs in a separate Supabase
test project with at least three server processes and 500 concurrent clients
owned by 500 test subjects across 50 simulated source-network partitions.
An untimed setup phase enrolls one baseline principal per subject. It selects
125 disjoint subjects to enroll a second device, pre-issues only the 125 fresh
enrollment challenges needed for their first completions, and pre-issues 225
of the 400 post-enrollment nonces
needed by proof-bearing timed operations, never exceeding five live items per
principal. Pre-issued items are created during the final 30 seconds before the
timer and consumed during the first 60 seconds, leaving at least 210 seconds
of TTL margin. After each simulated lost initial-enrollment response, the retry
obtains its required fresh challenge during the timed phase. Remaining
completions consume challenges/nonces issued during
the timed phase. The timed phase sends exactly 1,000 HTTP requests in five minutes:
300 challenge/nonce issuances (125 enrollment retries, 175 post-enrollment), 250
enrollment/idempotent-retry completions (125 each), 150 reads (100 exact, 50
inventory), 150 host-session operations (50 register, 50 heartbeat, 50 exact
deregister), and 150
lifecycle operations (50 revoke, 50 rotate, 50 renew).

The main success run must stay below every rate ceiling and achieve p95 under
1.5 seconds and p99 under 3 seconds over successful timed requests, zero
unexpected HTTP responses, zero lost or duplicate authority mutations, and no
deadlock/split brain. A separate abuse phase, excluded from latency
percentiles, drives one subject and source network one request beyond each
published ceiling and requires the exact expected `429`, bounded `Retry-After`,
and zero mutation. Both phases must prove single-use nonces, one same-key
principal, distinct devices, monotonic generation, cross-instance revocation
fencing, bounded pagination, and zero founder/maintainer credential, quota,
model, or compute use.

## Risks / Trade-offs

- **A device key is lost:** account recovery revokes the old principal and
  enrolls a new one; it never reconstructs or transfers the old key.
- **A user reinstalls:** default to a new device principal unless the approved
  native store still proves the old key. Do not fingerprint hardware to guess.
- **Host-pool code mistakes session ID for principal ID:** use distinct typed
  identifiers and negative tests; never reuse the same column/name.
- **Challenge storage is abused:** short TTL, one-use consumption, scoped rate
  limits, bounded per-account outstanding challenges, and periodic deletion.
- **A stable host ID becomes tracking data:** keep reads ownership-scoped and
  non-enumerating; self-inventory is private, bounded, subject-derived, and
  exposes no public or cross-account host directory.
- **A short-lived enrollment bearer is stolen:** dedicated audience, recent
  step-up, narrow scopes, rate limits, owner inventory, and recovery reduce the
  window but do not make the bearer proof-of-possession. OAuth DPoP remains an
  explicit non-goal; this residual risk is visible in the security review.
- **This duplicates PR #1736:** its owner adapts the client protocol and
  native-store-owned onboarding state; this lane implements only the server
  contract and requires owner acceptance before runtime claims.

## Migration Plan

1. Obtain PR #1736 owner acceptance to adapt `OAuthConfig`, authorization and
   refresh resource-indicator handling, `OriginClient`, and onboarding state
   to the dedicated audience/challenge/proof/principal response while this lane
   does not edit its desktop files.
2. Obtain identity/host-pool and draft PR #1746 owner acceptance of the stable
   principal/session/custody split.
3. Add route-local dedicated-audience validation, storage, typed IDs,
   challenge verification, bounded self-inventory, exact reads,
   revocation/rotation, and session linkage behind disabled writers.
4. Deploy readers/storage first and prove legacy rows remain unattested.
5. Adapt the PR #1736 client owner to device proof and the server-issued
   principal response; do not copy account tokens or private keys.
6. Run focused security/concurrency tests and the named
   `docs/design-notes/2026-04-18-full-platform-architecture.md` §14 scale proof.
7. Enable authenticated production registration, then allow downstream
   consumers to require the stable principal one by one.
8. Prove live source/receipt, packaged mirror parity, rendered tray onboarding,
   and post-fix organic use or retain a dated monitoring row.

## Open Questions

The security-critical protocol decisions are frozen above before RED tests.
The implementation lane still must identify and claim the narrow route-local
origin/auth module after current owners release exact files. That file-location
choice cannot weaken the dedicated audience, step-up, proof, lifecycle,
privacy, or load requirements.
