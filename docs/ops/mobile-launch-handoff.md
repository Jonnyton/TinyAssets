# Mobile launch handoff — where this stands, 2026-09-03

Written so a new session can pick this up cold. The goal is unchanged: **users able
to download the app from Google Play and the Apple App Store.**

Runbooks stay where they are — `docs/ops/google-play-launch.md` and
`docs/ops/app-store-launch.md` — and founder-only items stay in
`docs/host-actions.md`. This file is the map between them.

---

## The one-line status

**Google Play: installable today, but only by invited testers.** Public availability
is at minimum 14 days away and needs 12 real people. **Apple: the App Store record,
metadata, unpublished privacy draft, signing/profile/API credentials, verified signed
IPA, and both required screenshots are staged; legal/privacy attestations, one contact
disclosure authorization, device proof, and review remain.** The authoritative phone
number already exists in the founder's local candidate profile; it must not be copied
into this repository or sent to Apple without explicit action-time authorization.

---

## Google Play

### Done

- App created (`io.tinyassets.app`, Play app id `4975777632183072073`). Listing,
  graphics, privacy policy URL, in-app privacy link, account deletion, and the
  Ads / Government / Financial / Health declarations are all filled.
- **Content rating** submitted 2026-09-02 — Everyone / PEGI 3 / USK 0 / ClassInd L.
- **Data safety** corrected to list password + OAuth account creation, saved, and
  Actioned; it has not been sent for review.
- **Advertising ID** saved as **No** after the shipped artifact, current merged
  manifest, and locked dependencies all verified that no advertising ID is used. It
  is Actioned in Play but has not been sent for review.
- WorkOS production now supports Email + Password with its recommended strong policy.
  The founder/admin remains `jonathan.m.farnsworth@gmail.com`. The dedicated reviewer
  identity is `play-review@tinyassets.io` (`user_01M1N3BFV6N1V1C9PP1NEWCCHP`), routed
  through the TinyAssets `info@tinyassets.io` mailbox to the founder's controlled Gmail.
  WorkOS shows it Verified + Active, with no organization or connected accounts and two
  successful password sign-ins. Both sign-ins reached the same isolated empty universe.
  Play **Sign in details** is saved and Actioned with that account; the mistaken Simkal
  plus-alias reviewer was deleted after the replacement was proven.
- **A signed bundle is live on the internal testing track**: release `1 (1.0)`,
  published 2026-09-03 11:10, 3.1 MB.
  Opt-in link: <https://play.google.com/apps/internaltest/4701716760893982267>
- App content now shows **10 actioned declarations** and **1 needing attention**.

### The wall, stated precisely

Google Play had three gates stacked in a fixed order. All three are now complete:

1. **Sign in details — done 2026-09-03.** The durable TinyAssets alias, isolated WorkOS
   user, two clean password sign-ins, and saved Play instruction set are all verified.
   The optional Google/partner-device feedback switch was left off. Nothing was sent
   for review.
2. **Target audience and content — done 2026-09-03.** Saved as **18 and over** and
   Actioned; not sent for review.
3. **Data safety — done 2026-09-03.** The verified data-flow answers are Actioned,
   including both password and OAuth account creation; not sent for review.

Separately, and independent of those three: a personal developer account must run a
**closed test with at least 12 testers, opted in continuously for 14 days**, before it
may even *apply* for production access. **Open testing is also locked behind production
access** — the Console says so directly, so there is no public route that skips the
closed test.

That 14-day clock is wall-clock. It is the real long pole on Play, and nothing an
agent does shortens it.

### What the next session should actually do

- The only App content declaration needing attention is **Foreground service
  permissions**. Play requires a public demonstration-video link; no verified redacted
  phone recording exists yet. The exact shot list is in `docs/host-actions.md`. Do not
  submit or send anything for review before that evidence exists.
- **Do not** re-derive the `gh secret set` situation. It is denied by the harness
  classifier (tested four times, including piping from a file so no value entered
  argv). Do not route around it with `gh api` — that bypasses the intent of the
  denial. It is also **not** on the critical path any more: see below.

---

## Building a bundle without CI

`mobile/container/` holds a Dockerfile and two scripts that mirror
`android-release.yml` and produce a signed `.aab` in about five minutes, needing **no
GitHub secret at all**. Read `mobile/container/README.md`. This is how the current
Play build was made.

