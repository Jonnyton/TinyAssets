## ADDED Requirements

### Requirement: Production host ownership derives from a dedicated WorkOS audience and subject

An authenticated production host-binding route SHALL use a route-local
validator for the configured WorkOS issuer and the mandatory
`WORKOS_HOST_BINDING_RESOURCE`. It SHALL NOT fall back to
`WORKOS_MCP_RESOURCE`, the global MCP provider, or
`WORKOS_ALLOW_NO_AUDIENCE`; missing dedicated configuration or disabled
audience checking SHALL keep every host-binding writer disabled.
The validator SHALL produce a typed host-binding request context containing
the verified audience and authentication time; the current global `Identity`
object SHALL NOT be treated as sufficient authority for these routes.
The `aud` claim SHALL contain exactly `WORKOS_HOST_BINDING_RESOURCE`; a token
that also contains `WORKOS_MCP_RESOURCE` or any other audience SHALL be
refused.
The routes SHALL require TLS and `Authorization: Bearer`; SHALL reject cookie,
query-string, browser-ambient, and MCP-connector authority; SHALL require
`application/json` for challenge/mutation bodies; and SHALL disable
credentialed cross-origin browser access.

The verified `(issuer, sub)` pair SHALL be the sole owner and uniqueness axis.
A present `org_id` SHALL pass the canonical WorkOS organization-ID validator
and MAY be stored only as non-authoritative metadata. Organization membership
changes SHALL NOT transfer, merge, or select a host principal. The request
SHALL accept no authoritative owner, subject, tenant, or organization selector.

Enrollment SHALL require `host:enroll` and a verified authentication time no
more than five minutes old. Device-proven ordinary operations SHALL require
`host:manage`; private inventory SHALL additionally require authentication no
more than five minutes old. Lost-key recovery SHALL require distinct
`host:recover` with the same step-up window. Personal-account and organization role-to-scope provisioning
SHALL be proven before writers enable; missing or ambiguous provisioning SHALL
keep writers disabled. Step-up SHALL use the validated WorkOS `auth_time`
claim proving interactive reauthentication.
Access-token `iat`, refresh, and other non-interactive grant times SHALL NOT
satisfy or advance the window; missing/stale interactive time SHALL require
reauthentication, and unavailable validation SHALL keep writers disabled. Body
owner, ambient environment, host process, universe ACL,
anonymous, MCP-audience, ordinary bearer, and maintainer/founder identity
SHALL fail before challenge, principal, session, or audit mutation.

#### Scenario: Dedicated-audience subject may begin enrollment

- **WHEN** a current token from the configured WorkOS issuer carries the exact host-binding audience, non-empty `sub`, recent authentication, and `host:enroll`
- **THEN** the server may create a challenge scoped to that verified subject
- **AND** a validated `org_id` remains metadata rather than ownership authority

#### Scenario: MCP or audience-disabled authority is refused

- **WHEN** a token carries the MCP audience alone or alongside the host-binding audience, carries any other audience, lacks the dedicated resource, or audience validation is disabled
- **THEN** the host-binding route fails before mutation
- **AND** neither a body field nor maintainer/founder authority supplies a fallback

#### Scenario: Organization change does not transfer ownership

- **WHEN** the verified subject joins, leaves, or changes a WorkOS organization
- **THEN** its principal owner remains the same verified `(issuer, sub)`
- **AND** no organization field selects or transfers another subject's principal

### Requirement: HostProofV1 is pinned, canonical, and replay-safe

Policy `host-binding-v1` SHALL accept exactly Ed25519 public JWKs conforming to
RFC 8037 with exactly the members `kty=OKP`, `crv=Ed25519`, and `x`.
`x` SHALL be canonical unpadded base64url that decodes and round-trips to 32
bytes; signatures SHALL be canonical unpadded base64url that decode and
round-trip to 64 bytes. The server SHALL derive the algorithm from its policy
or stored record, never from an untrusted algorithm selector.

Signed payloads SHALL be I-JSON canonicalized with RFC 8785. Parsing SHALL
reject duplicate member names, invalid Unicode, non-finite numbers, invalid key
material, and non-canonical alternatives. The signed bytes SHALL be the ASCII
domain `tinyassets.host-principal-proof.v1`, one NUL byte, and the exact RFC 8785 bytes
acted on by the server. Body binding SHALL use SHA-256 of the route's
parsed-and-validated typed operation intent, excluding challenge, nonce,
signature, proof wrapper, and transport-only fields.

