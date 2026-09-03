# Android store release — cross-family review

**Date:** 2026-09-03  
**Author / reviewer:** Codex implementation, Claude Opus independent read-only review  
**Environment:** Windows worktree; review command used Claude CLI safe mode after two
ordinary `scripts/peer_agent.py` dispatches were intercepted by unrelated workspace
task-ledger hooks and returned only their epilogues.  
**Review verdict:** `ADAPT`

The reviewer inspected the live Android release diff, ran only
`tests/test_android_release_pipeline.py` (9 passed at its snapshot), and returned
three P1 findings plus P2 hardening notes. This table is the durable disposition.

| Review finding | Disposition |
|---|---|
| New Gradle/lint/merged-manifest gates have no green workflow run | Resolved. Draft PR run `33812289283` proved clean generation, release lint, and `bundleRelease`, then failed closed because AGP 8's real merged root omits `android:compileSdkVersion`. The verifier was corrected to read package/version/min/target from that artifact and continue asserting compile SDK from generated Gradle input. Rerun `33812526724` at `d61b0a95` passed the complete unsigned release job; a signed run still requires the founder's upload secrets. |
| Exact 1080×1920 listing screenshots were coupled to every debug APK build | Fixed. Default app verification checks packaged app artwork only. The release-only artwork gate checks Play media separately and accepts screenshots within Play's 320–3840 px / 2:1 bounds. |
| `add_app_scheme.py` still claimed `dataSync` needed no Play justification | Fixed. The source comment now matches the required Play declaration and behavior-video gate. |
| Signed workflow could fetch main anonymously after checkout removes credentials | Accepted under this repository's explicit public-repository invariant, documented inline. A private fork fails closed until it supplies read auth. Tag/manual signing is limited to commits already in main history. |
| Literal `mobile-v` tag bypassed the version-name assertion | Fixed. A tag with no suffix now fails. The candidate is code 2 / name 1.0.1 because Play already has code 1; Play remains the final monotonic-code authority. |
| Docs/step name said SDK values were applied even though dependency-owned values are asserted | Fixed in workflow and runbook language. Version is applied; generated SDK levels are asserted. |
| Same-job checksum is not independent provenance | Accepted and kept explicit: it verifies transfer integrity, not builder identity. The main-history gate and pinned upload certificate are the current provenance controls. Adding OIDC attestation to the PR build job was rejected because it would grant untrusted PR code token authority; a future separate signing job can add attestations safely. |
| Manifest parser caveats and `uses-permission-sdk-23` visibility | Capacitor's current non-self-closing application tag is covered by clean-generation evidence. Permission scanning now includes both permission element forms. |
| First-release staged-rollout claim lacked a nearby source | Fixed with an inline link to Google's staged-rollout help; the runbook still requires a live Console check before rollout. |
| Container wording implied it performed signing | Fixed. It produces the verified unsigned bundle; `sign.sh` owns signing. |

The requested missing tests were added for a realistic merged release manifest,
debuggable/version drift, unexpected microphone permission, an unprotected exported
component, debug-workflow gate presence, runbook/version consistency, and zero/multiple
merged-manifest candidates. Final focused result after adaptation: **16 passed**.

The operational P1 is closed by run `33812526724`. Signing, Play upload, policy
submission, and rollout remain deliberately outside this review and change.

## Later voice-native reconciliation

After that verdict, the voice lane requested a native Android microphone slice on
this branch. It adds `RECORD_AUDIO`, an exact-origin/audio-only WebView permission
handler, a native Continue gesture before every grant, runtime permission handling,
and background capture teardown. That later authority-sensitive diff is **not covered
by the `ADAPT` verdict above**.

On 2026-09-03, `scripts/peer_agent.py claude` failed before review output, and a
direct `claude -p --safe-mode --permission-mode plan --model fable` retry reported
that the Claude subscription had reached its monthly spend limit. Therefore this
slice may be built and exercised in the draft PR, but the repository's independent
cross-family landing gate remains open. Device proof and Play Data safety comparison
also remain open; voice flags and store copy must stay off until both are closed.

A voice-lane review of the first draft found that an older disclosure callback could
act on a newer pending WebView request, and that WebView cancellation was not handled.
The implementation now rejects overlapping requests, binds each disclosure callback
to its exact `PermissionRequest`, clears only a matching canceled request, dismisses
stale dialogs, and revalidates the request origin, current WebView origin, audio-only
resource set, window focus, and activity state immediately before granting. Focused
tests and the release verifier enforce those source safeguards; the independent
cross-family and device gates above remain open.
