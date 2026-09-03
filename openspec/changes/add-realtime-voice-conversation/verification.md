# Verification

Date: 2026-09-03
Environment: Windows local worktree, branch `codex/first-class-voice`
Production flags: unchanged/off
Paid Realtime calls: none

## Authority correction

Founder direction on 2026-09-03 established universe authority as the capability boundary. The
earlier proof plan incorrectly asked Jonathan to deposit a separate OpenAI API key and approve a
spend ceiling. That host action was removed. Official OpenAI documentation currently exposes API
credentials, not the existing ChatGPT/Codex subscription session, for Realtime calls; the branch
therefore treats that subscription-only universe as Voice-locked and never borrows a platform key.
Automated evidence below is being refreshed for the new capability preflight and locked-state UI.

## Automated evidence

- `python -m pytest -q tests/test_realtime_voice.py tests/test_onboarding_app.py`
  — **111 passed** after the authority correction. Coverage includes authenticated secret-free
  capability status, ambient-key refusal, a locked UI that opens only the connection explanation,
  and the existing exact-writer/audio lifecycle contract.
- `python -m pytest -q tests/test_mirror_parity_gate.py` — **15 passed** after rebuilding the
  packaged runtime mirror.
- `python -m ruff check tinyassets/onboarding/__init__.py tinyassets/onboarding/realtime_voice.py tests/test_onboarding_app.py tests/test_realtime_voice.py` — **all checks passed**.
- `python packaging/claude-plugin/build_plugin.py` — **391 runtime files staged; import probe passed**.
- `openspec validate add-realtime-voice-conversation --strict` — **valid**.
- `python scripts/openspec_flow.py check-change add-realtime-voice-conversation --provider codex`
  — **ALLOWED**, with the pre-existing global WIP count of four reported.
- `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp` — **exit 0** on
  2026-09-03. Production was not changed; this confirms the existing public MCP surface remained
  healthy while the branch stayed dark and local.
- After removing the undocumented `OpenAI-Safety-Identifier` header:
  `python -m pytest -q tests/test_realtime_voice.py tests/test_onboarding_app.py` — **107 passed**;
  `python -m pytest -q tests/test_mirror_parity_gate.py` — **15 passed**; focused Ruff and strict
  OpenSpec validation remained green. The stable signed-in identity still keys TinyAssets' local
  mint limiter, but no provider identity header is invented outside the documented Realtime schema.

The deterministic browser harness executes the shipped JavaScript transition table and `Voice`
adapter under Node. It proves that a locked universe shows `Voice · Connect`, opens the capability
dialog rather than the microphone disclosure, and can become ready only after a fresh server
status says a compatible resource is bound. It also covers permission failure/retry, barge-in
muting with tolerated truncated transcript, call-id duplicate prevention, exact canonical tool
output, untrusted-output refusal, uninterrupted mismatch failure/telemetry, transport teardown,
bounded three-attempt reconnect, and the existing persisted text-history restore path. Server
tests cover both flags, status/session authentication, same-origin enforcement for minting,
empty-body contract, caller-universe rejection, two-identity home isolation, owner-vault-only key
lookup, per-identity mint limits, stable upstream errors, response reduction/redaction, and
no-store.

## Rendered browser evidence

The earlier pre-correction `Voice ready` rendering is superseded and is not rollout evidence. In a
new local in-app-browser rendering with both adapter flags enabled and an injected signed-in
resource-less state, the actual app showed `Voice · Connect`; its accessible description was
`Voice requires a compatible resource`, and the live status explained that the current
ChatGPT/Codex subscription route has no documented Realtime audio authorization. This static
preview made no status, microphone, session-broker, or OpenAI request. The deterministic shipped-
JavaScript harness separately exercises activation of that control and proves it opens the unlock
dialog without exposing the microphone disclosure.

This is rendered UI evidence, not final chatbot-surface, authenticated conversation, microphone,
or device proof.

## Independent review

The corrected authority/security diff was dispatched read-only to the Claude peer on 2026-09-03
with the required structured-disagreement contract. The peer process exited 1 after 17 seconds
with no output. This is recorded in
`docs/reviews/2026-09-03-realtime-voice-authority-correction-review.md` and is not counted as
approval. Opposite-provider review remains a landing gate.

## Rollout and rollback

The kill switch is either server flag: disabling `TINYASSETS_REALTIME_VOICE_ENABLED` removes the
adapter and disabling `TINYASSETS_ALLOW_REALTIME_VOICE_API` independently prevents the initial
OpenAI adapter from using a universe-bound API resource. Neither flag supplies spend authority.
Rollout remains blocked on native permission integration, final store privacy answers, an
authenticated locked-capability browser proof, one browser/device pass in a test universe that
already has a compatible user-bound voice resource, public canary, rendered live conversation,
and post-change deployed-SHA proof. No separate key or spend ceiling is requested from Jonathan.
The first cohort must monitor broker status counts, connection/reconnect failures, latency,
session duration/usage estimates, and content-free `voice_output_mismatch` events. Any anomalous
spend, mismatch, isolation, or capture-teardown signal disables the flag; text chat and canonical
history remain intact because voice adds no migration or audio storage.

## Native coordination

- Android commits `6e855a58`, `ebff23bb`, and `146bfbdf` add `RECORD_AUDIO` only with an
  exact-origin/audio-only WebView gate, a native Continue gesture before the runtime prompt,
  foreground/focus revalidation, exact-request binding and cancellation handling, and pause/stop
  teardown. On 2026-09-03 in the Android release worktree, the generated source/manifest verifier
  passed and `tests/test_android_release_pipeline.py` reported **14 passed**. Draft PR #2793's
  current-head CI at `146bfbdf` passed the Android debug APK, release AAB, iOS compile,
  actionlint, invariants, preview-security, and scope gates; the broad required suite was still
  running when this evidence was stamped. No Android device is attached to this host, and the
  authority-sensitive native diff still needs opposite-provider review because the Claude
  subscription reported its monthly limit. Store copy and the web voice flags remain dark.
- iOS commit `9d0d4375` stages the handoff's exact `NSMicrophoneUsageDescription`, asserts it in
  unsigned and signed workflows, and keeps voice/privacy copy dark. On 2026-09-03 in the iOS
  release worktree, `python -m pytest -q tests/test_mobile_ios_release.py -k "microphone or
  configuration"` reported **3 passed, 8 deselected**. The commit remains on the separate release
  branch; submission still requires a signed physical-iPhone background/end capture-release proof
  and final Audio Data / Other User Content answers.