Enrollment challenges SHALL contain 32 CSPRNG bytes encoded as canonical
unpadded base64url, expire within five minutes, and bind verified issuer/sub,
dedicated audience, RFC 7638 JWK thumbprint, exact method, a route-owned
canonical path constant that never derives from host/forwarded headers, body digest, policy,
idempotency scope, issued-at, and expiry. Post-enrollment `HostProofV1` SHALL
bind issuer/sub, principal ID, expected principal generation, dedicated
audience, method, canonical path, body digest, one-use nonce/JTI, issued-at,
expiry, and policy. Nonce consumption and every binding check SHALL be atomic
before mutation. The challenge response SHALL provide the exact encoded
canonical signing bytes so the client only decodes and signs. The server SHALL
re-derive and byte-compare them and verify Ed25519 before taking a database
write lock; invalid proof SHALL NOT consume the challenge.

Each subject SHALL have at most five live challenges, with no more than ten
challenge creations per minute per subject and thirty per minute per source
network. Post-enrollment nonce issuance SHALL allow at most five live per
principal, sixty per minute per principal, and six hundred per minute per
source network in a separate bucket. Authentication, rate-limit, absence, mismatch, and replay failures
SHALL have a non-enumerating response shape and bounded timing class. This
device proof SHALL NOT be described as OAuth DPoP, RFC 9449 token binding, or
hardware attestation.

#### Scenario: Exact Ed25519 envelope activates a principal

- **WHEN** the verified subject signs an unexpired enrollment envelope with the private key matching the exact accepted JWK
- **THEN** the server atomically consumes the challenge and creates or idempotently returns that subject's principal
- **AND** no token, private key, signature, raw challenge, or body enters the principal record

#### Scenario: Replay or canonicalization variant is refused

- **WHEN** a proof reuses a nonce or changes subject, audience, generation, method, path, canonical body, key, time, policy, JSON member set, or Unicode representation
- **THEN** verification fails before principal, session, or audit mutation
- **AND** neither an idempotency key nor an existing session upgrades the proof

#### Scenario: Post-enrollment mutation proves current generation

- **WHEN** a host reads, revokes, rotates, renews, registers/deregisters a session, or heartbeats
- **THEN** its fresh proof binds the exact current principal generation and operation
- **AND** stale-generation or replayed proof fails before the operation

### Requirement: Host-binding v1 wire operations are closed and scope-specific

The server SHALL issue all enrollment and post-enrollment proofs through
`POST /v1/host-proof-challenges` with
`HostChallengeRequestV1 {schema_version: "host-binding-v1", operation,
intent}` and
`HostChallengeV1 {schema_version: "host-binding-v1", challenge_id_b64u,
signing_input_b64u, expires_at, policy_version}`. Proof-requiring completion
routes SHALL accept only
`HostProofSubmissionV1 {schema_version: "host-binding-v1",
challenge_id_b64u, signatures}` with the closed
signature-role map required by the operation: `new` for enroll/recover,
`current` for ordinary operations, and both for rotate. Rotation's two distinct
keys SHALL sign the same exact signing input; missing, extra, duplicate,
swapped-role, same-key, or malformed signatures SHALL fail before nonce
consumption. Principal results SHALL expose only schema version, principal ID,
generation, status, expiry, and policy.
Unknown fields, schema versions, operations, or enum values SHALL fail closed.

Both challenge issuance and completion SHALL revalidate the dedicated-audience
token. The closed operation policy SHALL be:

- enroll at `POST /v1/host-principals`: recent `host:enroll`, new-key proof;
- inventory at `GET /v1/host-principals`: recent `host:manage`, no device proof;
- read/revoke/rotate/renew at the literal
  `POST /v1/host-principals/{id}:{operation}` routes: `host:manage` and current
  generation proof, with rotation additionally proving the new key;
- lost-key revoke/recover at the same exact-ID routes: recent `host:recover`,
  with direct revoke using
  `AccountRevokeIntentV1 {schema_version: "host-binding-v1",
  host_principal_id, expected_generation, idempotency_key_b64u, reason_code?}`
  and recovery proving the new key without requiring `host:enroll`;
- session registration at `POST /v1/host-sessions` and heartbeat at
  `POST /v1/host-sessions/{id}:heartbeat`: `host:manage` and current
  generation proof;
- exact deregistration at `POST /v1/host-sessions/{id}:deregister`:
  `host:manage`, current-generation proof, and mutation idempotency.

