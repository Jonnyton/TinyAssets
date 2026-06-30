$ErrorActionPreference = "Continue"

Write-Host "TinyAssets Android toolchain check"

Write-Host "`nJava:"
try {
    java -version
} catch {
    Write-Host "java not found"
}

Write-Host "`nAndroid SDK:"
if ($env:ANDROID_SDK_ROOT) {
    Write-Host "ANDROID_SDK_ROOT=$env:ANDROID_SDK_ROOT"
} elseif ($env:ANDROID_HOME) {
    Write-Host "ANDROID_HOME=$env:ANDROID_HOME"
} else {
    Write-Host "ANDROID_SDK_ROOT / ANDROID_HOME not set"
}

Write-Host "`nadb:"
try {
    adb version
    adb devices -l
} catch {
    Write-Host "adb not found"
}

Write-Host "`nGradle wrapper:"
if (Test-Path ".\gradlew.bat") {
    .\gradlew.bat --version
} else {
    Write-Host "gradlew.bat not found. Generate it with Gradle 9.4.1 or open the project in Android Studio."
}
