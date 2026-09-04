## Context

The shipped dark Voice slice already has the correct media boundary: browser WebRTC talks to a provider-neutral `tinyassets.voice.v1` bridge through an authenticated same-origin SDP broker; the bridge can call only canonical `converse`; TinyAssets stores text, not audio; and all credentials remain inside the exact-scoped outbound worker. Its missing product boundary is capability selection. Today `realtime_voice.py` reads a host-written `voice-connection.json`, while provider definitions describe only the primary text executor and the connection ledger has no auxiliary-capability metadata.

Jonathan's live acceptance result on 2026-09-04 is authoritative: if he can chat with his universe, he must be able to speak with that same universe without redundant account setup. The current implementation violated that rule by treating a provider-native realtime bridge as the only speech transport. One Voice control stays beside the composer. The current provider remains the sole writer through `converse`; browser/device speech may supply transcription and synthesis, while a declared realtime bridge remains an optional richer transport.

## Goals / Non-Goals

**Goals:**

- Represent auxiliary provider capabilities as bounded, non-secret metadata attached to an existing user-owned connection.
- Let an authenticated owner declare or revoke a capability only for the connection/grant currently powering their home universe.
- Resolve Voice readiness from the current serving provider and live grant on every status/session request.
- Make the composer Voice control one-tap when ready and reuse existing connection/request UI when not ready.
- Preserve the existing credential-blind broker, exact endpoint/method scope, writer routing, disclosure, and generic outbound transport gate.
- Let a supported browser/device speech service wrap the already-working canonical text turn without requiring a provider-native realtime entitlement.

**Non-Goals:**

- Creating a Voice-specific credential, account, billing path, provider SDK, platform-funded fallback, or claiming that a ChatGPT subscription grants external Realtime API access.
- Guessing capability from a provider brand, model name, URL substring, or ambient host credential.
- Automatically selecting a different provider or connection from the one currently serving the universe.
- Publishing a store release or claiming live acceptance before Jonathan's bounded test.
- Background audio, raw-audio persistence, wake words, or changes to the canonical `converse` writer.

## Decisions

### 1. Capability metadata belongs to the existing connection ledger

Add a `connection_capabilities` table keyed by `(connection_id, capability_kind)`, with a foreign key to `outbound_connections(connection_id)`. The first supported kind is `realtime_voice`, whose value is a canonical bounded document:

```json
{
  "protocol": "tinyassets.voice.v1",
  "session_url": "https://bridge.example/session",
  "service_name": "Example Voice",
  "privacy_url": "https://bridge.example/privacy"
}
```

The row contains no credential reference, bearer, model choice, or billing authority. The connection continues to own credential custody and endpoint/method scope; the universe grant continues to own use authority. Declaring a capability cannot add an endpoint, add `POST`, mint a grant, or change a serving binding. `ConnectionLedger.delete_connection` deletes capability rows inside the same transaction before deleting the connection so a deterministic connection id cannot resurrect an old capability if the destination is later re-provisioned.

This replaces `voice-connection.json` rather than retaining a compatibility read. Voice is dark and has no accepted live user data, so carrying two sources would create ambiguous authority and violate the fail-loud boundary.

Alternatives rejected:

- A second Voice credential store duplicates custody and invites platform-key fallback.
- Extending immutable provider-definition identity with mutable endpoint metadata makes capability revocation require rebinding the writer.
- Inferring support from provider names or URLs silently grants behavior the user did not declare.

### 2. One authenticated generic operation declares or revokes a capability

Add `write_graph(target="connection", operation="configure_provider_capability")`. The payload contains only capability kind, descriptor, and `enabled`; it cannot select a universe, provider, connection, or grant. The operation derives the authenticated actor and founder home through the same resolver used by Voice status/session, refuses a caller `graph_id` that does not exactly match that home, requires both a current admin ACL and exact `grant.owner_user_id` ownership, resolves the current serving binding, and proves that its open provider definition references the same grant and connection before any mutation.

Enabling validates exact schema, HTTPS URLs, bounded text, no userinfo/fragment, and that `session_url` is already allowed for `POST` by the connection. Disabling deletes only that non-secret capability row. Calls are idempotent. The operation returns a secret-free status and never returns connection credentials.

The existing connection form/request rail invokes this operation after the user has already deposited or extended their provider connection. It is capability negotiation on existing authority, not a Voice credential form.

### 3. Voice resolution follows the current serving provider; it never searches for substitutes

`voice_capability()` resolves exactly one current founder serving binding. For an `api_key_http` provider it loads the provider definition's grant, resolves that grant to its redacted connection, and reads the connection's `realtime_voice` capability. It reuses `_current_serving_authority` and `verify_open_grant_custody` rather than reimplementing serving authority, including the credential-reference rotation digest, then additionally checks exact owner, universe, HTTP type, `POST`, protocol, capability row, and endpoint allowlist. Once those checks pass, that user-owned capability is the Voice readiness authority; legacy Voice-specific host flags cannot override it. The existing generic outbound HTTP switch remains the operational transport kill switch.

Current subscription-CLI providers advertise no realtime capability because their subscription interfaces expose no documented provider-neutral SDP bridge. This says nothing about their ability to answer the existing canonical text turn. A future adapter may expose the generic descriptor only from the user's own authenticated provider resource.

