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
```
