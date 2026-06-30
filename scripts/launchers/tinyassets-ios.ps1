$ErrorActionPreference = "Continue"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$IosDir = Join-Path $RepoRoot "clients\ios"
$Readme = Join-Path $IosDir "README.md"
$SetupDoc = Join-Path $RepoRoot "docs\reference\mobile-app-setup.md"

Write-Host "TinyAssets iOS" -ForegroundColor Cyan
Write-Host "Project: $IosDir"
Write-Host ""

$xcodebuild = Get-Command xcodebuild -ErrorAction SilentlyContinue
if ($xcodebuild) {
    Write-Host "xcodebuild is available. Opening project folder."
} else {
    Write-Host "iOS Simulator builds require macOS with Xcode 16+." -ForegroundColor Yellow
    Write-Host "This Windows shortcut opens the iOS project and setup docs so the same folder can be moved or opened on a Mac."
}

try {
    Set-Clipboard -Value $IosDir
    Write-Host "Copied iOS project path to clipboard."
} catch {
    Write-Host "Could not copy path to clipboard."
}

Start-Process explorer.exe -ArgumentList "`"$IosDir`""
if (Test-Path $Readme) {
    Start-Process notepad.exe -ArgumentList "`"$Readme`""
}
if (Test-Path $SetupDoc) {
    Start-Process notepad.exe -ArgumentList "`"$SetupDoc`""
}

Write-Host ""
Write-Host "On a Mac:"
Write-Host "  cd clients/ios"
Write-Host "  open TinyAssets.xcodeproj"
Write-Host "  ./scripts/build-simulator.sh"