The resolver does not enumerate other connections and does not pick a fallback. If a different user-owned connection could support Voice, the user must explicitly make it the current authorized provider through the existing connection/serving path before it is eligible.

### 4. The single composer control owns four honest outcomes

The existing `btn-voice` remains the only Voice entry point:

- `ready`: one tap proceeds directly to the existing disclosure (if needed) and microphone/session start.
- `unpowered`: the app opens/focuses the existing synthesized provider request; no Voice-specific setup dialog is shown.
- `provider_voice_unsupported`, `capability_not_declared`, bridge-disabled, or invalid bridge authority: when browser speech input and synthesis exist, the app offers browser speech around canonical `converse` and does not open provider setup.
- no browser speech input and no ready bridge: the app names the browser/device limitation and keeps typed conversation available.

The old Voice unlock modal is removed. No path requests microphone permission before a transport-specific disclosure is accepted.

The remediation affordance only opens or focuses the existing connection/request surface. It never pre-fills or auto-submits an endpoint extension derived from capability metadata; any `extend_http` mutation remains a separate explicit user-authorized action.

### 5. Browser speech wraps canonical conversation when no bridge exists

When `SpeechRecognition` (including the WebKit-prefixed implementation),
`speechSynthesis`, and `SpeechSynthesisUtterance` are present, the app can run a
bounded foreground turn without `/voice/session`: recognition produces one
final text utterance, `sendVoiceTurn` submits it once through the same
authenticated `MCP.converse` path used by typed chat, and synthesis receives the
exact returned reply after that text is rendered in history. Stop, page hide,
sign-out, errors, and navigation abort recognition and cancel queued speech.

This mode is turn-based, not full-duplex realtime: it does not promise semantic
VAD, barge-in, or bridge-quality interruption. Speech recognition is not
available in every browser and may use a remote service chosen by the browser or
device, so the disclosure names that possibility and TinyAssets does not claim
local processing. No raw audio crosses a TinyAssets route or enters TinyAssets
storage. If these browser APIs are absent, the app reports the device limitation
instead of asking for another provider account.

### 6. Session creation repeats every authority and capability check

Status is advisory. `POST /mcp/app/voice/session` resolves the current serving provider and capability again immediately before creating its exact-scoped proxy. A provider rebind, grant/connection revocation, capability deletion, endpoint-scope change, credential-reference rotation, ownership mismatch, or ACL loss therefore fails before the SDP leaves TinyAssets.

The browser still supplies only `offer_sdp`; it cannot choose a universe, provider, connection, grant, endpoint, protocol, model, or credential.

While Voice is active, the client polls the authenticated status route every five seconds with a five-second request deadline. Any non-ready response, identity failure, timeout, or network error immediately stops every local microphone track and closes the peer connection. This bounds continued capture after capability deletion, grant/connection revocation, provider rebind, credential rotation, or ACL loss to ten seconds. Each ready response also carries a disclosure identity derived from connection id, protocol, session URL, service name, and privacy URL, so changing the bridge or protocol requires fresh disclosure acceptance.

## Risks / Trade-offs

- [Existing API-key provider lacks a declared Voice capability] → Report `capability_not_declared` and route to the existing connection/request surface; do not infer or probe with the credential.
- [A provider powers text but its credential plan does not include realtime] → The bridge may refuse at session time; preserve the existing secret-free provider error and leave typed chat available.
- [Capability metadata outlives endpoint or grant authority] → Delete it transactionally with the connection, revalidate live custody and exact endpoint on every status/session call, and stop active capture within the bounded status-poll window.
- [Two tabs configure the same capability] → Use a transaction and idempotent upsert/delete keyed by connection and kind; last complete authenticated declaration wins without changing credential scope.
- [The current provider is a subscription CLI] → Keep it as the canonical writer. Use disclosed browser/device speech when available; never infer external Realtime API entitlement or fall back to platform API usage.
- [Browser recognition is absent or remotely processed] → Capability-detect it, disclose that the browser/device may send audio to its own recognition service, and report an honest device limitation when unavailable.

## Migration Plan

1. Add the ledger table and fail-closed capability APIs; existing connections have no capability rows and remain valid for their existing purposes. Extend connection deletion to remove capability rows in the same transaction.
2. Replace the file-based Voice resolver and tests with current-serving-provider capability resolution.
3. Update the shared app state machine and remove the separate unlock modal.
4. Retire the redundant Voice-specific host flags. Run focused tests, required CI, authenticated public canary, and rendered browser proof that an exact compatible capability reaches ready while capability gaps reuse the existing connection path. The generic outbound HTTP gate remains fail-closed.
5. After the signed-in app renders browser speech ready for the already-working current provider, stop before microphone permission for Jonathan's explicit bounded live test.

Rollback disables generic outbound HTTP or reverts the code. The additive capability table may remain unused; removing a capability row or reverting the resolver leaves no credential or broader authority behind.

## Open Questions

- Which shipped browser and WebView combinations expose reliable speech recognition? This is runtime capability-detected; it must not become a claim that every browser can provide speech input.
