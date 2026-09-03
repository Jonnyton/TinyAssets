# TinyAssets — Android app (Capacitor)

A native Android app that wraps the live TinyAssets web app. It is a thin,
maintainable **Capacitor** shell whose WebView loads `https://tinyassets.io/mcp/app`
(configured in `capacitor.config.json` → `server.url`). Because that page, the
`/mcp` API, and the AuthKit sign-in all live on the same origin (`tinyassets.io`),
the WorkOS OAuth round-trip stays inside the app and Just Works — no deep-link
plumbing. Web-app changes ship instantly (no store resubmit); the store build only
changes when the native shell, icon, or config change.

> **Architecture:** app shell = Capacitor + a few native plugins (splash, status
> bar, app lifecycle). Product logic (sign-in, connect subscription, chat) is the
> web app, reused verbatim. iOS can be added later with `npx cap add ios` — the
> same `server.url` works.

## What I (the app author) can build vs. what needs you

**Built here:** the Capacitor project, config, native-plugin set, loading/offline
fallback page, and this runbook. It compiles to an APK/AAB with the standard
commands below.

**Needs you (identity / accounts / payment — I can't do these):**
- A **Google Play Developer** account ($25 one-time) → https://play.google.com/console
- An **upload keystore** (you generate + keep it secret; it signs your uploads)
- The store listing + the actual upload & submission for review

## Prerequisites (on your build machine)

- **Node.js 22+** and npm (`@capacitor/cli@8` declares `engines.node >= 22`)
- **Android Studio** (bundles the Android SDK + platform tools) — https://developer.android.com/studio
- **JDK 21** (Android Studio bundles one; or install Temurin 21). Capacitor 8
  compiles its Java at source/target 21 — JDK 17 fails with
  `error: invalid source release: 21`.
- Set `ANDROID_HOME` / accept SDK licenses (`sdkmanager --licenses`)

## First-time setup

> **Upgrading an existing checkout?** Delete `mobile/android` first. It is
> gitignored generated output, and `cap sync` *preserves* `android/variables.gradle`
> — so a project generated under Capacitor 6 silently keeps `minSdkVersion = 22`
> and compile/target 34 even after the dependency bump, which Play now rejects.
> `cap add android` refuses outright rather than overwrite, so nothing is lost by
> removing it. CI is unaffected: it always starts from a clean checkout.


```bash
cd mobile
npm install
rm -rf android               # REQUIRED if you generated it before Capacitor 8
npx cap add android          # generates the android/ native project
npx cap sync android         # copies www/ + config into the native project
```

## App icon + splash (optional but recommended before release)

Put a square **1024×1024 PNG** at `resources/icon.png` (and optionally
`resources/splash.png` 2732×2732), then:

```bash
npx @capacitor/assets generate --android
npx cap sync android
```

## Build & test a debug APK (on a device/emulator)

```bash
npx cap run android          # builds + installs on a connected device/emulator
# — or —
cd android && ./gradlew assembleDebug
# → android/app/build/outputs/apk/debug/app-debug.apk  (sideload to test)
```

Verify the full loop on the device: **sign in (WorkOS)** → **connect your AI
subscription** → **chat with your universe**.

## Build a release bundle (.aab) for Google Play

1. **Generate an upload keystore** (once; keep it + the passwords safe):
   ```bash
   keytool -genkey -v -keystore tinyassets-upload.jks -keyalg RSA -keysize 2048 \
           -validity 10000 -alias upload
   ```
2. **Point Gradle at it** — create `android/keystore.properties` (do NOT commit):
   ```properties
   storeFile=../../tinyassets-upload.jks
   storePassword=********
   keyAlias=upload
   keyPassword=********
   ```
   and wire it into `android/app/build.gradle` `signingConfigs`/`buildTypes.release`
   (Android Studio → Build → Generate Signed Bundle does this for you via a wizard).
3. **Build the bundle:**
   ```bash
   cd android && ./gradlew bundleRelease
   # → android/app/build/outputs/bundle/release/app-release.aab
   ```

## Submit to Google Play

1. Play Console → **Create app** (name: *TinyAssets*, app or game: App, free).
2. Complete the required declarations (privacy policy URL, data safety, content
   rating, target audience). The app collects a sign-in identity + the AI
   credential the user deposits — declare accordingly.
3. **Create a release** (Internal testing first is fastest) → upload
   `app-release.aab` → roll out. Internal testing reaches your testers in minutes;
   production goes through review (hours–days).
4. Enrolling in **Play App Signing** (recommended default) lets Play manage the
   final signing key; your upload keystore only signs uploads.

## Notes / follow-ups

- `appId` is `io.tinyassets.app` (change in `capacitor.config.json` before first
  publish if you want a different package name — it's permanent once published).
- The WebView allow-list (`server.allowNavigation`) includes `tinyassets.io` and
  `*.authkit.app` so the WorkOS login page loads. If you move AuthKit to a
  production domain, add it there.
- To harden Play review against "minimum functionality," the native plugins here
  give real device integration; a later pass can add push notifications
  (`@capacitor/push-notifications`) for run/agent updates.
- iOS later: `npx cap add ios` + an Apple Developer account ($99/yr) + a Mac/Xcode.
