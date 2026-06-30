# TinyAssets mobile app setup

Status: initial native scaffold, 2026-06-30.

## Product boundary

TinyAssets mobile clients are native control surfaces for the same MCP resource
server used by chatbot clients. They do not introduce a mobile-only backend,
mobile-only founder id, or mobile-only universe shape.

Shared constants in both clients:

- MCP resource: `https://tinyassets.io/mcp`
- Protected resource metadata: `https://tinyassets.io/.well-known/oauth-protected-resource`
- Staging AuthKit domain: `inventive-van-62-staging.authkit.app`

The next auth slice should use WorkOS/OIDC and platform credential storage:

- iOS: Keychain.
- Android: Android Keystore-backed encrypted storage.

Provider API keys must not live in either mobile client.

## iPhone client

Path: `clients/ios`

Stack:

- SwiftUI
- App Intents and App Shortcuts
- Xcode project `TinyAssets.xcodeproj`
- Bundle id `io.tinyassets.mobile`
- iOS deployment target 17.0

Build on macOS:

```bash
cd clients/ios
open TinyAssets.xcodeproj
./scripts/build-simulator.sh
```

The current Windows host cannot verify this build because `xcrun`/Xcode are not
available.

## Android client

Path: `clients/android`

Stack:

- Kotlin
- Jetpack Compose
- Material 3
- Gradle Kotlin DSL
- Version catalog
- Static shortcut and deep-link routing

Build on a machine with Android Studio or Android SDK tools:

```powershell
cd clients/android
.\scripts\doctor.ps1
gradle wrapper --gradle-version 9.4.1
.\gradlew.bat :app:assembleDebug --console=plain
```

Runtime check:

```powershell
adb devices -l
.\gradlew.bat :app:installDebug --console=plain
adb -s <serial> shell monkey -p io.tinyassets.mobile 1
adb -s <serial> shell am start -W -a android.intent.action.VIEW -d "tinyassets://mcp" io.tinyassets.mobile
```

The current Windows host cannot verify this build yet. It has Java 8 only, no
Gradle command, no `adb`, and no `ANDROID_HOME` / `ANDROID_SDK_ROOT`.

## Android plugin source stamp

User-provided source: `https://github.com/SangkuOh/build-androidos-apps`

Checked on 2026-06-30:

- `main` / `v0.1.3`: `fab84ec0ae36647dabf701c3bddf57d2fadaa168`
- License: MIT
- Session installer status: not available in this Codex plugin installer list.
- Applied guidance manually: Gradle wrapper first, explicit adb target, Compose
  state ownership, Material 3, small external action surface, and runtime proof
  before claiming device success.

Install for a future Codex thread:

```bash
codex plugin marketplace add SangkuOh/build-androidos-apps --ref v0.1.3
codex plugin add build-androidos-apps@build-androidos-apps
codex plugin list
```

Start a new Codex thread after installation so the plugin skills are discoverable.

## First follow-up slices

1. Generate and commit the Android Gradle wrapper after JDK 17 is available.
2. Verify the iOS project on macOS with Xcode and set XcodeBuildMCP defaults.
3. Add WorkOS OIDC login on both clients, storing tokens only in platform-secure storage.
4. Add one smoke UI test per platform for launching the MCP status surface.
5. Add app icons before distribution work.