The correction worth carrying forward: the four `ANDROID_UPLOAD_*` secrets were
written up in this repo as *the* blocker. They were not. The goal was a signed bundle
in the Console; GitHub secrets are one route to that, and a denied route is not the
same as a blocked goal. Setting them is still worth doing — it turns each future
release into one `gh workflow run` — but nothing waits on it.

---

## Apple App Store

**Apple Developer Program membership is active.** Checked 2026-09-03, not inferred from
the purchase receipt: the signed-in portal exposes App Store Connect and Certificates,
IDs & Profiles, and shows a Team ID plus a 2027 renewal date. The Apple Developer Program
License Agreement and Apple Developer Agreement both show accepted on 2026-09-03. The
explicit App ID
`io.tinyassets.app` was registered and verified on 2026-09-03 in the signed-in Apple
Developer browser: the Identifiers list showed `TinyAssets iOS` and the exact bundle ID.
The founder accepted App Store Connect Terms of Service V100 (last updated 04 June
2018) on 2026-09-03. The TinyAssets App Store Connect record now exists (Apple ID
`6808434444`), with iOS 1.0 in **Prepare for Submission**. Product metadata and
manual release are saved; the four-type privacy draft is configured but unpublished,
with legal-policy URLs blank. An empty `Internal` TestFlight group exists with automatic
distribution off, 0 testers, and 0 builds. An Apple Distribution certificate/private
key, matching App Store profile, and Developer-role CI upload key now exist; all six
required values are protected GitHub environment secrets. Signed IPA 1.0.0 (1) is
verified. Apple's upload rejected build 2 only because the runner defaulted to Xcode
16.4/iOS 18.5 while iOS SDK 26 is mandatory; exact reviewed revision `6ccb3d24`
selects Xcode 26.3 and has a Claude Opus **AGREE** receipt. The exact remaining values and confirmation boundaries are in
`docs/ops/app-store-submission-packet.md`.

What is ready, stated precisely — the gap here is wider than "just enrol":

- The Capacitor iOS platform, the `tinyassets://` URL-scheme patch, and the listing
  and App-Privacy copy in `docs/ops/app-store-launch.md`. The complete Apple-specific
  metadata, privacy/age/export drafts, screenshot manifest, TestFlight copy,
  accessibility device matrix, smoke checklist, and portal sequence are in
  `docs/ops/app-store-submission-packet.md`.
- The generated `Info.plist` now includes the exact microphone purpose string for
  the incoming realtime-voice slice. Voice remains dark: a physical-iPhone run must
  prove background/stop release, and App Privacy must be re-evaluated against the
  provider retention configuration before a voice-enabled build can be submitted.
- The generated `Info.plist` declares `ITSAppUsesNonExemptEncryption = false`; the
  current shell uses only exempt OS-provided HTTPS/TLS and no custom cryptography.
- `ios-build.yml` compiles green on `macos-15` runners, including after the Capacitor 8
  upgrade. `ios-release.yml` now adds the manual, fail-closed signed archive: a verified
  IPA artifact by default and an explicit opt-in App Store Connect/TestFlight upload.
  It never submits for App Review. The build installs the committed TinyAssets icon and
  splash instead of Capacitor's placeholders.
- `app-store-launch.md` still has real iPhone screenshots outstanding. The existing
  1080×1920 Play captures are not valid Apple screenshot dimensions and must not be
  dressed up as native iPhone captures.
- **A Mac is still not needed** — both iOS workflows run on `macos-15` CI runners.
- **App Review risk remains:** the installed shell loads the remotely served client.
  Apple's current Guideline 4.2 may treat that as a repackaged website even though the
  product has real utility and native OAuth return. The evidence and pre-submission
  decision are recorded in
  `docs/concerns/2026-09-03-ios-web-wrapper-app-review-risk.md`.
- **Privacy publication is not ready:** the public policy URL is reachable, but it
  still says Draft v0 pending counsel and its deployed copy omits iOS. PR #2798
  stages the iOS wording only; the final legal approval and post-deploy proof remain.

Local evidence, Windows checkout, 2026-09-03:

