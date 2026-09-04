# Verification

Date: 2026-09-03
Environment: Windows local worktree, branch `codex/first-class-voice`
Production flags: unchanged/off
Paid Realtime calls: none

## Authority correction

Founder direction on 2026-09-03 established universe authority as the capability boundary and,
after this branch began, current `main` added the rule that the platform substrate may not grow a
provider-specific path. The implementation now uses a provider-neutral `tinyassets.voice.v1`
bridge referenced by a non-secret universe manifest and an existing generic HTTP connection/grant.
Voice code never resolves the long-lived credential; the credential-blind broker child owns that
boundary. A writer-only universe remains Voice-locked and no platform authority is borrowed.

## Automated evidence

- `python -m pytest -q tests/test_realtime_voice.py tests/test_onboarding_app.py`
  — **113 passed, 1 skipped** after the provider-neutral authority correction and merge with
  current `main`. The skip is the platform-dependent symlink creation case. Coverage includes
  authenticated secret-free capability status, connection/grant authority refusal, a locked UI
  that opens only the connection explanation, and the exact-writer/audio lifecycle contract.
- `python -m pytest -q tests/test_realtime_voice.py tests/test_onboarding_app.py tests/test_channel_agnostic_ratchet.py`
  — **128 passed, 1 skipped** after the final same-origin SDP exchange replaced the earlier
  client-side credential design. This is the current focused verification command.
- `python -m pytest -q tests/test_mirror_parity_gate.py` — **15 passed** after rebuilding the
  packaged runtime mirror.
- `python -m pytest -q tests/test_realtime_voice.py tests/test_onboarding_app.py
  tests/test_channel_agnostic_ratchet.py tests/test_mirror_parity_gate.py
  tests/test_brand_parity.py` — **146 passed, 1 skipped** after the Opus round-two repairs.
  Added coverage binds late success and failure to their originating voice transport, enforces
  the configured client session cap, re-prompts after a bound-service change, and refuses a
  non-prefix output mismatch even after a bridge interruption event.
- `python -m ruff check tinyassets/onboarding/__init__.py tinyassets/onboarding/realtime_voice.py tests/test_onboarding_app.py tests/test_realtime_voice.py` — **all checks passed**.
- `python packaging/claude-plugin/build_plugin.py` — **391 runtime files staged; import probe passed**.
- `openspec validate add-realtime-voice-conversation --strict` — **valid**.
- `python scripts/openspec_flow.py check-change add-realtime-voice-conversation --provider codex`
  — **ALLOWED**, with the pre-existing global WIP count of four reported.
- `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp` — the earlier anonymous
  success was superseded when current `main` made the public probes authenticated. This host has
  neither the canary token nor the 1Password CLI needed to load it, so a fresh authenticated
  canary was not claimed locally. The deploy workflow must supply its protected
  `TINYASSETS_WIKI_CANARY_TOKEN` and pass `--assert-handles` after landing.
- `python scripts/check_channel_agnostic.py` — **clean at the 686-reference baseline** after the
  provider-neutral rewrite; the new voice module contributes no provider/channel reference.
- `python scripts/linux_oracle.py -- -q tests/test_realtime_voice.py tests/test_onboarding_app.py`
  — attempted again after the round-two repairs but the local Docker Linux engine remained
  unavailable (`dockerDesktopLinuxEngine` pipe missing). CI Linux is required before the branch
  can be considered verified; the Windows symlink case remains skipped locally for lack of
  symlink privilege.

The deterministic browser harness executes the shipped JavaScript transition table and `Voice`
adapter under Node. It proves that a locked universe shows `Voice · Connect`, opens the capability
dialog rather than the microphone disclosure, and can become ready only after a fresh server
status says a compatible resource is bound. It also covers permission failure/retry, barge-in
muting with tolerated truncated transcript, call-id duplicate prevention, exact canonical tool
output, untrusted-output refusal, uninterrupted mismatch failure/telemetry, transport teardown,
bounded three-attempt reconnect, and the existing persisted text-history restore path. Server
tests cover all three flags, status/session authentication, same-origin enforcement for signaling,
empty-body contract, caller-universe rejection, two-identity home isolation, missing/invalid/
symlinked bindings, exact owner/universe connection grants, session-endpoint allowlisting, bounded
SDP validation, per-identity
session limits, stable bridge errors, response reduction/redaction, and no-store.

## Rendered browser evidence

The earlier pre-correction `Voice ready` rendering is superseded and is not rollout evidence. In a
new local in-app-browser rendering with the voice gates enabled and an injected signed-in
resource-less state, the actual app showed `Voice · Connect`; its accessible description was
`Voice requires a compatible resource`, and the status explained that a user-owned voice
connection is required. This static preview made no status, microphone, session-broker, or remote
service request. The deterministic shipped-
JavaScript harness separately exercises activation of that control and proves it opens the unlock
dialog without exposing the microphone disclosure.

This is rendered UI evidence, not final chatbot-surface, authenticated conversation, microphone,
or device proof.

## Independent review

The corrected authority/security diff was dispatched read-only to the Claude peer on 2026-09-03
with the required structured-disagreement contract. Early attempts either exited without output
or returned an invalid receipt; those assessments are preserved under `docs/reviews/` and are not
approval. A valid Opus round one against `7a13f08f` returned `ADAPT` with two blockers, both fixed
and regression-tested. Opus round two against `050f168a` confirmed both repairs and returned
`ADAPT` with four additional client findings: stale turn completion crossing a transport boundary,
the client cap ignoring configured duration, disclosure acceptance surviving service rebinding,
and interruption over-suppressing mismatch enforcement. All four were repaired and covered by
the 146-test focused run above. The round-two receipt is preserved at
`docs/reviews/2026-09-03-realtime-voice-opus-review-round2.md`. The third and final Opus round
reviewed `20cc50e0` and returned `ADAPT` with one stated blocker: a superseded `_connect` attempt
could globally tear down the replacement transport. That defect is repaired with attempt-local
disposal and a deterministic two-attempt race regression. The saved review omitted the content of
several non-blocking findings it referenced, and the three-round cap forbids another review. On
2026-09-03 the founder explicitly accepted that capped evidence and authorized a dark landing
after exact-head CI. PR #2797 passed every required check and merged as `3edec0ab`; the resolved
concern was deleted. This decision does not authorize enabling or releasing Voice.

## Rollout and rollback

The kill switch is any of the three server flags: disabling `TINYASSETS_REALTIME_VOICE_ENABLED`
removes the app adapter, disabling `TINYASSETS_ALLOW_REALTIME_VOICE_API` prevents session exchange,
and disabling `TINYASSETS_OUTBOUND_HTTP_CONNECTIONS_ENABLED` closes generic egress. No flag
supplies spend authority.
Rollout remains blocked on native permission integration, final store privacy answers, an
authenticated locked-capability browser proof, one browser/device pass in a test universe that
already has a compatible user-bound voice resource, public canary, rendered live conversation,
and post-change deployed-SHA proof. No separate key or spend ceiling is requested from Jonathan.
Production deploy run `33832278162` started the merged image healthy, then rolled it back because
the canary principal's no-home `get_status` shape omitted `active_host` and `release_state`; the
same pre-existing defect appears in run `33831877514` and is being repaired independently in PR
#2814. The failed canary means this archive is landing evidence, not a deployed-SHA claim.
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