Enrollment and recovery intents SHALL bind a 32-byte idempotency key, exact
public JWK, and optional NFC device label of at most 64 characters. Exact-read
intents SHALL bind principal ID and expected generation. Revoke, rotate, renew,
recovery, and session-registration mutations SHALL bind a 32-byte idempotency
key; rotation/recovery SHALL also bind the new JWK. Session registration SHALL bind provider,
capability ID, visibility, price floor, max concurrency, and always-active
using current host-pool enums/ranges and no owner field; heartbeat SHALL bind
the exact session ID; deregistration SHALL additionally bind a 32-byte
idempotency key. The literal route template and every substituted ID SHALL
be bound and checked. Refusals SHALL use one
`HostBindingErrorV1 {schema_version: "host-binding-v1",
error: "host_binding_refused", retryable}` shape, with
`409` only for idempotency intent conflict and bounded `Retry-After` on `429`.
Inventory SHALL accept only cursor/limit query fields and return
`HostInventoryPageV1` containing only principal ID, status, generation, policy
version, issue/expiry times, optional coarse last-seen bucket, and optional
bounded device label per item. Exact read SHALL return
`HostPrincipalDetailV1` with exactly that allowlist plus RFC 7638 thumbprint;
recovery SHALL return typed revoked/replacement principal results; session
register/heartbeat/deregister SHALL return only exact session ID, accepted
principal generation where applicable, and active/deleted status. A no-device
lost-key revoke SHALL accept that exact direct account intent only under recent
`host:recover`; it SHALL NOT accept or infer device proof.

#### Scenario: Client and server share one testable signing contract

- **WHEN** the packaged-tray client owned by merged #1736 requests a challenge for a closed v1 operation
- **THEN** the server returns the exact signing bytes and both sides use the same versioned DTO and literal route binding
- **AND** neither side depends on server-private serialization or proxy headers

#### Scenario: Operation authority cannot be substituted

- **WHEN** a caller uses the wrong scope, stale step-up, absent required device proof, wrong route, unknown field, or inventory result
- **THEN** the operation fails before nonce consumption or domain mutation
- **AND** no stronger operation inherits authority from a weaker one

### Requirement: Durable mutating retries converge without challenge replay

Every durable mutating intent except heartbeat SHALL carry exactly 32 CSPRNG idempotency bytes as
canonical unpadded base64url. The server SHALL store only a domain-separated
keyed hash bound to subject, policy, operation, literal route, and canonical
intent digest; enrollment/rotation/recovery SHALL additionally bind the exact
JWK thumbprints. After response loss on a proof-requiring operation, the client
SHALL obtain and prove a fresh challenge; after consumption, the same scope and
intent SHALL return the previously committed result without another mutation.
Direct account-authority revoke SHALL revalidate recent `host:recover` before
the same lookup. Exact challenge replay SHALL always fail and changed-intent
reuse SHALL return `409`.

After proof verification, challenge CAS consumption, idempotency lookup/write,
subject/key uniqueness, principal write, and generation SHALL commit in that
fixed order in one transaction before response. A pre-commit crash SHALL leave no partial
principal or consumed durable authority; a post-commit crash SHALL recover via
fresh-challenge retry. Idempotency results SHALL expire within 24 hours and
SHALL never serve as subject or device authority.

Heartbeat SHALL be the sole mutation exempt from durable idempotency. With a
fresh nonce and current-generation proof it SHALL set only the exact session's
`updated_at` to the maximum of its stored value and database transaction
time. Response-loss retry SHALL obtain a fresh nonce and MAY advance only that
timestamp. It SHALL NOT create or resurrect a session or change principal
expiry/generation, capability, visibility, price, concurrency, assignment, or
any other authority.

A device key SHALL bind to at most one WorkOS subject. Reuse across subjects
SHALL fail non-enumeratingly, while distinct per-account keys for one subject
SHALL produce distinct principals. No public global key or thumbprint lookup
SHALL exist.

#### Scenario: Response-loss retry returns one result

- **WHEN** a committed mutation response is lost and the same subject/operation/intent/idempotency scope is retried with fresh required authority
- **THEN** the fresh proof or account step-up is verified and the prior typed result is returned
- **AND** no second principal, session, lifecycle, or generation mutation occurs

#### Scenario: Concurrent first registration has one winner

- **WHEN** multiple server instances race valid first registrations for the same subject and key
- **THEN** transactional uniqueness produces exactly one principal and one initial generation
- **AND** every successful retry observes the committed winner without split brain

#### Scenario: Cross-account key reuse reveals nothing

- **WHEN** a device key already bound to one subject is offered by another
- **THEN** enrollment fails with the same non-enumerating class as an invalid binding
- **AND** the response exposes no prior subject, principal, or global lookup

