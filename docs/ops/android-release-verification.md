# Android release verification and rollback

This is the evidence sheet for moving TinyAssets from an internal Play build to a
user-downloadable release. The procedural form copy stays in
[`google-play-launch.md`](google-play-launch.md); this file owns the release gates,
monitoring, and rollback shape.

## Evidence snapshot — 2026-09-03, Windows host + GitHub Actions

| Claim | Evidence | State |
|---|---|---|
| Generated app identity and SDK | Main run `33797592515`, commit `8b8e8a59`; downloaded `app-debug.apk` SHA-256 `5baadde6f09c0afcfcc34a0ccdc76613d3744280d7865abe05c6012bc548689e`; Android build-tools 36 `aapt dump badging` reports `io.tinyassets.app`, version `1 (1.0)`, min SDK 24, target/compile SDK 36 | Verified |
| Compiled permissions | The same APK declares Internet, `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_DATA_SYNC`, plus AndroidX's app-scoped signature permission; no camera, microphone, location, contacts, storage, advertising-id, SMS, or call-log permission | Verified |
| Internal testing release | Repository handoff records Play release `1 (1.0)`, 3.1 MB, published 2026-09-03 11:10 and available to invited testers at the recorded opt-in link | Store receipt recorded; authenticated Console re-check unavailable because the browser automation bridge timed out twice on 2026-09-03 |
| Release CI | Last `android-release.yml` run `33596736810` failed closed at signing because all four upload-key secrets were empty. It predates the API-36/JDK-21 and signing hardening now in this branch. No green signed release-workflow run exists yet. Pull requests now exercise the unsigned release build, lint, and merged-manifest verifier while skipping both secret-backed steps | Open until this branch has a green PR run and a later authorized signed run |
| Clean native generation | From a worktree with no generated `mobile/android/`, `npm ci --ignore-scripts --no-audit --no-fund`, `cap add android`, `cap sync android`, scheme/icon installation, release configuration, and `verify_android_release.py` completed on Windows on 2026-09-03 | Verified; full Gradle build remains a CI gate |
| Final Wolf Moon Seal artwork | `verify_android_release.py --artwork-only` passed directly against logo commit `90639606`: mobile icon/splash, all Android density outputs, and the 512×512 Play icon | Verified in the isolated logo lane; reconcile that commit before the final candidate build |
| Local signed build | The container path produced the Play-uploaded bundle earlier on 2026-09-03. A fresh re-run in this worktree stopped during `npm ci` with Docker `ENOSPC`, before Android generation; that is a host storage failure, not a passing build | Re-run after Docker storage is recovered |
| Device behavior | No dated phone install/sign-in/conversation result is recorded | Open; founder action |

The public privacy policy was also read live on 2026-09-03 at
<https://tinyassets.io/legal#privacy>. It explicitly covers the web, Android, and
desktop clients; WorkOS identity, provider credentials, messages/files, billing
records, processors, TLS, retention/deletion, and the absence of ads/analytics are
described. Treat that as disclosure evidence, not proof that the saved Play Data
safety draft selected the same answers—the Console submission still needs a direct
comparison against this page and the actual SDK/data flows.

The downloaded debug artifact also showed `android:allowBackup="true"`. The
post-generation hardening now forces backup and cleartext traffic off, and the
release verifier checks the source and merged release manifests. This change still
needs a green CI artifact before it can replace the baseline evidence above.

### Pending voice-branch compatibility gate

The separately owned first-class voice branch has declared Android-native work that
is not in this candidate. The current permission allowlist deliberately rejects
`RECORD_AUDIO`, so microphone access cannot be added as an accidental manifest-only
change. If voice reaches the shared `/mcp/app` before this Android candidate ships,
either hide/disable that control in Android or land all of these together before a
bundle is accepted:

- a pre-capture disclosure followed by Android's runtime microphone request;
- a WebView permission handler that accepts only the exact
  `https://tinyassets.io` origin, grants only audio capture, and denies every other
  resource/origin;
- capture teardown when the app backgrounds; and
- a fresh Play Data safety comparison for voice/sound recordings and any canonical
  text retained or sent to providers.

Re-run the source, merged-manifest, device, and Play-disclosure gates after that
integration. Do not loosen the permission allowlist before the native behavior and
disclosure are present.

## Reproducible release inputs

`mobile/android-release.json` is the Android source of truth. It pins the immutable
application id and Play version code/name, and asserts the SDK levels supplied by the
generated Capacitor template. The generated
`mobile/android/` directory remains untracked. The checked-in next candidate is
`1.0.1 (2)`: code 1 is already recorded as uploaded to internal testing, so a newly
built bundle must not reuse it. Promoting the existing code-1 bundle between tracks
does not require or permit a rebuild.

For every Play upload:

1. Increase `versionCode` monotonically. Play never accepts a code it has seen
   before, even if the old artifact was only on a test track.
2. Change `versionName` when the user-facing release label should change. A
   `mobile-v<versionName>` tag must match it exactly; the workflow fails otherwise.
3. Build only after a fresh `cap add android`. A platform generated under an older
   Capacitor major can retain stale SDK values through `cap sync`; configuration fails
   closed rather than silently rewriting a dependency-owned template.
4. Run the post-generation sequence:
   `add_app_scheme.py` → `add_app_icons.py` →
   `configure_android_release.py` → `verify_android_release.py` →
   `gradlew lintRelease bundleRelease` →
   `verify_android_release.py --merged`.
5. Sign only with the pinned upload certificate, verify the JAR signature, and keep
   the emitted SHA-256 file beside the AAB. Never log or put passwords on argv.

