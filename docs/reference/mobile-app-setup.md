# TinyAssets mobile app setup

Status: initial native scaffold, 2026-06-30.

## Product boundary

TinyAssets mobile clients are native control surfaces for the same MCP resource
server used by chatbot clients. They do not introduce a mobile-only backend,
mobile-only founder id, or mobile-only universe shape.

OpenSpec alignment: this work belongs to `openspec/changes/universe-personification`.
Native mobile is a first-class TinyAssets surface: the app opens as a
WorkOS-bound universe chat surface, and the chat is the universe's
personification once server-side authorization-before-voice routing is
available. This scaffold completes task 2.10 only; it does not complete
authorization-before-voice, visitor tier binding, token exchange, or real MCP
message routing.

Basic user experience:

1. User opens the iPhone or Android app.
2. The first screen is the universe chat surface.
3. User taps "Continue with WorkOS".
4. WorkOS AuthKit handles login and redirects back to the app.
5. The app exchanges the authorization code, stores tokens in platform-secure
   storage, resolves the founder's main universe, and opens chat with that
   universe's agent.

Current scaffold state:

- PKCE authorization URL construction exists on both platforms.
- `tinyassets://auth/callback` redirect handling exists on both platforms.
- The chat shell exists on both platforms.
- Token exchange, secure token persistence, founder-universe resolution, and
  real MCP chat routing are still next slices.
- Chat messages in the scaffold stay local until MCP chat routing lands.

Shared constants in both clients:

- MCP resource: `https://tinyassets.io/mcp`
- Protected resource metadata: `https://tinyassets.io/.well-known/oauth-protected-resource`
- Staging AuthKit domain: `inventive-van-62-staging.authkit.app`
- Staging WorkOS client id: `client_01KW15P07QYSMF9CY4XXXJN520`
- Development redirect URI: `tinyassets://auth/callback`

The next auth slice should use WorkOS/OIDC and platform credential storage:

- iOS: Keychain.
- Android: Android Keystore-backed encrypted storage.

Provider API keys must not live in either mobile client.

The custom-scheme redirect is a development scaffold. Before distribution,
prefer claimed HTTPS Universal Links / Android App Links for the OAuth redirect
if WorkOS and store-review constraints allow it, and keep the custom scheme as a
fallback only if explicitly accepted.

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
adb -s <serial> shell am start -W -a android.intent.action.VIEW -d "tinyassets://auth/callback?code=dev-code&state=<state-from-active-request>" io.tinyassets.mobile
```

The current Windows host cannot verify this build yet. It has Java 8 only, no
Gradle command, no `adb`, and no `ANDROID_HOME` / `ANDROID_SDK_ROOT`.

## WorkOS setup checklist

- [ ] Allowlist `tinyassets://auth/callback` for staging native development.
- [ ] Decide production redirect shape: claimed HTTPS app link/universal link
      preferred; custom scheme only if accepted deliberately.
- [ ] Confirm `resource=https://tinyassets.io/mcp` produces the expected `aud`.
- [ ] Exchange authorization code with PKCE verifier.
- [ ] Store access/refresh tokens only in Keychain / Android Keystore-backed storage.
- [ ] Resolve the caller's main universe from the authenticated founder.
- [ ] Route chat messages through the MCP server to the caller's universe agent.
- [ ] Clear all local tokens and pending PKCE state on sign out.

Primary references checked 2026-06-30:

- WorkOS AuthKit MCP docs: `https://workos.com/docs/authkit/mcp`
- WorkOS authorization URL docs: `https://workos.com/docs/reference/authkit/authentication/get-authorization-url`
- WorkOS redirect URI docs: `https://workos.com/docs/sso/redirect-uris`
- WorkOS OAuth 2.1 guidance: `https://workos.com/blog/oauth-2-1-whats-new`
- RFC 8252 OAuth 2.0 for Native Apps: `https://datatracker.ietf.org/doc/html/rfc8252`

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
3. Add WorkOS code exchange on both clients, storing tokens only in platform-secure storage.
4. Add founder-main-universe resolution and MCP chat routing.
5. Add one smoke UI test per platform for launching the signed-in chat surface.
6. Add app icons before distribution work.
