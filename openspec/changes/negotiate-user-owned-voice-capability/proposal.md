## Why

The dark Voice client can start only from a host-written `voice-connection.json`, so a signed-in user cannot unlock Voice through the product even when their universe already runs on a user-authorized provider. Voice must instead discover a provider-neutral realtime capability on the authority the user already granted, start from the composer in one tap when it is present, and fail visibly without platform credentials or fallback when it is not.

## What Changes

- Extend the existing user-owned HTTP connection/provider metadata with a bounded, non-secret auxiliary capability declaration for `tinyassets.voice.v1`; the declaration never carries a credential and cannot widen the connection's endpoint or method grant.
- Resolve Voice from the authenticated founder's current serving provider and its current universe grant. Remove runtime dependence on a host-written voice binding file.
- Keep the single Voice control beside the composer. A tap starts immediately when the current provider advertises an authorized realtime capability; it never opens a second credential flow.
- When no provider powers the universe, route the user to the existing unpowered-universe provider request. When the current provider lacks realtime support, report that exact capability gap and either offer the existing user-authorized connection/request path or remain unavailable.
- Preserve the provider-neutral WebRTC bridge, canonical `converse` writer, disclosure, teardown, exact capability checks, and generic outbound transport gate. Never substitute a platform/shared credential, platform-paid usage, anonymous access, or a different provider.

## Capabilities

### New Capabilities

- `provider-capability-negotiation`: Declares, validates, discovers, and revokes non-secret auxiliary capabilities on an existing user-owned provider connection without creating credential authority.

### Modified Capabilities

- `realtime-voice-conversation`: Resolves Voice from the current provider's negotiated capability and defines the one-control ready, unpowered, incompatible, and unavailable states.
- `credential-vault`: Stores only capability metadata beside an existing connection and proves that it cannot widen the underlying credential grant or expose credential material.
- `identity-auth-and-access-control`: Requires the capability declaration and resolution paths to derive the founder's home universe and current serving provider from the authenticated subject.
- `provider-routing`: Makes auxiliary capability discovery explicit while preserving the selected primary writer and forbidding implicit provider fallback.

## Impact

- The connection ledger gains a durable auxiliary-capability table and migration; existing public connection payloads and redacted connection views remain unchanged.
- `tinyassets/onboarding/realtime_voice.py` resolves the current serving provider's existing grant rather than a filesystem manifest.
- The shared `/mcp/app` Voice control and pending-request integration gain provider-capability states without a new credential form.
- Focused storage, authority, route, browser-state, and regression tests are required. A validated user-owned capability becomes ready in production after independent review and deployment; microphone acceptance remains an explicit user action.
