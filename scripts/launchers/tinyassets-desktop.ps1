$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$SilentLauncher = Join-Path $RepoRoot "start-tinyassets-server.vbs"
$ConsoleLauncher = Join-Path $RepoRoot "start-tinyassets-server.bat"

if (Test-Path $SilentLauncher) {
    Start-Process -FilePath "wscript.exe" -ArgumentList "`"$SilentLauncher`"" -WorkingDirectory $RepoRoot
    return
}

if (Test-Path $ConsoleLauncher) {
    Start-Process -FilePath $ConsoleLauncher -WorkingDirectory $RepoRoot
    return
}

throw "TinyAssets desktop launcher was not found in $RepoRoot."
