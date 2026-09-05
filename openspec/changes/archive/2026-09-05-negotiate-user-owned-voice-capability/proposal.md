## Why

The Voice client still treats an external realtime-audio bridge as a prerequisite even when the signed-in user's universe already chats through its connected provider. The live result is a redundant Connect prompt and an unsupported-connection message. Typed conversation already supplies the correct writer and canonical transcript; Voice must let a supported browser/device provide speech input and output around that same `converse` path, while retaining an authorized realtime bridge as an optional richer transport.

## What Changes

- Extend the existing user-owned HTTP connection/provider metadata with a bounded, non-secret auxiliary capability declaration for `tinyassets.voice.v1`; the declaration never carries a credential and cannot widen the connection's endpoint or method grant.
- Resolve Voice from the authenticated founder's current serving provider and its current universe grant. Remove runtime dependence on a host-written voice binding file.
- Keep the single Voice control beside the composer. A tap starts with the current provider's authorized realtime capability when present; otherwise a supported browser/device speech service transcribes one utterance into the existing `converse` call and reads its exact reply aloud.
- When no provider powers the universe, route the user to the existing unpowered-universe provider request. When typed conversation works but no realtime bridge exists, never ask for another provider connection. Report only a real browser/device speech limitation when speech input is unavailable.
- Preserve the provider-neutral WebRTC bridge, canonical `converse` writer, disclosure, teardown, exact capability checks, and generic outbound transport gate. Browser speech requires its own disclosure because recognition may use a browser-vendor service. Never substitute a platform/shared credential, platform-paid usage, anonymous access, or a different provider.

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
