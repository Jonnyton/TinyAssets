<#
.SYNOPSIS
Remove sandbox-created directories whose ACL locks out the interactive user.

.DESCRIPTION
A sandboxed agent (Codex, Cursor) that points pytest's --basetemp or TMPDIR
inside the checkout creates those directories under a RESTRICTED TOKEN. The
resulting ACL is owned by a sandbox group -- observed 2026-08-26 as
DESKTOP-<host>\CodexSandboxUsers -- with inheritance disabled and no entry for
the interactive user. The effect is not merely "cannot delete": Get-Acl itself
fails with "Attempted to perform an unauthorized operation", and a reboot does
not help because it is an ACL, not a held handle.

Prevention lives in tests/conftest.py, which now refuses to run when pytest's
temp root resolves inside the repo. This script is the cleanup for husks that
already exist.

.NOTES
MUST run ELEVATED. BUILTIN\Administrators holds inherited Full control on the
PARENT directories, which is what lets takeown reach the locked children.

Two bugs in the ad-hoc one-liner this replaces, both fixed here:
  1. "$env:USERNAME:(OI)(CI)F" expands to "(OI)(CI)F" -- PowerShell parses
     $env:USERNAME: as a namespace path and resolves it to empty, so icacls
     silently receives a malformed argument and grants nothing. Braces are
     required: "${env:USERNAME}:(OI)(CI)F". This script sidesteps it entirely
     by using icacls /reset, which needs no principal name.
  2. Piping takeown/icacls to Out-Null hides their failure, so the only visible
     error is the Remove-Item that was doomed by it.

.PARAMETER Root
Directory to scan. Defaults to the repo's parent.

.PARAMETER Keep
Directory names to leave alone. Live worktrees belong here.

.PARAMETER Apply
Actually delete. Without it the script only reports (dry run).

.EXAMPLE
powershell -File scripts/clear_sandbox_temp_dirs.ps1
.EXAMPLE
powershell -File scripts/clear_sandbox_temp_dirs.ps1 -Apply
#>
[CmdletBinding()]
param(
    [string]   $Root   = '',
    [string[]] $Keep   = @(),
    [string]   $Filter = 'wf-*',
    [switch]   $Apply
)

$ErrorActionPreference = 'Continue'

# $PSScriptRoot is not reliably bound inside a param() default on PS 5.1, so the
# repo-parent default is resolved here instead.
if (-not $Root) {
    $repo = Split-Path -Parent $PSScriptRoot
    $Root = Split-Path -Parent $repo
}

$elevated = ([Security.Principal.WindowsPrincipal]`
    [Security.Principal.WindowsIdentity]::GetCurrent()`
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if ($Apply -and -not $elevated) {
    Write-Error @'
Not elevated. BUILTIN\Administrators is the only principal with rights on these
directories; without elevation takeown cannot reach them and every removal will
fail with Access Denied. Re-run from an elevated PowerShell.
'@
    exit 1
}

# Auto-protect anything git still knows about. A registered worktree is live
# work, and no cleanup script should be able to delete it by omission from a
# hand-typed keep-list.
$registered = @()
try {
    $registered = git worktree list --porcelain 2>$null |
        Where-Object { $_ -like 'worktree *' } |
        ForEach-Object { Split-Path -Leaf ($_ -replace '^worktree ', '') }
} catch { }

$protected = @($Keep) + @($registered) | Where-Object { $_ } | Select-Object -Unique
if ($protected) { Write-Host "Protected: $($protected -join ', ')`n" }

$targets = Get-ChildItem -Path (Join-Path $Root $Filter) -Directory -ErrorAction SilentlyContinue |
    Where-Object { $protected -notcontains $_.Name }

if (-not $targets) { Write-Host 'Nothing to clear.'; exit 0 }

$cleared = 0; $failed = 0; $skipped = 0

foreach ($dir in $targets) {
    # Refuse to delete anything holding real files. These husks are empty;
    # a directory with content is someone's work, not sandbox residue.
    $files = @(Get-ChildItem $dir.FullName -Recurse -File -Force -ErrorAction SilentlyContinue)
    if ($files.Count -gt 0) {
        Write-Host ("SKIP  {0} - holds {1} file(s), not empty residue" -f $dir.Name, $files.Count)
        $skipped++
        continue
    }

    if (-not $Apply) {
        Write-Host ("WOULD CLEAR  {0}" -f $dir.Name)
        continue
    }

    # /A assigns ownership to Administrators rather than the running user --
    # more reliable when the existing owner is a sandbox group.
    & takeown /F $dir.FullName /A /R /D Y > $null 2>&1
    # /reset restores inheritance from the parent, which already grants
    # Administrators Full. Simpler and less error-prone than granting a named
    # principal, and it is what the malformed /grant above was reaching for.
    & icacls $dir.FullName /reset /T /C /Q > $null 2>&1

    Remove-Item $dir.FullName -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path $dir.FullName) {
        Write-Host ("FAIL  {0}" -f $dir.Name) -ForegroundColor Red
        & icacls $dir.FullName 2>&1 | Select-Object -First 4 | ForEach-Object { "        $_" }
        $failed++
    } else {
        Write-Host ("CLEARED  {0}" -f $dir.Name) -ForegroundColor Green
        $cleared++
    }
}

if (-not $Apply) {
    Write-Host "`nDry run. Re-run ELEVATED with -Apply to delete."
} else {
    Write-Host "`ncleared=$cleared failed=$failed skipped=$skipped"
    if ($failed -gt 0) { exit 1 }
}
