# Android release verification and rollback

This is the evidence sheet for moving TinyAssets from an internal Play build to a
user-downloadable release. The procedural form copy stays in
[`google-play-launch.md`](google-play-launch.md); this file owns the release gates,
monitoring, and rollback shape.

## Evidence snapshot — 2026-09-03, Windows host + GitHub Actions

| Claim | Evidence | State |
|---|---|---|
| Generated app identity and SDK | Main run `33797592515`, commit `8b8e8a59`; downloaded `app-debug.apk` SHA-256 `5baadde6f09c0afcfcc34a0ccdc76613d3744280d7865abe05c6012bc548689e`; Android build-tools 36 `aapt dump badging` reports `io.tinyassets.app`, version `1 (1.0)`, min SDK 24, target/compile SDK 36 | Verified |
| Compiled permissions | Baseline APK `5baadde6...` declares Internet and foreground-service permissions but no microphone. The next candidate intentionally adds `RECORD_AUDIO` together with the native safeguards below; it still declares no camera, location, contacts, storage, advertising-id, SMS, or call-log permission | Baseline verified; candidate CI + device proof required |
| Internal testing release | Repository handoff records Play release `1 (1.0)`, 3.1 MB, published 2026-09-03 11:10 and available to invited testers at the recorded opt-in link | Store receipt recorded; authenticated Console re-check unavailable because the browser automation bridge timed out twice on 2026-09-03 |
| Release CI | Draft PR run `33816154684`, merge head `9ef0c693`, succeeded on GitHub's Ubuntu runner on 2026-09-03: clean generation, voice-native Java compilation, release configuration/verification, `lintRelease bundleRelease`, real merged-manifest verification, and bundle location all passed. The ancestry/signing/upload steps were skipped on the PR by design. No green signed release-workflow run exists yet | Unsigned candidate verified; authorized signed run remains open |
| Clean native generation | From a worktree with no generated `mobile/android/`, `npm ci --ignore-scripts --no-audit --no-fund`, `cap add android`, `cap sync android`, scheme/icon installation, release configuration, and `verify_android_release.py` completed on Windows on 2026-09-03 | Verified; full Gradle build remains a CI gate |
| Final Wolf Moon Seal artwork | `verify_android_release.py --artwork-only` passed for the reconciled logo commit `688b5cff`: mobile icon/splash, all Android density outputs, and the 512×512 Play icon. That commit is an ancestor of candidate merge head `9ef0c693` | Verified and reconciled |
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

### First-class voice native gate

The next Android candidate includes the native half of first-class voice while the
web voice flag and store copy remain off. `VoiceWebChromeClient` denies every origin
except normalized `https://tinyassets.io` on the default HTTPS port, denies camera or
mixed-resource requests, and grants only WebView audio capture. A web-initiated
request first shows a native disclosure; only the user's **Continue** tap opens the
Android runtime microphone prompt. Active tracked media streams stop in `onPause`,
and pending requests are denied in `onStop`/destroy. The release verifier requires
that implementation and rejects any permission outside the explicit allowlist.

This is build evidence, not device proof. Keep the web voice control/flag and Play
voice copy dark until a real internal-test phone proves prompt ordering, denial,
record/stop, Home/app-switch teardown, screen-lock teardown, and return-to-app state.
Before enabling voice, compare the real data flow against Play Data safety for
voice/sound recordings and for canonical text retained or sent to providers. Then
replace the candidate evidence above with `aapt` output from the exact signed AAB/APK
and a dated device result.

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
  access is granted. The private recruitment/onboarding tracker and message are in
  `docs/host-actions.md`; target 15–18 invitees to protect the continuous minimum.
- Store media: the final **Wolf Moon Seal** Android and Play icon outputs are included
  in the candidate. The unsafe conversation image was removed and replaced on
  2026-09-03 with an honest 540×960 live signed-out capture. It and the retained
  1080×1920 Connect capture pass the release artwork gate and expose no account,
  universe, branch, run, or credential identifiers. They remain staged, not uploaded.

Current Google references (re-checked 2026-09-03):

- <https://developer.android.com/google/play/requirements/target-sdk>
- <https://support.google.com/googleplay/android-developer/answer/14151465>
- <https://support.google.com/googleplay/android-developer/answer/13392821>
- <https://support.google.com/googleplay/android-developer/answer/10787469>
- <https://support.google.com/googleplay/android-developer/answer/16559646>
- <https://support.google.com/googleplay/android-developer/answer/15748846>

## Internal-phone smoke record

This is the smallest device proof required before promoting a candidate to the closed
track or attesting to its foreground-service behavior. Test the Play-installed build,
not a sideloaded debug APK. Use a dedicated test account and non-sensitive content.

Record first: date/time/timezone, tester initials, phone model, Android version,
Play-displayed app version/code, network type, install source, and the candidate commit
or artifact checksum if known. Then record pass/fail plus a short observation for every
row:

| Flow | Required observation |
|---|---|
| Install/update | Accept the internal-test invitation; install from Play; cold launch without a crash, blank screen, or debug UI. |
| Sign-in | Sign in through WorkOS; return to TinyAssets; kill/relaunch once and confirm the session behavior is coherent. Never record the password or callback URL. |
| Core navigation | Open universe/chat, Connect, Account, privacy policy, and account-deletion information. Links resolve and Back returns predictably. Do not actually delete a non-disposable account. |
| Provider callback | Start **Connect OpenAI**; observe the foreground-service notification before/during the browser step; complete or cancel; return to the app; confirm the notification disappears on success, cancel, and timeout. Redact identifiers in the required declaration video. |
| Conversation | With a review-safe provider connected, send one ordinary non-sensitive message and confirm one response plus usable error/retry behavior. If no safe provider exists, mark this blocked rather than borrowing a personal credential. |
| Lifecycle | During Connect and an idle app screen, press Home, app-switch, screen-lock/unlock, and return. Confirm no stuck notification, leaked microphone indicator, duplicate callback, or corrupted screen state. |
| Connectivity | Repeat one launch/navigation step offline or during a network transition; confirm a visible recoverable error rather than silent failure. |
| Dormant voice safeguards | The store/web voice control and copy remain off. If an internal-only path can invoke the native prompt, prove disclosure → Android microphone prompt ordering, Deny, Allow, stop, Home/app-switch teardown, screen-lock teardown, and no camera/mixed-resource grant. Otherwise record "not user-reachable" and keep voice disabled. |

Capture: one redacted foreground-service video; screenshots only for failures or
non-sensitive proof; exact timestamps for logs; and a final `PASS`, `FAIL`, or
`BLOCKED` verdict per row. A failed row blocks closed-track promotion until fixed and
retested. After any code fix, use a higher Play version code and rerun the full sheet.

## Independent voice-native review gate

The earlier Claude review predates `VoiceWebChromeClient.java`; it cannot approve the
later microphone/permission diff. Before landing or enabling voice, a Claude-family
reviewer must independently inspect the exact candidate with no write permission and
return `AGREE`, `DISAGREE_EVIDENCE` with file/line evidence, or
`DISAGREE_CONCERN`. The prepared scope, commands, and retry path are recorded in
`docs/audits/2026-09-03-android-store-release-claude-review.md`. A same-family review,
green CI, or device test complements but does not replace that repository gate.

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
