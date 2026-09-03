# Realtime voice mobile handoff

Date: 2026-09-03
Owner track: `codex/ios-store-release`
Source change: `openspec/changes/add-realtime-voice-conversation/`

The shared `/mcp/app` client now contains a dark, foreground-only Realtime voice slice. The native
release track owns the following packaging and store declarations. This branch deliberately does
not change signing, enrollment, publication, or native release ownership.

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
- In Google Play Data safety, account for audio transmitted off-device to OpenAI under **Voice or
  sound recordings**, and for the stored canonical text under the applicable user-content category.
  The final collected/shared and ephemeral-processing answers must reflect the actual provider
  agreement and retention controls used for release, not this implementation's lack of raw-audio
  storage alone.

## Coordinated acceptance

Before enabling either platform, first prove that Voice is visibly locked and requests no
microphone permission when the signed-in universe lacks a compatible user-owned voice resource.
Then, on a test universe that already has such a resource bound, prove on a physical device that
first-use disclosure precedes the OS permission prompt; deny and later retry work; headphones and
speaker paths work; barge-in stops the current reply; backgrounding ends capture; reconnect is
bounded; typed chat remains available after every voice failure; and a restored conversation
contains exactly the canonical text turns, never raw audio or a synthetic duplicate. Do not ask
Jonathan for a separate API key or spend ceiling merely to run this proof, do not use a shared
fallback, and do not publish as part of this proof.

### Evidence packet and run order

Record the pull-request head SHA, app build identifier, device model, OS version, test-universe id,
bound resource kind (never its secret), UTC start/end, and the operator for every run. Screenshots
must exclude tokens and OS account identifiers; network evidence records only origin, path, status,
and timing.

1. **Subscription-only authority proof.** Use a test universe powered by its own Codex subscription
   with no Realtime-compatible resource. Confirm `GET /mcp/app/voice/status` returns secret-free
   `locked` metadata. Tap `Voice · Connect`; confirm the capability dialog appears, the privacy
   disclosure does not, the OS microphone prompt does not, and neither `/voice/session` nor an
   OpenAI Realtime endpoint is contacted. Send one typed turn and record that the Codex writer still
   answers through canonical `converse`.
2. **Already-bound compatible-resource proof.** Only if a test user has independently chosen to
   bind a compatible voice resource to that universe, enable the two non-production adapter gates.
   Confirm status becomes `ready`, disclosure version 2 appears before the first OS microphone
   prompt, and declining causes no session or audio request. Then accept, grant microphone access,
   complete one short turn, and compare the visible/stored assistant text byte-for-byte with the
   `converse` result before accepting spoken playback as evidence.
3. **Lifecycle proof on each physical platform.** While speaking, interrupt once; background and
   foreground once; disconnect and recover once; deny and later grant permission once; and exhaust
   reconnect once in a controlled network-loss run. At each stop/error boundary verify the native
   audio-capture indicator ends, all local tracks are released, no turn is submitted twice, and
   typed chat remains usable.
4. **Custody and persistence proof.** Confirm status/session responses are `no-store`, contain no
   long-lived secret, and are scoped to the authenticated home universe. Confirm the conversation
   store contains only the canonical founder/universe text pair—no microphone bytes, partial
   transcripts, provider audio events, or temporary client secret. Remove or revoke the compatible
   resource and confirm the same universe returns to `locked` without changing its writer.
5. **Post-run safety proof.** Turn both non-production gates off, repeat the public MCP canary, and
   record that production flags, signing, store submissions, billing configuration, and deployment
   state were never changed by the acceptance run.

Stop immediately on any cross-universe readiness, ambient/platform credential use, microphone
prompt before ready/disclosure, non-canonical visible reply, duplicate `converse` call, audio that
continues after a lifecycle stop, or secret-bearing log/response. Preserve the failure evidence,
keep both gates off, and return the change to implementation review.
