## Why

Merged PR #1736 gives the packaged-tray lane a real client-side `OriginClient`
protocol and native account-token custody, but TinyAssets has no authenticated
production route that binds the verified platform account to a stable host
principal.
The two identifiers available today are unsuitable: the host-pool API accepts
a caller-supplied owner and intentionally inserts a new session row on every
registration, while the tray's local `host-{uuid}` value is self-asserted.

That gap blocks trustworthy BYOC/provider custody, paid-market host authority,
and one-click host onboarding. A requester-controlled executor cannot safely
publish a provider binding or advertise capacity if the control plane cannot
prove which verified account owns the stable host.

## What Changes

- Add an authenticated account-to-host-principal contract that derives its
  owner only from the validated WorkOS issuer, dedicated host-binding
  audience, and required WorkOS `sub`. A validated `org_id` is metadata, not
  an ownership or uniqueness axis.
- Bind one opaque stable server-issued `host_principal_id` to one subject and
  one proof-of-possession device key. Never treat caller-supplied owner fields,
  tray-local UUIDs, or insert-always host-pool rows as that principal.
- Use one-use, short-lived, audience/method/path/body-bound challenges,
  Ed25519, RFC 8785 canonical JSON, and a versioned `HostProofV1` envelope for
  initial binding and subsequent proof of possession.
- Freeze a closed v1 operation/scope/wire matrix so the independently owned
  tray and server sign the same typed intents without sharing private
  serializers.
- Make same-account/same-device retries idempotent and make a second device a
  distinct host principal; preserve explicit revocation, generation, expiry,
  key rotation, and atomic lost-key replacement semantics.
- Keep host-pool rows as ephemeral capability/availability sessions. They may
  reference the stable principal, but repeated registration still creates
  distinct session rows and exact deregistration still deletes only one row.
- Expose narrow subject-scoped self-inventory, exact read/revoke/rotate
  operations, and exact-tuple internal reads for authorized control-plane
  consumers such as provider-custody reconciliation.
- Keep account refresh-token storage, native backend policy, subject-pinned
  `bound`-not-`online` state, and the client-side `OriginClient` implementation
  in the packaged-tray owner established by merged #1736. That owner must adapt
  that protocol and onboarding state to request challenges, sign exact
  envelopes, and receive `host_principal_id` plus generation; this change
  defines the server contract and does not claim its desktop files.
- Keep provider-secret namespace, enrollment, reconciliation, rotation, and
  deletion in draft PR #1746; this change carries no provider secret or
  credential-binding reference.
- Add no MCP tool or action. This is an origin authentication/identity
  primitive used by the existing tray and host protocols.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `identity-auth-and-access-control`: Derive host ownership from the verified
  account identity and define replay-safe device proof, revocation, rotation,
  and non-enumerating reads.
- `daemon-identity-and-host-pool`: Introduce a stable account-bound host
  principal distinct from the existing insert-always host session rows.

## Impact

This lane is specification/review-only. The active packaged-tray target owns
the local subject pin, loopback safety, provider-free binding, and
`bound`-not-`online` contract; this change consumes that client boundary rather
than creating a third identity capability. Future implementation is expected to
touch a narrow authenticated origin module under `tinyassets/api/` or
`tinyassets/auth/`, host-principal storage/migrations, the host-pool
registration adapter, packaged mirrors, and focused identity/concurrency
tests. Exact runtime files must be re-claimed after the merged #1736 owner and active
identity/host-pool owners accept the split.

Dependencies are merged #1736's `OriginClient`/desktop owner accepting the
protocol adaptation, a WorkOS native/public client and exact loopback redirect
configuration, a dedicated `WORKOS_HOST_BINDING_RESOURCE` plus
step-up/scoped WorkOS token contract, draft PR #1746's custody consumer, and
the current host-pool session contract. This change grants no provider,
credential, compute, market, lease, settlement, payment, universe, or
maintainer/founder authority.
