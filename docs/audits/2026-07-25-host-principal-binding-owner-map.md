# Host-principal binding owner map

**Date:** 2026-07-25
**Environment:** Windows worktree `wf-host-principal-binding`, base
`origin/main` initially `3f933caf`, then folded through `6cde7ef0`; PR #1736
protocol inspected at `31d4bf9d` and rechecked at current head `dccbadba`
(desktop diff empty); draft PR #1746 owner-resolution head inspected at
`4c1c6eb5`.
**Scope:** OpenSpec and ownership evidence only; no runtime, canonical-spec,
production, or deployment mutation.

## Current gap

TinyAssets has no production server route that binds a verified WorkOS subject
to a stable host principal:

- `openspec/specs/daemon-identity-and-host-pool/spec.md` keeps repeated
  host-pool registrations as distinct availability/capability sessions.
- `tinyassets/host_pool/client.py:200-220` accepts caller-supplied
  `owner_user_id`; `tinyassets/host_pool/registration.py:62-65` inserts a new
  session and returns its ID. Neither proves stable account ownership.
- PR #1736 `tinyassets/desktop/onboarding.py:51-102` defines
  `OriginClient.register_host(access_token, host_id,
  capability_visibility) -> None`; its local `_host_id()` is `host-{uuid}`.
  The protocol cannot request a challenge, provide device proof, or return a
  server principal ID/generation.
- PR #1736 authorization currently sends no RFC 8707 `resource` and its
  `audience="tinyassets-desktop"` test value is not a production resource
  indicator.
- Current WorkOS env names are `WORKOS_AUTHKIT_DOMAIN`,
  `WORKOS_MCP_RESOURCE`, `WORKOS_ALLOW_NO_AUDIENCE`, and
  `WORKOS_REQUIRE_AUTH` in `tinyassets/auth/workos_provider.py:88-121`.
  `from_env()` hard-wires the MCP audience, middleware caches one global
  provider, and the current global `Identity` does not retain verified audience
  or authentication time. The MCP resource/provider cannot be repurposed.
- Draft #1746 consumes a verified host principal but owns provider-secret
  namespace, local pending index, commit-token enrollment, reconciliation,
  rotation, and deletion.

## Exact ownership boundary

`bind-host-principal-to-account` specifies only:

1. a route-local WorkOS validator with mandatory
   `WORKOS_HOST_BINDING_RESOURCE`, a typed host-binding request context, and
   `(issuer, sub)` as sole ownership;
2. pinned Ed25519/RFC 8037, RFC 8785 `HostProofV1`, one-use replay state,
   bounded private self-inventory, and exact lifecycle operations;
3. opaque stable principal storage, generation, retention, export/deletion,
   rotation, recovery, renewal, and terminal behavior;
4. current-generation linkage from insert-always host-pool sessions;
5. exact-tuple consumer evidence that grants no downstream authority.

It does not own:

- PR #1736 desktop files, PKCE/token custody, or native-store policy. That
  owner must adapt `OAuthConfig`, RFC 8707 authorization/token/refresh,
  `OriginClient`, onboarding state, native device-key use, and the
  principal-bearing response.
- PR #1746 provider secrets/references or #1691 provider assignment state.
- host-pool scheduling/economics, distributed execution, market authority, an
  MCP tool, or a chatbot secret-deposit path.

## Frozen pre-RED choices

- Owner is verified `(issuer, sub)`; validated `org_id` is non-authoritative
  metadata, so organization membership changes cannot transfer a principal.
- A dedicated audience and recent scoped step-up are mandatory. The
  host-binding route fails closed if its resource is absent or no-audience mode
  is enabled. The host-binding audience must be the sole `aud`; MCP-only,
  MCP+host, or any extra audience is rejected. Step-up uses interactive WorkOS
  `auth_time`, never refresh-minted access-token `iat`.
  Personal-account and organization scope provisioning must be proven before
  writers enable.
- V1 is Ed25519, RFC 8037 public JWK, RFC 7638 client-visible thumbprint, RFC
  8785 I-JSON, exact base64url lengths, and domain-separated `HostProofV1`.
  The server returns exact signing bytes; body digest covers only the typed
  operation intent, excluding the proof wrapper.
- Nonces are 32 CSPRNG bytes, one-use, five-minute TTL, subject/rate bounded.
  Response-loss retry uses a fresh proof plus a 32-byte body-bound idempotency
  scope; exact nonce replay always fails.
- A closed route/DTO/scope matrix separates enrollment challenges,
  post-enrollment nonces, inventory, lifecycle, and host-session operations.
  Rotation carries role-bound current/new signatures; every durable mutation
  has exact idempotency/results; authenticated session deregistration is exact
  and retry-safe. Heartbeat is the sole naturally monotonic liveness-only
  exemption. Atomic recovery cannot revoke the old host without committing the
  proven replacement.
- Principals expire after 90 days and renew only in the final 30 days.
  Rotation proves old and new keys; lost-key recovery is step-up revoke plus
  new enrollment. Terminal IDs/keys never reactivate.
- Private self-inventory is subject-derived, step-up, cursor-bounded
  (25 default/100 maximum), and management-field-only. It is not device or
  consumer authority.
- Every authenticated session and authority consumer checks exact
  `host_principal_generation`; #1746 separately checks provider-assignment
  generation.
- A disclosed owner-free 365-day key tombstone reconciles anti-reuse with
  account deletion; old identifiers never reactivate.
- Retention, account export/deletion, log-HMAC pseudonyms, reader-first
  rollout, mixed-version rollback, and the numeric three-instance
  `docs/design-notes/2026-04-18-full-platform-architecture.md` §14 proof are
  specified before RED work.

## Review history

Current-main Opus 5 reviews and independent Codex/spec-quality reviews returned
**ADAPT** before the final exact review. Their required changes included the #1736 protocol adaptation,
dedicated audience, stable owner axis, explicit proof/idempotency envelope,
rotation/recovery/expiry, generation propagation, private inventory, privacy
lifecycle, a normative wire/scope matrix, atomic recovery, separate nonce
limits, reproducible load traffic, exact `auth_time`, sole-audience rejection,
rollback, restoration of the unrelated `workflow-voice` concern, and
preservation of host Capacity/context steering. Those corrections are folded
into the candidate artifact.

Final exact review returned **APPROVE — spec/review-only** from Claude Opus 5
and three independent Codex reviewers at substantive artifact head
`5905cc41` over current reviewed base `6cde7ef0`. Evidence was clean range
`git diff --check`, strict target validity, all-item strict OpenSpec 42/42,
canonical host-pool `updated_at` liveness, exact 60-line STATUS, and no runtime
or canonical-spec files. Main then advanced by `92d730bc`, a STATUS-only
coordination commit; it was merged without changing the approved OpenSpec or
audit content. Approval does not authorize runtime, sync/archive, deployment,
or rollout.

Runtime remains blocked until PR #1736, identity/auth, daemon/host-pool, and
draft #1746 owners accept the split; Opus 5 and latest Codex approve the same
exact artifact; runtime files are freshly claimed; RED tests exist; and the
named load proof passes. Canonical spec sync/archive and deployment are not
authorized by this planning lane.
