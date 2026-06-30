$ErrorActionPreference = "Stop"
Push-Location (Join-Path $PSScriptRoot "..")
try {
    if (Test-Path ".\gradlew.bat") {
        .\gradlew.bat :app:assembleDebug --console=plain
    } else {
        gradle :app:assembleDebug --console=plain
    }
} finally {
    Pop-Location
}
