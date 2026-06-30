$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Desktop = [Environment]::GetFolderPath("Desktop")
$Icon = Join-Path $RepoRoot "tinyassets\desktop\app.ico"

function New-Shortcut {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$TargetPath,
        [string]$Arguments = "",
        [string]$WorkingDirectory = $RepoRoot,
        [string]$Description = ""
    )

    $shortcutPath = Join-Path $Desktop "$Name.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $TargetPath
    $shortcut.Arguments = $Arguments
    $shortcut.WorkingDirectory = $WorkingDirectory
    $shortcut.Description = $Description
    if (Test-Path $Icon) {
        $shortcut.IconLocation = $Icon
    }
    $shortcut.Save()
    Write-Host "Created $shortcutPath"
}

$PowerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$AndroidLauncher = Join-Path $PSScriptRoot "tinyassets-android.ps1"
$IosLauncher = Join-Path $PSScriptRoot "tinyassets-ios.ps1"
$DesktopLauncher = Join-Path $PSScriptRoot "tinyassets-desktop.ps1"

New-Shortcut `
    -Name "TinyAssets Android" `
    -TargetPath $PowerShell `
    -Arguments "-NoLogo -ExecutionPolicy Bypass -NoExit -File `"$AndroidLauncher`"" `
    -Description "Open the TinyAssets Android project"

New-Shortcut `
    -Name "TinyAssets iOS" `
    -TargetPath $PowerShell `
    -Arguments "-NoLogo -ExecutionPolicy Bypass -NoExit -File `"$IosLauncher`"" `
    -Description "Open the TinyAssets iOS project and setup docs"

New-Shortcut `
    -Name "TinyAssets Desktop" `
    -TargetPath $PowerShell `
    -Arguments "-NoLogo -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$DesktopLauncher`"" `
    -Description "Start the TinyAssets desktop tray/server"
