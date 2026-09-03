# Apple App Store launch — runbook

The iOS counterpart of `google-play-launch.md`. The iPhone app is the SAME
Capacitor shell over `https://tinyassets.io/mcp/app` — one shared core with the
Android + web + desktop surfaces. Staged so the founder's actions are limited to
the Apple account, agreements, payment, signing/API assets, truthful console
declarations, device testing, and the final submit.

Bundle id: **`io.tinyassets.app`** (matches `mobile/capacitor.config.json`
`appId`; permanent once published).

> **Picking this up cold? Read [`mobile-launch-handoff.md`](mobile-launch-handoff.md)
> first.** This file is the procedure; that one is where both platforms actually
> stand. The short version for iOS: Apple Developer Program membership activated
> on 2026-09-03; the explicit App ID was registered and verified that day. App
> Store Connect presented a new Terms of Service before the Apps page, so the
> app record remains the next gate and the agreement is awaiting founder review.
> The copy-ready form answers, asset manifest, smoke checklist, and exact portal
> sequence live in [`app-store-submission-packet.md`](app-store-submission-packet.md).

---

## 0. Founder-only actions (I cannot do these)

| Step | Action | Where |
|---|---|---|
| Account | **Complete 2026-09-03:** Apple Developer Program membership active. | developer.apple.com/account |
| Payment | **Complete 2026-09-03:** annual membership purchase confirmed. | Apple Online Store |
| App ID | **Complete 2026-09-03:** `TinyAssets iOS` / `io.tinyassets.app` registered and visible in the signed-in Identifiers list. | developer.apple.com |
| App record | Review the newly presented App Store Connect Terms of Service, then create the app record for `io.tinyassets.app` before any upload. The terms were not accepted and no record was created. | App Store Connect |
| Signing assets | Create an Apple Distribution certificate + App Store Connect provisioning profile for `io.tinyassets.app`, and an **App Store Connect API key** for CI upload. Provide them as Actions secrets (§3). | developer.apple.com / App Store Connect |
| Identity/tax/banking | Complete Apple's identity + (for paid apps) tax/banking. This app is free → tax/banking optional. | App Store Connect |
| Submit | Click **Submit for Review** after the build + metadata are in. | App Store Connect |

Everything else below I build/stage.

---

## 1. What ships

A signed **`.ipa`** built from the Capacitor iOS project (`mobile/ios/`, generated
by `cap add ios`), uploaded to **App Store Connect** → **TestFlight** (internal
testers in minutes) → **App Store** (review, ~1–3 days). The web app updates ship
instantly; a new `.ipa` is only needed for native-shell/config changes.

CI: `.github/workflows/ios-build.yml` compile-checks the project unsigned on every
change (no Apple account needed). `.github/workflows/ios-release.yml` is the
manual-only signed lane: it exports a verified IPA artifact by default, and only
uploads to App Store Connect/TestFlight when the dispatcher explicitly turns on
`upload_to_testflight`. It never submits for App Review.

---

## 2. Local build (needs a Mac + Xcode)

```bash
cd mobile
npm ci
npm run add:ios          # cap add ios (generates ios/; writes Package.swift, NOT a Podfile)
npm run sync:ios         # cap sync ios
python3 scripts/add_ios_scheme.py   # registers OAuth return + microphone purpose
python3 scripts/add_ios_assets.py   # installs TinyAssets icon + splash, fails on drift
npm run open:ios         # opens Xcode → Product > Archive → Distribute App > App Store Connect
```

**Capacitor 8 uses Swift Package Manager, not CocoaPods.** When every plugin ships a
`Package.swift` — ours all do — `cap sync ios` writes `Package.swift` and never runs
`pod install`, so there is **no `App.xcworkspace`**. Open and build `App.xcodeproj`.
CI does the same: `ios-build.yml` passes `-project App.xcodeproj`, falling back to a
workspace only if a CocoaPods integration ever reappears. If you follow an old
Capacitor guide that says to open the workspace, it will not exist and that is correct.

In Xcode: select the App target → Signing & Capabilities → your Team →
"Automatically manage signing." Archive → Distribute → App Store Connect → Upload.

---

