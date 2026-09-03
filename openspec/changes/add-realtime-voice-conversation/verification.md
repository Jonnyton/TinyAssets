# Verification

Date: 2026-09-03
Environment: Windows local worktree, branch `codex/first-class-voice`
Production flags: unchanged/off
Paid Realtime calls: none

## Automated evidence

- `python -m pytest -q tests/test_realtime_voice.py tests/test_onboarding_app.py tests/test_mirror_parity_gate.py`
  — **122 passed** after rebuilding the packaged runtime mirror.
- `python -m ruff check tinyassets/onboarding/__init__.py tinyassets/onboarding/realtime_voice.py tests/test_onboarding_app.py tests/test_realtime_voice.py` — **all checks passed**.
- `python packaging/claude-plugin/build_plugin.py` — **391 runtime files staged; import probe passed**.
- `openspec validate add-realtime-voice-conversation --strict` — **valid**.
- `python scripts/openspec_flow.py check-change add-realtime-voice-conversation --provider codex`
  — **ALLOWED**, with the pre-existing global WIP count of four reported.
- After removing the undocumented `OpenAI-Safety-Identifier` header:
  `python -m pytest -q tests/test_realtime_voice.py tests/test_onboarding_app.py` — **107 passed**;
  `python -m pytest -q tests/test_mirror_parity_gate.py` — **15 passed**; focused Ruff and strict
  OpenSpec validation remained green. The stable signed-in identity still keys TinyAssets' local
  mint limiter, but no provider identity header is invented outside the documented Realtime schema.

The deterministic browser harness executes the shipped JavaScript transition table and `Voice`
adapter under Node. It covers permission failure/retry, barge-in muting with tolerated truncated
transcript, call-id duplicate prevention, exact canonical tool output, untrusted-output refusal,
uninterrupted mismatch failure/telemetry,
transport teardown, bounded three-attempt reconnect, and the existing persisted text-history
restore path. Server tests cover both flags, authentication, same-origin enforcement, empty-body
contract, caller-universe rejection, two-identity home isolation, owner-vault-only key lookup,
per-identity mint limits, stable upstream errors, response reduction/redaction, and no-store.

## Rendered browser evidence

Chrome rendered the real app HTML/CSS/JavaScript from a local Starlette preview with both voice
flags set only in that preview process. The preview bypassed sign-in solely to expose the signed-in
composer; it did not simulate an authenticated server turn. The Voice control rendered enabled
with `Voice ready.` in the live region. Activating it opened the modal, moved focus to `Continue`,
and visibly showed all required disclosure text. Both `Not now` and a final-tree `Escape` pass
closed the modal and restored focus to the Voice control. No microphone permission was accepted
and no session broker or OpenAI request was made.

This is rendered UI evidence, not final chatbot-surface, authenticated conversation, microphone,
or device proof.

## Rollout and rollback

The kill switch is either server flag: disabling `TINYASSETS_REALTIME_VOICE_ENABLED` removes the
UI/broker and disabling `TINYASSETS_ALLOW_REALTIME_VOICE_API` independently prevents metered API
use. Rollout remains blocked on a founder-approved user-owned key and spend ceiling, native
permission integration, final store privacy answers, one authenticated browser session, one
physical-device pass, public canary, rendered live conversation, and post-change deployed-SHA
proof. The first cohort must monitor broker status counts, connection/reconnect failures, latency,
session duration/usage estimates, and content-free `voice_output_mismatch` events. Any anomalous
spend, mismatch, isolation, or capture-teardown signal disables the flag; text chat and canonical
history remain intact because voice adds no migration or audio storage.

## Native coordination

- Android confirmed its current manifest verifier rejects `RECORD_AUDIO`; it will add permission
  only with the exact-origin WebView gate, disclosure, background release, and Data safety update.
- iOS commit `9d0d4375` stages the handoff's exact `NSMicrophoneUsageDescription`, asserts it in
  unsigned and signed workflows, and keeps voice/privacy copy dark. On 2026-09-03 in the iOS
  release worktree, `python -m pytest -q tests/test_mobile_ios_release.py -k "microphone or
  configuration"` reported **3 passed, 8 deselected**. The commit remains on the separate release
  branch; submission still requires a signed physical-iPhone background/end capture-release proof
  and final Audio Data / Other User Content answers.
