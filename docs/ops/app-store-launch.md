# Apple App Store launch — runbook

The iOS counterpart of `google-play-launch.md`. The iPhone app is the SAME
Capacitor shell over `https://tinyassets.io/mcp/app` — one shared core with the
Android + web + desktop surfaces. Staged so the founder's only actions are the
Apple Developer account + payment + signing assets + the final submit.

Bundle id: **`io.tinyassets.app`** (matches `mobile/capacitor.config.json`
`appId`; permanent once published).

> **Picking this up cold? Read [`mobile-launch-handoff.md`](mobile-launch-handoff.md)
> first.** This file is the procedure; that one is where both platforms actually
> stand. The short version for iOS: nothing here can ship until the founder enrols
> in the Apple Developer Program, and that is the long pole.

---

## 0. Founder-only actions (I cannot do these)

| Step | Action | Where |
|---|---|---|
| Account | Enroll in the **Apple Developer Program** ($99/year). | https://developer.apple.com/programs/enroll/ |
| Payment | Authorize the $99/yr fee. | during enrollment |
| Signing assets | Create a Distribution certificate + an App Store provisioning profile (or let Xcode "Automatically manage signing"), and an **App Store Connect API key** for CI upload. Provide them as repo secrets (§3). | developer.apple.com / App Store Connect |
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
change (no Apple assets needed). A signed archive + TestFlight upload is added once
the founder provides the signing secrets (§3) — same pattern as the Android release.

---

## 2. Local build (needs a Mac + Xcode)

```bash
cd mobile
npm ci
npm run add:ios          # cap add ios (generates ios/; writes Package.swift, NOT a Podfile)
npm run sync:ios         # cap sync ios
python3 scripts/add_ios_scheme.py   # registers the tinyassets:// URL scheme
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

## 3. Repo secrets for CI-signed builds (optional; enables CI upload)

| Secret | Value |
|---|---|
| `APPLE_DISTRIBUTION_CERT_P12_B64` | base64 of your Distribution cert `.p12` |
| `APPLE_DISTRIBUTION_CERT_PASSWORD` | the `.p12` password |
| `APPLE_PROVISIONING_PROFILE_B64` | base64 of the App Store provisioning profile |
| `APP_STORE_CONNECT_API_KEY_ID` / `_ISSUER_ID` / `_KEY_B64` | App Store Connect API key for `xcrun altool`/`notarytool` upload |

(Until these exist, CI compile-checks only; you upload via Xcode from a Mac.)

---

## 4. App Store listing content (copy-paste)

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

---

## 6. Screenshots (App Store Connect requires per device size)

- iPhone 6.7" (or 6.9") screenshots, ≥3 — captured from the app (sign-in, a
  universe conversation, the Connect view). Same procedure as
  `google-play-launch.md` §10; staged in `docs/ops/play-assets/screenshots/`.
- App icon: 1024×1024 (from `mobile` capacitor assets, `npm run assets:ios`).

---

## 7. Submit

1. App Store Connect → **My Apps → +** → New App (name `TinyAssets`, bundle
   `io.tinyassets.app`, SKU, primary language).
2. Fill the listing (§4), App Privacy (§5), screenshots + icon (§6).
3. Upload the build (Xcode Archive → Distribute, or CI) → it appears under
   TestFlight + the app version.
4. **TestFlight** internal testing → verify sign-in → connect → chat on a device.
5. Select the build for the App Store version → **Submit for Review** → release
   (auto or manual).

---

## Status checklist

- [x] iOS platform wired into the Capacitor project (`add:ios`/`sync:ios` scripts, `@capacitor/ios` dep)
- [x] `tinyassets://` URL scheme patch (`scripts/add_ios_scheme.py`)
- [x] CI compile-check (`ios-build.yml`)
- [x] Listing content + App Privacy answers (§4, §5)
- [ ] Founder: Apple Developer Program enrollment + $99 (§0)
- [ ] Founder: signing assets / API key (§3) — or build from a Mac (§2)
- [ ] Screenshots captured (§6)
- [ ] Build uploaded → TestFlight verified → submitted (§7)
