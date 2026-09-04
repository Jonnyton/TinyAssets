# Realtime voice mobile handoff

Date: 2026-09-03
Owner track: `codex/ios-store-release`
Source changes:
`openspec/changes/archive/2026-09-04-add-realtime-voice-conversation/` and
`openspec/changes/negotiate-user-owned-voice-capability/`

The shared `/mcp/app` client contains a dark, foreground-only Realtime Voice slice. Voice is one
composer control and a capability of the universe's current serving provider. It does not select a
second provider and does not ask for a second Voice credential. The native release track owns the
packaging and store declarations below. This change does not alter signing, enrollment,
publication, production flags, or native release ownership.

Readiness is stored as a non-secret `tinyassets.voice.v1` capability on the exact generic HTTP
connection and grant already used by the signed-in founder's current serving provider. The
authenticated `write_graph target=connection operation=configure_provider_capability` operation
derives those records; callers cannot name another connection or grant. Its HTTPS session URL must
already be in that connection's exact `POST` allowlist. Revoking the grant, deleting the connection,
rotating its credential authority, changing the serving provider, or revoking the capability closes
Voice on the next status/session check.

The browser sends a bounded SDP offer only to the authenticated same-origin session route. The
bridge response contains only `protocol`, `answer_sdp`, `expires_at`, and `max_session_seconds`; no
long-lived credential or arbitrary remote URL reaches browser JavaScript. During a live session the
client rechecks current authority every five seconds with a five-second timeout and tears down all
local audio tracks when readiness or disclosure identity changes. Server-side session creation also
re-resolves authority immediately before proxying.

The single control behaves as follows:

- `ready`: start after the current disclosure is accepted; only then request microphone access.
- `unpowered`: open the existing provider request/setup flow.
- `incompatible` with a safe remediation: focus the existing connection/request surface without
  prefilling or submitting an endpoint extension.
- `incompatible` without a remediation, or `disabled`: report unavailable and never request the
  microphone.

No host-written file, platform credential, maintainer account, another user's connection,
platform-paid usage, anonymous access, or silent fallback can unlock Voice or count as acceptance
evidence.

## iOS

- Add `NSMicrophoneUsageDescription` before any device proof. Recommended copy: **“TinyAssets uses
  the microphone only while voice conversation is active so you can speak with your universe.”**
- Stop voice and release every audio track when the app resigns active or enters the background.
- In App Store privacy answers, re-evaluate **Audio Data** and **Other User Content** against the
  shipped provider-retention configuration. The canonical founder utterance and universe reply are
  text history; TinyAssets does not persist raw audio.

## Android

- Declare `android.permission.RECORD_AUDIO` and request the dangerous runtime permission only after
  the in-app voice disclosure is accepted.
- In the WebView permission callback, verify the requesting origin is exactly
  `https://tinyassets.io`, grant only `PermissionRequest.RESOURCE_AUDIO_CAPTURE`, and deny every
  other requested resource. A platform permission grant alone must not become a general WebView
  media grant.
- Stop voice and release every audio track on pause/background.
- In Google Play Data safety, account for audio transmitted off-device to the user-selected service
  under **Voice or sound recordings**, and for the stored canonical text under the applicable
  user-content category. Final collected/shared and ephemeral-processing answers must reflect the
  actual provider agreement and retention controls used for release.

## Coordinated acceptance

Keep both Voice-specific production gates off. First prove the single composer control's
`disabled`, `unpowered`, and `incompatible` states in the rendered app without any microphone or
bridge request. Then identify an already-authorized current provider with a compatible bridge. Stop
for Jonathan at the rendered `ready` state and obtain his explicit authorization before beginning
the bounded live microphone proof. If no eligible current provider exists, record that as the host
action; do not create a second credential path or enable Voice merely to finish the change.

### Evidence packet and run order

Record the pull-request head SHA, app build identifier, device model, OS version, test-universe id,
current serving provider kind, bound resource kind (never its secret), UTC start/end, and operator.
Screenshots must exclude tokens and OS account identifiers; network evidence records only origin,
path, status, and timing.

1. **Closed-state proof.** Render `disabled`, `unpowered`, remediable `incompatible`, and
   unremediable `incompatible`. Confirm the one Voice control either focuses the existing setup
   surface or reports unavailable as specified. Confirm no disclosure, microphone prompt,
   `/voice/session`, or external Voice endpoint request occurs. Send one typed turn and confirm the
   current serving provider still answers through canonical `converse`.
2. **Current-provider authority proof.** Using the public authenticated operation, configure only an
   already-connected `tinyassets.voice.v1` bridge on the universe's current HTTP serving provider.
   Confirm the response is secret-free and status becomes `ready`. Attempt another connection,
   grant, owner, universe, method, or endpoint and confirm refusal. Do not manually write storage.
3. **Founder stop and consent.** Show Jonathan the rendered `ready` state and disclosure version 3,
   naming the selected service. Stop. Continue only after he explicitly authorizes this bounded
   proof. Declining the disclosure must cause no session or audio request.
4. **Physical lifecycle proof.** After authorization, grant microphone access and complete one
   short turn. Compare visible and stored assistant text byte-for-byte with canonical `converse`.
   Interrupt once; background and foreground once; disconnect and recover once; deny and later
   grant permission once; and exhaust reconnect once under controlled network loss. At every stop
   boundary verify the native capture indicator ends, all local tracks are released, no turn is
   submitted twice, and typed chat remains usable.
5. **Custody and revocation proof.** Confirm status/session responses are `no-store`, contain no
   long-lived secret, and resolve only the authenticated home universe. Confirm storage contains
   only canonical founder/universe text—no microphone bytes, partial transcripts, or bridge audio
   events. Revoke the capability, grant, connection, or current serving binding and confirm Voice
   closes within ten seconds without changing providers or falling back.
6. **Post-run safety proof.** Leave both Voice-specific gates off, repeat the authenticated public
   MCP canary, and record that production flags, signing, store submissions, billing configuration,
   and release state were not changed by the acceptance run.

Stop immediately on cross-universe readiness, ambient/platform credential use, microphone access
before readiness and disclosure, non-canonical visible reply, duplicate `converse`, capture that
continues after a lifecycle stop, or secret-bearing output. Preserve the evidence, keep all gates
off, and return the change to implementation review.