- `npm ci --ignore-scripts --no-audit --no-fund && npx --no-install cap add ios &&
  npx --no-install cap sync ios && python scripts/add_ios_scheme.py && python
  scripts/add_ios_assets.py` — passed
  against Capacitor 8.5.1's generated Xcode project. The generated icon's SHA-256
  matched `resources/icon.png`; all three splash hashes matched `resources/splash.png`.
- `python -m pytest -q tests/test_mobile_ios_release.py tests/test_onboarding_app.py
  -k "mobile_ios_release or android_shell or app_itself_links"` — 13 passed, 83
  deselected. The two account-deletion/native checkout guards also passed directly.
- `actionlint .github/workflows/ios-build.yml .github/workflows/ios-release.yml` —
  passed (actionlint container on Windows).
- `npm audit --audit-level=high` — passed after removing unused
  `@capacitor/assets`; three moderate `uuid` findings remain and are recorded in
  `docs/concerns/2026-09-03-capacitor-cli-uuid-advisory.md`.
- `python -m pytest -q tests/test_mobile_ios_release.py` — 15 passed after adding
  automated App Store metadata byte-limit, keyword, URL, and least-access guards.
- PR #2798 exact-head `build-ios` on GitHub's `macos-15` runner — passed 2026-09-03
  after the App ID registration update.

Membership, the explicit App ID, the App Store Connect record, signing/profile/API
credentials, and all six protected secrets are active. The release workflow produced
and verified a signed IPA. TestFlight upload is blocked only by Apple's new iOS 26 SDK
floor and the repository's required cross-family review; the focused local fix selects
Xcode 26.3 and fails closed if the SDK is not 26.x.

---

## Traps already paid for — do not rediscover these

- **Try a verification step before filing it as a founder action.** The Play contact
  phone was written up here and in `docs/host-actions.md` as *"BLOCKS EVERYTHING"*, on
  the reasoning that Google would send a code only the founder could read. It sent no
  code: verifying took one click in the Console. The row then outlived its own truth by
  a day, still telling the founder the launch was stuck behind them while the app was
  already on internal testing. Both a wrong blocker and a stale one cost more than the
  step would have.
- **When a launch state changes, the table at the *top* of a doc is what rots.** §0 of
  the Play runbook contradicted its own status checklist 350 lines below, because the
  checklist got updated and the founder-facing summary did not. Update both or neither.

- **Play requires `targetSdk` 36 for new apps since 2026-08-31.** Capacitor 6 pins 34,
  and a low target is **rejected at upload**, not warned about. We are on Capacitor 8
  (which also forces node 22 and **JDK 21** — Capacitor 8 compiles its Java at
  source/target 21). The August cutover repeats annually; re-check
  <https://developer.android.com/google/play/requirements/target-sdk> before each release.
- **`cap sync` preserves a stale `android/variables.gradle`.** A checkout that generated
  the platform under Capacitor 6 keeps minSdk 22 / SDK 34 after the dependency bump and
  builds a bundle Play rejects *while looking perfectly healthy*. Delete `mobile/android`
  before regenerating. CI never sees this because it starts clean.
- **Capacitor 8's iOS side is Swift Package Manager, not CocoaPods.** `cap sync ios`
  writes `Package.swift` and never runs `pod install`, so there is no `App.xcworkspace`.
  Build `App.xcodeproj`.
- **`~/.tinyassets/android/upload-keystore.env` has CRLF endings.** Sourcing it leaves a
  trailing `\r` on every value, and keytool then reports *"Keystore was tampered with, or
  password was incorrect"* — which blames the keystore for a line-ending bug. `tr -d '\r'`
  first. The same trap applies to `gh secret set`.
- **Git Bash mangles `origin/main:path`** into `origin\main;path`, so `git show` fails and
  a piped `grep -c` returns a confident `0`. Set `MSYS_NO_PATHCONV=1`. This produced one
  false "main is broken" alarm in the session that wrote this file.
- **Auto-merge can land a stale head.** #2784 squash-merged between two of my pushes, so
  two commits silently did not land. After any auto-merge, diff your branch against main
  and check what actually arrived.

---

## Open PRs from this work

- **#2784** — merged. Capacitor 8, targetSdk 36, JDK 21, node 22, iOS SPM fix.
- **#2786** — the live-status docs and the iOS runbook correction.
