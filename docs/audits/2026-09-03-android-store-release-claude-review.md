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
| New Gradle/lint/merged-manifest gates have no green workflow run | Accepted. The release workflow now runs its unsigned build on pull requests. A green PR run remains required before merge; a signed run still requires the founder's upload secrets. |
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

The remaining P1 is operational rather than a code finding: open the PR and require
its Android release build to pass on GitHub's Linux/JDK 21/Android SDK environment.