## 3. GitHub environment + secrets for signed builds

The protected GitHub environment **`app-store`** was created on 2026-09-03. It
requires the founder's approval and allows deployments only from `main`. Both
release jobs use that environment, so neither a signing identity nor an upload
credential is exposed to an unapproved run. No signing secrets are present yet.
Store all six values as `app-store` environment secrets; each step references
only the subset it uses:

| Secret | Value |
|---|---|
| `APPLE_DISTRIBUTION_CERT_P12_B64` | base64 of your Distribution cert `.p12` |
| `APPLE_DISTRIBUTION_CERT_PASSWORD` | the `.p12` password |
| `APPLE_PROVISIONING_PROFILE_B64` | base64 of the App Store provisioning profile |
| `APP_STORE_CONNECT_API_KEY_ID` / `_ISSUER_ID` / `_KEY_B64` | App Store Connect API key ID, issuer ID, and base64 of the downloaded `.p8`; used only by the explicit upload job |

The profile must be the **App Store Connect** distribution type for the explicit
App ID `io.tinyassets.app`, and must include the same certificate supplied in the
`.p12`. The workflow rejects a mismatched bundle ID, a development profile, a
missing distribution identity, malformed version/build numbers, or an invalid
export. Signing files live only in runner-temporary storage and are deleted after
the archive step.

Run **iOS signed release** manually. Leave `upload_to_testflight` off to produce
only a 14-day IPA artifact with a SHA-256 checksum and source/version manifest.
Turn it on only when the app record exists and a TestFlight upload is intended;
that job validates before upload. Uploading creates a build in App Store Connect
but does not select it for an App Store version or submit it for review.

---

## 4. App Store listing content (copy-paste)

The complete copy-ready metadata, including description, internal SKU, version,
privacy choices URL, copyright, review notes, age-rating draft, and export answer,
is in [`app-store-submission-packet.md`](app-store-submission-packet.md).

Reuse the Play content in `google-play-launch.md` §4 verbatim where it fits:

- **Name:** `TinyAssets`
- **Subtitle (≤30 chars):** `Your own AI universe`
- **Promotional text (≤170):** `A persistent AI universe that runs real, multi-step work on your own LLM — the same universe on web, phone, and your chatbot.`
- **Description:** the full description from `google-play-launch.md` §4.
- **Keywords (≤100 chars):** `AI,assistant,agent,automation,workflow,universe,productivity,LLM,OpenAI,Claude`
- **Support URL:** https://tinyassets.io
- **Marketing URL:** https://tinyassets.io
- **Privacy Policy URL:** https://tinyassets.io/legal (the app-data section added for Play covers iOS too)
- **Category:** Productivity

---

## 5. App Privacy ("nutrition label", App Store Connect → App Privacy)

Mirror the Play Data-safety answers (`google-play-launch.md` §6):
- **Contact Info → Email Address** — collected, linked to identity, for App
  Functionality. Not used for tracking.
- **User Content → Other User Content** (messages to the universe) — App
  Functionality. Not for tracking.
- **Identifiers → User ID** — App Functionality / account.
- The deposited AI credential is stored for functionality; not sold; not for ads.
- **Tracking:** No. **Third-party ads:** No.

The generated app also carries `NSMicrophoneUsageDescription` with this exact
purpose: "TinyAssets uses the microphone only while voice conversation is active
so you can speak with your universe." This stages the native permission prompt;
it does **not** by itself make voice release-ready. Keep realtime voice dark until
a physical-device TestFlight run proves that capture stops and the microphone is
released whenever the app backgrounds or the conversation ends.

Before answering App Privacy for a voice-enabled build, re-evaluate **Audio Data**
and **Other User Content** against the OpenAI retention configuration actually in
production. TinyAssets does not persist raw audio and does retain the canonical
conversation text, but those facts alone do not establish the complete disclosure
for data processed by the provider. The account holder must approve the truthful
answers shown in App Store Connect before submission.

---

## 6. Screenshots (App Store Connect requires per device size)

The ordered capture contract and accepted 6.9-inch pixel sizes are committed at
[`app-store-assets/screenshot-manifest.json`](app-store-assets/screenshot-manifest.json).

