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

Before enabling either platform, prove on a physical device that first-use disclosure precedes the
OS permission prompt; deny and later retry work; headphones and speaker paths work; barge-in stops
the current reply; backgrounding ends capture; reconnect is bounded; typed chat remains available
after every voice failure; and a restored conversation contains exactly the canonical text turns,
never raw audio or a synthetic duplicate. Use only a founder-approved user-owned API key and spend
ceiling. Do not publish as part of this proof.
