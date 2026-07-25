param(
    [Parameter(Mandatory = $true)][string]$Installer
)

$ErrorActionPreference = "Stop"
$installerPath = (Resolve-Path -LiteralPath $Installer).Path
$installRoot = Join-Path $env:LOCALAPPDATA "Programs\TinyAssets"
$dataRoot = Join-Path $env:APPDATA "TinyAssets"
$tray = Join-Path $installRoot "TinyAssets.exe"
$uninstaller = Join-Path $installRoot "unins000.exe"
$startup = Join-Path $env:APPDATA `
    "Microsoft\Windows\Start Menu\Programs\Startup\TinyAssets.lnk"
$marker = Join-Path $dataRoot "clean-machine-content-marker.txt"

function Invoke-Installer {
    $process = Start-Process -FilePath $installerPath -ArgumentList @(
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/TASKS=autostart"
    ) -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw "installer failed with exit code $($process.ExitCode)"
    }
}

Invoke-Installer
if (-not (Test-Path -LiteralPath $tray -PathType Leaf)) {
    throw "installed tray executable is missing"
}
if (-not (Test-Path -LiteralPath $startup -PathType Leaf)) {
    throw "installer-owned autostart entry is missing"
}

New-Item -ItemType Directory -Force -Path $dataRoot | Out-Null
Set-Content -LiteralPath $marker -Value "preserve me"
$env:TINYASSETS_DATA_DIR = $dataRoot
$probe = Start-Process -FilePath $tray `
    -ArgumentList @("--packaged-role", "health-probe") -Wait -PassThru
if ($probe.ExitCode -ne 0) {
    throw "packaged health probe failed with exit code $($probe.ExitCode)"
}

# Same-version repair must converge without a duplicate startup entry.
Invoke-Installer
$startupEntries = @(Get-ChildItem -LiteralPath (Split-Path $startup) `
    -Filter "TinyAssets.lnk")
if ($startupEntries.Count -ne 1) {
    throw "repair produced $($startupEntries.Count) autostart entries"
}

$uninstall = Start-Process -FilePath $uninstaller -ArgumentList @(
    "/VERYSILENT",
    "/SUPPRESSMSGBOXES",
    "/NORESTART"
) -Wait -PassThru
if ($uninstall.ExitCode -ne 0) {
    throw "uninstaller failed with exit code $($uninstall.ExitCode)"
}
if (Test-Path -LiteralPath $tray) {
    throw "uninstaller left the tray executable behind"
}
if (Test-Path -LiteralPath $startup) {
    throw "uninstaller left the autostart entry behind"
}
if (Test-Path -LiteralPath (Join-Path $dataRoot "updates")) {
    throw "uninstaller left updater program files behind"
}
if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) {
    throw "uninstaller deleted user-owned content"
}
