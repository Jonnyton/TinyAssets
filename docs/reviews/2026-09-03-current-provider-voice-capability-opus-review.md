# Current-provider Voice capability — Claude Opus implementation review

Date: 2026-09-03 (America/Los_Angeles)
Change: `openspec/changes/negotiate-user-owned-voice-capability/`
PR: #2841
Reviewer: Claude Opus through the repository `peer-agents` harness, read-only

## Review record

The review covered the complete change from base
`cdda89df47653d21ac35f957290cc0aa7593269d` through implementation head
`0b58f081fb98a0fbbf756123a7a2e681e24854a1`. The brief required inspection of
provider/connection/grant derivation, credential custody and rotation, storage deletion and
re-provisioning, endpoint/method scope, public routing, browser disclosure and microphone timing,
session revocation, secret exposure, and tests. It explicitly prohibited sub-agent dispatch,
writes, and a full test sweep.

The bounded implementation rounds returned:

1. `ADAPT`: reconnect could clear the authority poll and reacquire the microphone before a fresh
   status check. Fixed by preflighting every reconnect and testing zero connection/media requests
   after revocation.
2. `ADAPT`: an unpowered session could escape as an internal error, and the authority timeout did
   not include token refresh. Fixed with stable `provider_not_configured`/409 mapping and an
   end-to-end five-second deadline that suppresses a late fetch.
3. `APPROVE`: the reviewer verified both fixes and returned the exact trailing verdict
   `VERDICT: APPROVE`.

The third review also noted two remaining race windows: capability identity could change while the
disclosure was open, and a slow initial handshake could hold capture before periodic authority
checks began. The repository's three-round cap forbids a fourth review. Both observations were
nonetheless resolved before publication: disclosure acceptance now performs a fresh bounded status
check before persisting consent or starting, and authority polling begins immediately after media
capture is acquired. The deterministic browser harness covers the changed-disclosure refusal,
fresh-disclosure retry, reconnect refusal, and end-to-end timeout. The subsequent merge from current
`main`, OpenSpec whitespace normalization, and brand-manifest regeneration do not broaden Voice
authority or enable either production gate.

## Verification supplied with the candidate

- Focused capability, serving-authority, Voice server/browser, connection-removal, and outbound HTTP
  matrix: 199 passed on Windows, Python 3.14, 2026-09-03.
- Ruff: clean on changed Python and tests.
- OpenSpec: strict validation passed.
- Packaged runtime: build import probe passed; 393 canonical files mirror-matched.
- Voice remains gated by `TINYASSETS_REALTIME_VOICE_ENABLED` and
  `TINYASSETS_ALLOW_REALTIME_VOICE_API`; neither is enabled by this change.

Final independent verdict: **APPROVE**.
