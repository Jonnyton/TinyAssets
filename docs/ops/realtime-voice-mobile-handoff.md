# Realtime voice mobile handoff

Date: 2026-09-03
Owner track: `codex/ios-store-release`
Source changes:
`openspec/changes/archive/2026-09-04-add-realtime-voice-conversation/` and
`openspec/changes/negotiate-user-owned-voice-capability/`

The shared `/mcp/app` client contains a dark, foreground-only Voice slice. Voice is one composer
control around the universe's existing canonical conversation. It does not select a second
provider, infer external Realtime API entitlement from a ChatGPT subscription, or ask for a second
Voice credential. The native release track owns the packaging and store declarations below. This
change does not alter signing, enrollment, publication, production flags, or native release
ownership.

Bridge readiness is stored as a non-secret `tinyassets.voice.v1` capability on the exact generic HTTP
connection and grant already used by the signed-in founder's current serving provider. The
authenticated `write_graph target=connection operation=configure_provider_capability` operation
derives those records; callers cannot name another connection or grant. Its HTTPS session URL must
already be in that connection's exact `POST` allowlist. Revoking the grant, deleting the connection,
rotating its credential authority, changing the serving provider, or revoking the capability closes
Voice on the next status/session check.

There are two speech transports. A compatible bridge sends a bounded SDP offer only to the
authenticated same-origin session route and retains the existing five-second authority checks.
Otherwise, a browser/device with speech recognition and synthesis captures one final transcript,
sends that text through canonical `converse`, and speaks the exact returned reply. TinyAssets does
not receive raw browser-speech audio. Depending on the browser, its vendor speech service may
process audio remotely and recognition may not work offline. Browsers without both required speech
surfaces report that device/browser limitation while typed chat remains available.

The single control behaves as follows:

- `ready`: start the available bridge or browser speech transport after its current disclosure is
  accepted; only then request microphone access.
- `unpowered`: open the existing provider request/setup flow.
- `incompatible` or bridge-disabled with browser speech available: keep the existing conversation
  writer and offer disclosed browser speech without a bridge session request.
- `incompatible` or bridge-disabled without browser speech: report the browser/device limitation
  and never route a working conversation back through provider setup.

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
- In Google Play Data safety, account for audio transmitted off-device to the selected bridge or
  browser/device speech service
  under **Voice or sound recordings**, and for the stored canonical text under the applicable
  user-content category. Final collected/shared and ephemeral-processing answers must reflect the
  actual provider agreement and retention controls used for release.

## Coordinated acceptance

Conversation readiness comes from the exact current provider that already answers canonical typed
chat. Speech readiness comes independently from either the exact provider's user-owned bridge or
the current browser/device speech surfaces; retired Voice-specific host flags are not acceptance
gates. Prove that an already-working subscription-backed conversation offers browser speech
without provider setup or `/voice/session`, and that an unsupported browser reports only its
device/browser limitation. Stop there for Jonathan and obtain his explicit authorization before
beginning the bounded live microphone proof. Do not create a second credential path, request a
platform key, infer Realtime API entitlement, or switch providers merely to finish the change.

### Evidence packet and run order

Record the pull-request head SHA, app build identifier, device model, OS version, test-universe id,
current serving provider kind, bound resource kind (never its secret), UTC start/end, and operator.
Screenshots must exclude tokens and OS account identifiers; network evidence records only origin,
path, status, and timing.

1. **Closed-state proof.** Render `unpowered`, bridge-incompatible with browser speech, and
   bridge-incompatible without browser speech. Confirm only `unpowered` opens provider setup. The
   browser-capable state must show the browser-speech disclosure with no microphone prompt or
   `/voice/session`; the browser-incapable state must name the device/browser limitation. Send one
   typed turn and confirm the current serving provider still answers through canonical `converse`.
2. **Canonical browser-speech proof.** With the subscription-backed current provider unchanged,
   inject one final recognition result and confirm exactly one canonical `converse` turn. Compare
   visible and synthesized reply text byte-for-byte, confirm raw audio never reaches TinyAssets,
   and confirm stop aborts recognition and cancels synthesis. Do not start a real microphone or
   send a live-universe turn in this automated proof.
3. **Optional bridge authority proof.** If testing the richer path, use the public authenticated
   operation to configure only an already-connected `tinyassets.voice.v1` bridge on the universe's
   current HTTP serving provider. Confirm the response is secret-free and status becomes `ready`.
   Attempt another connection, grant, owner, universe, method, or endpoint and confirm refusal. Do
   not manually write storage.
4. **Founder stop and consent.** Show Jonathan the rendered browser disclosure (or honest
   unsupported-browser state) on the exact signed-in path that failed. Stop. Continue only after he
   explicitly authorizes the bounded microphone proof. Declining disclosure must cause no session,
   recognition, or audio request.
5. **Physical lifecycle proof.** After authorization, grant microphone access and complete one
   short turn. Compare visible and stored assistant text byte-for-byte with canonical `converse`.
   Interrupt once; background and foreground once; disconnect and recover once; deny and later
   grant permission once; and exhaust reconnect once under controlled network loss. At every stop
   boundary verify the native capture indicator ends, all local tracks are released, no turn is
   submitted twice, and typed chat remains usable.
6. **Custody and revocation proof.** For the bridge path, confirm status/session responses are
   `no-store`, contain no long-lived secret, and resolve only the authenticated home universe.
   Confirm storage contains only canonical founder/universe text—no microphone bytes, partial
   transcripts, or bridge audio events. Revoke the capability, grant, connection, or current
   serving binding and confirm Voice closes within ten seconds without changing providers or
   falling back.
7. **Post-run safety proof.** Leave the retired Voice-specific flags absent, repeat the authenticated
   public MCP canary, and record that the generic outbound gate, signing, store submissions, billing
   configuration, and release state were not changed by the acceptance run.

Stop immediately on cross-universe readiness, ambient/platform credential use, microphone access
before readiness and disclosure, non-canonical visible reply, duplicate `converse`, capture that
continues after a lifecycle stop, or secret-bearing output. Preserve the evidence, keep all gates
off, and return the change to implementation review.
