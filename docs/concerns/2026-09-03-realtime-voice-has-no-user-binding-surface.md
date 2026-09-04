# Realtime voice has no user-owned binding surface

**Filed:** 2026-09-03
**Verified:** 2026-09-03 on production source `b4662ab6`
**Severity:** P2
**Surface:** first-class in-app Voice unlock and live proof

## Finding

The shared app can deposit a generic outbound HTTP connection and receive its non-secret
`connection_id` and `grant_id`. The Voice runtime will become ready only when the authenticated
founder's home universe also contains a bounded, non-symlinked `voice-connection.json` naming
those exact records, an HTTPS session endpoint, and schema `tinyassets.voice.v1`.

No authenticated app or MCP action creates, updates, or removes that binding. Repository search
finds writes only in `tests/test_realtime_voice.py`; production code only reads the file in
`tinyassets/onboarding/realtime_voice.py`. Reaching `ready` therefore still requires direct host
filesystem access even when the user has already connected a compatible provider. That is not a
first-class user unlock path and cannot serve as live acceptance evidence.

## Safety boundary that is already correct

`GET /mcp/app/voice/status` resolves only the signed-in founder's home. Readiness requires the
same owner, universe, connection, active grant, HTTP type, POST scope, and exact endpoint
allowlist. Session creation goes through the credential-blind exact-scoped proxy. Host CLI auth,
platform API keys, maintainer credentials, and another founder's connection cannot satisfy this
check. The two Voice-specific gates remain off in production. Generic outbound HTTP is already on
for unrelated effectors, but it cannot unlock Voice by itself; users without an exact binding stay
locked when the Voice gates are later enabled.

## Resolution

Specify and implement the smallest authenticated binding operation that lets a founder select one
of their own existing compatible HTTP connections/grants for their home universe, validates the
`tinyassets.voice.v1` endpoint contract without exposing its credential, and supports revocation.
Because this adds a public authority-bearing API/MCP surface, it requires an OpenSpec proposal and
opposite-provider review before implementation. Then run the bounded device proof in
`docs/ops/realtime-voice-mobile-handoff.md` using an already user-connected bridge. Do not add a
platform credential, shared billing fallback, or host-written acceptance fixture.
