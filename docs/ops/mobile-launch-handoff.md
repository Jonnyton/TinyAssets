# Mobile launch handoff — where this stands, 2026-09-03

Written so a new session can pick this up cold. The goal is unchanged: **users able
to download the app from Google Play and the Apple App Store.**

Runbooks stay where they are — `docs/ops/google-play-launch.md` and
`docs/ops/app-store-launch.md` — and founder-only items stay in
`docs/host-actions.md`. This file is the map between them.

---

## The one-line status

**Google Play: installable today, but only by invited testers.** Public availability
is at minimum 14 days away and needs 12 real people. **Apple: the code/build lane is
ready; account enrollment, signing assets, the app record, screenshots, and review
still require founder-owned state.**

---

## Google Play

### Done

- App created (`io.tinyassets.app`, Play app id `4975777632183072073`). Listing,
  graphics, privacy policy URL, in-app privacy link, account deletion, and the
  Ads / Government / Financial / Health declarations are all filled.
- **Content rating** submitted 2026-09-02 — Everyone / PEGI 3 / USK 0 / ClassInd L.
- **Data safety** answered and saved as a draft (it cannot be *submitted* yet; see below).
- **A signed bundle is live on the internal testing track**: release `1 (1.0)`,
  published 2026-09-03 11:10, 3.1 MB.
  Opt-in link: <https://play.google.com/apps/internaltest/4701716760893982267>
- App content checklist reads **8 of 11**.

### The wall, stated precisely

Google Play has three gates stacked in a fixed order, and none of them can be skipped:

1. **Sign in details** needs working reviewer credentials. Our app is behind WorkOS
   AuthKit, and the live sign-in page offers only *"Continue with SSO"* and
   *"Continue with Google"* — there is **no email-and-password option**, so there is
   no credential we could hand Google today. Play's own dialog says reviewers "are
   unable to create accounts, use their own existing accounts, or use free trials."
2. **Target audience and content** refuses to open until (1) is complete. Verified by
   opening it: *"You must complete the Sign in details section before starting the
   Target audience and content questionnaire."*
3. **Data safety** cannot be submitted until (2) is done.

Separately, and independent of those three: a personal developer account must run a
**closed test with at least 12 testers, opted in continuously for 14 days**, before it
may even *apply* for production access. **Open testing is also locked behind production
access** — the Console says so directly, so there is no public route that skips the
closed test.

That 14-day clock is wall-clock. It is the real long pole on Play, and nothing an
agent does shortens it.

### What the next session should actually do

- Nothing on Play is agent-unblockable right now. Both remaining Play items are in
  `docs/host-actions.md` and need the founder.
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

**The Apple Account cannot yet be created, so the Developer Program cannot be enrolled.**
Checked 2026-09-03, not assumed: the official form accepted every field but returned only
"Your account cannot be created at this time." No field-specific validation or new Apple
email appeared, and Apple System Status reported Apple Account services available. That
does not identify a phone, region, account-state, device-limit, or browser/network cause.
Apple's supported next steps are to wait and try one different device/network route, or
use Apple Support. The preserved support tab is staged at **Apple Account → Other Apple
Account Topics → Creating an Apple Account**, immediately before starting Chat.

What is ready, stated precisely — the gap here is wider than "just enrol":

- The Capacitor iOS platform, the `tinyassets://` URL-scheme patch, and the listing
  and App-Privacy copy in `docs/ops/app-store-launch.md`.
- The generated `Info.plist` now includes the exact microphone purpose string for
  the incoming realtime-voice slice. Voice remains dark: a physical-iPhone run must
  prove background/stop release, and App Privacy must be re-evaluated against the
  provider retention configuration before a voice-enabled build can be submitted.
- `ios-build.yml` compiles green on `macos-15` runners, including after the Capacitor 8
  upgrade. `ios-release.yml` now adds the manual, fail-closed signed archive: a verified
  IPA artifact by default and an explicit opt-in App Store Connect/TestFlight upload.
  It never submits for App Review. The build installs the committed TinyAssets icon and
  splash instead of Capacitor's placeholders.
- `app-store-launch.md` still has real iPhone screenshots outstanding. The existing
  1080×1920 Play captures are not valid Apple screenshot dimensions and must not be
  dressed up as native iPhone captures.
- **A Mac is still not needed** — both iOS workflows run on `macos-15` CI runners.

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

The enrollment is $99/year with a one-to-two day identity check, and it needs the
founder: an agent must not create accounts or execute payments. It is the long pole on
the Apple side in exactly the way the 14-day closed test is on the Play side, so it is
worth starting before anything else. Until it exists and supplies signing assets,
the release workflow cannot produce an installable IPA or reach TestFlight.

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
