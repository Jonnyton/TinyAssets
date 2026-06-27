# Install TinyAssets repo-level git hooks into Git's hooks directory.
#
# Hooks live canonically at scripts/git-hooks/ and are copied into
# the path reported by `git rev-parse --git-path hooks`. Re-run this
# script whenever the canonical hooks change. Zero dependencies beyond
# git + PowerShell.

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$source = Join-Path $root "scripts\git-hooks"
$gitHooksPath = (& git -C $root rev-parse --git-path hooks) 2>$null
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($gitHooksPath)) {
    throw "Could not resolve git hooks path from: $root"
}
$gitHooksPath = $gitHooksPath.Trim()
if ([System.IO.Path]::IsPathRooted($gitHooksPath)) {
    $target = $gitHooksPath
} else {
    $target = Join-Path $root $gitHooksPath
}

if (!(Test-Path $source)) {
    throw "Canonical hooks dir not found: $source"
}
if (!(Test-Path $target)) {
    New-Item -ItemType Directory -Force -Path $target | Out-Null
}

$installed = 0
Get-ChildItem -File $source | ForEach-Object {
    $name = $_.Name
    $destPath = Join-Path $target $name
    Copy-Item -Force $_.FullName $destPath
    # On Windows, git-bash respects the file contents regardless of
    # NTFS exec bit, so no chmod needed. On POSIX, mark executable.
    if ($IsLinux -or $IsMacOS) {
        chmod +x $destPath
    }
    $installed++
    Write-Output "Installed: $name"
}

Write-Output "$installed git hook(s) installed in $target"