### Requirement: Owner inventory is private, bounded, and not device authority

A step-up `host:manage` token for the dedicated audience SHALL list only the
verified subject's own principals without device proof. The request SHALL
accept no owner/subject/tenant selector. Results SHALL use opaque cursor
pagination with a default page of 25 and maximum page of 100, and return only
opaque principal ID, status, generation, policy version, issue/expiry times,
optional coarse last-seen bucket, and optional NFC device label of at most 64
characters. The label SHALL be treated as bounded user content, omitted from
logs, and included in export/deletion.

Inventory SHALL omit public keys/thumbprints, provider or custody references,
capabilities, host-session details, other-subject existence, and internal
pseudonyms. It SHALL NOT be a public directory, market listing, MCP action,
device proof, or internal-consumer grant.

#### Scenario: Lost-device owner finds an exact principal

- **WHEN** a step-up owner lists its own principals after losing a device key
- **THEN** bounded results let it select an exact principal ID for the separate recovery/revocation flow
- **AND** the inventory result itself grants no revocation, device, session, or consumer authority

#### Scenario: Inventory cannot cross subjects or grow unbounded

- **WHEN** a caller injects another owner/subject, presents an MCP-audience token, requests more than 100 rows, or follows a cursor outside its verified subject
- **THEN** the route refuses or bounds the request without revealing another subject
- **AND** no key, thumbprint, capability, session, provider, or custody field is returned

### Requirement: Host-principal lifecycle is monotonic, recoverable, and privacy-bounded

The lifecycle SHALL be `pending -> active -> revoked|expired`. A principal
SHALL expire after 90 days and MAY renew for 90 days during its final 30 days
with current device proof and dedicated-audience authority. Revoked and expired
identifiers SHALL be terminal, SHALL NOT be reused, and SHALL require a new
principal and a key with no live anti-reuse tombstone.

Exact reads SHALL require the same verified subject and current device proof,
or a separately authorized internal exact-tuple consumer. Revocation SHALL
require current device proof or same-subject step-up `host:recover`, increment
generation, and prospectively fence attached sessions and consumers. Every
sensitive consumer SHALL re-check immediately before starting or committing
protected work. Rotation SHALL prove both current and new Ed25519 keys, bind
the exact expected generation, reject a new key with an active binding or live
anti-reuse tombstone, increment
generation atomically, and leave no dual-active window. Lost-key recovery SHALL
prove a new key and SHALL atomically revoke the old principal and enroll a new
one in one generation/idempotency transaction; it SHALL NOT rotate in place.
Pre-commit failure SHALL change neither principal, while response-loss retry
with a fresh challenge and the same idempotency scope SHALL return the
committed pair. `host:recover` SHALL authorize replacement enrollment without
requiring `host:enroll`.

Active storage MAY contain verified issuer/sub, optional validated organization
metadata, public JWK, RFC 7638 thumbprint, status/generation, optional bounded
device label,
timestamps, policy, and non-content reason code. Logs SHALL omit the label and
those identity/key fields and MAY use only a separately named, versioned server-HMAC
pseudonym. Challenges and idempotency results SHALL be deleted within 24 hours.
Terminal public keys SHALL be erased within 30 days. A separately keyed,
owner-free tombstone SHALL block key reuse for 365 days; the old identifier
SHALL never reactivate or be reused. After tombstone expiry, that key MAY enter
only a new principal through new step-up enrollment. Account export SHALL
include owner inventory metadata. Account deletion SHALL revoke sessions and
erase subject links, public keys, challenges, and idempotency records within 30
days absent a user-visible legal hold; the disclosed owner-free 365-day
anti-reuse tombstone and non-linkable aggregate metrics MAY remain.

#### Scenario: Rotation proves both keys and fences stale generations

- **WHEN** the owner completes a fresh rotation challenge with valid current-key and new-key proofs at the expected generation
- **THEN** the server atomically advances generation and replaces the key
- **AND** prior-generation sessions, consumers, proofs, and the old key become ineligible

#### Scenario: Lost-key recovery creates a new identity

- **WHEN** the same subject presents recent step-up `host:recover` without the old device key
- **THEN** one atomic idempotent transaction revokes the exact old principal and enrolls the separately proven new key
- **AND** ordinary bearer, founder/admin identity, and the old identifier cannot reactivate it

#### Scenario: Account deletion erases linkable host identity

- **WHEN** account deletion becomes effective
- **THEN** attached sessions are revoked immediately and bounded deletion erases linkable principal/key/proof state
- **AND** only non-linkable aggregate metrics may remain after the disclosed retention window