Both `.github/workflows/android-release.yml` and `mobile/container/build.sh` enforce
that sequence. Pull requests stop after the unsigned release build and verification;
tag/manual runs require the upload secrets and publish a signed AAB plus its checksum
as the workflow artifact.

## Play policy gates before production access

- App access: provide an active reviewer account and exact steps through WorkOS.
  Google says reviewers cannot rely on creating their own account. The current live
  login offers Google/SSO only, so a dedicated password-based reviewer path remains
  the blocking prerequisite.
- Target audience and Data safety: complete only from verified product behavior and
  SDK/data-flow evidence. The saved draft is not a submitted declaration.
- Foreground service: because the bundle declares a `dataSync` foreground service
  and targets Android 14+, Google requires a Play Console declaration with a
  description, interruption/defer impact, and demonstration video. Use this staged
  evidence, then have the founder review before submission:

  - Function: When a user explicitly starts OpenAI subscription sign-in, TinyAssets
    temporarily runs a local loopback callback listener while the external browser
    completes OAuth. A persistent notification makes the work visible. The listener
    stops on success, cancellation, or timeout.
  - Deferred impact: The browser sign-in may finish without a listener ready to
    receive its callback; the user must restart sign-in. No background sync is lost.
  - Interrupted impact: The callback is not delivered to the app, the attempt times
    out, and no credential from that attempt is stored.
  - Video proof: Record the user tapping **Connect OpenAI**, the foreground-service
    notification while the browser is open, the return to TinyAssets, and the
    notification disappearing. Redact account identifiers and never record secrets.

- Personal-account production access: at least 12 testers must remain opted into a
  closed test continuously for 14 days before the production-access application.
  Internal testing does not count, and open testing is unavailable until production
  access is granted.
- Store media: the final **Wolf Moon Seal** Android and Play icon outputs passed the
  release dimension gate in isolated logo commit `90639606`; that commit must be
  reconciled before the final candidate build. The feature graphic remains correctly
  sized and unchanged. The two phone captures are 1080×1920, but
  `01-universe-conversation.png` exposes an
  internal universe id and implementation/debug discussion. Replace it with a clean,
  representative conversation before production review; do not fabricate a mock
  screenshot.

Current Google references (re-checked 2026-09-03):

- <https://developer.android.com/google/play/requirements/target-sdk>
- <https://support.google.com/googleplay/android-developer/answer/14151465>
- <https://support.google.com/googleplay/android-developer/answer/13392821>
- <https://support.google.com/googleplay/android-developer/answer/10787469>
- <https://support.google.com/googleplay/android-developer/answer/16559646>

## Track progression and release verification

1. **Internal:** founder installs from Play, starts/signs in, opens the Connect view,
   completes one provider callback, sends one conversation message, backgrounds and
   resumes the app, and confirms account deletion/privacy links open. Record device,
   Android version, app version code/name, time, and result.
2. **Closed:** publish the same verified code (or a strictly newer version code) to
   the required closed track. Keep at least 12 testers continuously opted in for 14
   days. Collect actual feedback and resolve crashes, ANRs, sign-in failures, and
   policy/listing mismatches before applying for production access.
3. **First production release:** Play does **not** offer a percentage staged rollout
   for a first release ([Google's staged-rollout help](https://support.google.com/googleplay/android-developer/answer/6346149)). After Google grants production access and review passes, the
   founder's **Start rollout to production** action makes it available to all selected
   countries/regions. Use a narrow country set only if that is the founder's explicit
   launch choice; do not invent distribution scope.
4. **Updates:** use 5% → 25% → 50% → 100%, holding at least 24 hours at each step when
   there is enough usage to judge. If data is sparse, require the device smoke test
   and no new crash/ANR cluster before advancing; absence of metrics is not evidence
   of health.

At every stage, verify Play's release details show the intended package, version,
track, countries, and status. Compare the uploaded bundle's certificate and SHA-256
with the workflow artifact. A GitHub artifact is preparation, not proof that Play is
serving it.

## Monitoring and rollback

Use Play Console → **Monitor and improve → Android vitals** and the release dashboard.
Google's current bad-behavior thresholds are 1.09% overall user-perceived crash rate
and 0.47% overall user-perceived ANR rate (8% per phone model for either). Our launch
thresholds are deliberately tighter:

- Advance only with no new crash/ANR cluster, a green critical-flow smoke test, and
  crash/ANR rates below Google's thresholds.
- Hold on any new cluster, repeated sign-in failure, listing/policy warning, or a
  material regression whose cause is not understood.
- Halt an update immediately for credential exposure, data loss/corruption, broken
  sign-in for a meaningful cohort, any security issue, crash rate ≥1.09%, ANR rate
  ≥0.47%, or a per-device rate ≥8%.

For an **update**, use **Manage rollout → Halt rollout**; the previous eligible
version becomes available to users who have not received the update. Fix forward with
a higher `versionCode`, repeat internal/closed smoke tests, then resume or replace the
rollout.

For the **first production release**, Play cannot halt back to a previous production
version because none exists. The emergency choices are to unpublish (stops new users,
not existing installs) and submit a corrected AAB with a higher version code. That is
why the internal and closed tracks are the rollback rehearsal, not optional ceremony.

Re-check before each release:

- <https://support.google.com/googleplay/android-developer/answer/9844486>
- <https://support.google.com/googleplay/android-developer/answer/9859348>
- <https://support.google.com/googleplay/android-developer/answer/6346149>
- <https://support.google.com/googleplay/android-developer/answer/16285429>
