## Why

Founder, 2026-10-02: "build the connect screen with the $10 prompt and make sure
its clear to the user that its to extend their openrouter daily limit or that
they could connect another llm", and earlier "command centers should fast
connect to as much free compute as possible ... through oauth".

OpenRouter's free tier is 50 requests a day per account. One long build turn is
20-60 requests, so a $0 user hits the wall after one or two turns, and today the
only ways past it are pasting a key or a subscription. Hugging Face is the one
other free source with an app-facing OAuth consent that yields the user's own
token (`inference-api` scope, OpenAI-compatible `router.huggingface.co/v1`).
Research: `ta-scratch-lead/free-llm-research.md` section 6 (2026-10-01).

## What Changes

- A Hugging Face model source the owner connects by signing in (2 clicks), as a
  backup source next to OpenRouter.
- One connect screen ("Connect free AI"): OpenRouter one-click (pre-selected),
  Hugging Face sign-in, the ChatGPT subscription sign-in, and a collapsed
  "Paste a key" with each provider's terms caveat inline.
- A daily-cap card when OpenRouter's free daily requests run out: honest copy
  that $10 credit on the user's OWN OpenRouter account raises OpenRouter's daily
  limit to 1,000, or connect another AI, or wait until tomorrow.

## Capabilities

### Modified Capabilities
- `free-source-pooling`: a sign-in source card, and the daily-cap card.

## Impact

`tinyassets/providers/free_source_presets.json` (one entry), the app sign-in
ingress (`tinyassets/onboarding/model_connect.py`, one operation), a public
client-metadata document route, `app.html`. No new storage table, vault
encoding, grant kind or router branch: the source composes the existing
`connect` ask, generic OAuth flow and oauth2 vault bundle.

Owner: Claude Code (connect-screen lane). Branch: feat/connect-free-ai. One PR.
