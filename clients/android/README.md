# TinyAssets Android

Native Android starter for TinyAssets.

## Build

Prerequisites:

- JDK 17
- Android SDK platform-tools and Build Tools
- Android Studio or Gradle 9.4.1 to generate the wrapper

From this directory:

```powershell
.\scripts\doctor.ps1
gradle wrapper --gradle-version 9.4.1
.\gradlew.bat :app:assembleDebug --console=plain
```

Runtime device flow:

```powershell
adb devices -l
.\gradlew.bat :app:installDebug --console=plain
adb -s <serial> shell monkey -p io.tinyassets.mobile 1
adb -s <serial> shell am start -W -a android.intent.action.VIEW -d "tinyassets://auth/callback?code=dev-code&state=<state-from-active-request>" io.tinyassets.mobile
```

The app currently opens WorkOS AuthKit with PKCE, handles
`tinyassets://auth/callback`, and shows a one-screen universe conversation
surface. It does not send local messages or simulate a persona reply. Token
exchange, Android Keystore-backed storage, founder-universe resolution, and MCP
chat routing remain the next slice.