- iPhone 6.7" (or 6.9") screenshots, captured from the app (sign-in, a universe
  conversation, the Connect view). The two committed Play captures under
  `docs/ops/play-assets/screenshots/` are 1080×1920 and **cannot** be uploaded as
  App Store screenshots. Capture fresh iPhone-sized images from the signed app;
  do not resize or frame the Android captures as if they were iPhone output.
- App icon: committed 1024×1024 `mobile/resources/icon.png`; the release workflow
  installs and validates it through `scripts/add_ios_assets.py`.

---

## 7. Test, submit, release, and roll back

1. App Store Connect → **My Apps → +** → New App (name `TinyAssets`, bundle
   `io.tinyassets.app`, SKU, primary language).
2. Fill the listing (§4), App Privacy (§5), screenshots + icon (§6).
3. Upload the build (Xcode Archive → Distribute, or CI) → it appears under
   TestFlight + the app version.
4. **TestFlight** internal testing → verify sign-in → connect → chat on a device.
   If voice is enabled in that build, use a physical iPhone to verify start/stop,
   permission denial, interruption, and backgrounding; confirm the microphone is
   released in every stop path before proceeding.
5. Select the build for the App Store version and choose **Manually release this
   version**. The founder then makes the separate **Submit for Review** decision.
6. After approval, check the production web health and the TestFlight critical
   flow again, then have the founder click **Release This Version**. Watch the
   first hour for sign-in failures, native OAuth return failures, blank/offline
   shells, and `/mcp/app` server errors.

The first public version is a manual release. For later updates, use Apple's
7-day phased release (1% → 2% → 5% → 10% → 20% → 50% → 100%) and pause on any
new crash, auth failure, or broken critical flow. Phased release controls
automatic updates only; anyone can still manually download the current version.

Rollback has two different shapes:

- A web-app regression needs no store binary: revert/deploy the compatible
  `/mcp/app` version and verify the public endpoint and real mobile flow.
- A native-shell regression cannot restore the previous App Store binary. Pause
  a phased update when available; for a first-version emergency, make the app
  unavailable for new downloads and submit a fixed higher build/version. Existing
  installs remain, so server compatibility with the last released shell is the
  immediate containment mechanism.

References: Apple's current [manual release
options](https://developer.apple.com/help/app-store-connect/manage-your-apps-availability/select-an-app-store-version-release-option/),
[phased release](https://developer.apple.com/help/app-store-connect/update-your-app/release-a-version-update-in-phases),
and [unavailability procedure](https://developer.apple.com/help/app-store-connect/manage-your-apps-availability/make-a-version-unavailable-for-download/).

---

## Status checklist

- [x] iOS platform wired into the Capacitor project (`add:ios`/`sync:ios` scripts, `@capacitor/ios` dep)
- [x] `tinyassets://` URL scheme patch (`scripts/add_ios_scheme.py`)
- [x] Microphone purpose staged in generated `Info.plist` (voice remains dark)
- [x] Exempt OS-provided HTTPS/TLS export declaration staged in generated `Info.plist`
- [ ] Voice: physical-iPhone background/stop proof + privacy re-evaluation
- [x] CI compile-check (`ios-build.yml`)
- [x] Native TinyAssets icon/splash install, with template-drift checks
- [x] Manual signed IPA + opt-in TestFlight workflow (`ios-release.yml`)
- [x] Listing content + App Privacy answers (§4, §5)
- [x] Apple-specific metadata, age-rating/export drafts, screenshot manifest, and device checklist
- [x] Founder: Apple Developer Program enrollment + $99 (§0)
- [x] Apple: membership activated; portal shows Team ID and renewal date (2026-09-03)
- [x] Apple: explicit App ID `io.tinyassets.app` registered and verified (2026-09-03)
- [ ] Founder: review the new App Store Connect Terms of Service; then create the app record (§0)
- [x] Protected `app-store` environment: founder approval + `main` only (§3)
- [ ] Founder: signing assets / API key stored in `app-store` (§3)
- [ ] Screenshots captured (§6)
- [ ] Build uploaded → TestFlight verified → submitted/manual release (§7)
