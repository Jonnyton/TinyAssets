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

FAIL CLOSED: emptiness is proven only AFTER access is acquired, and a
directory whose contents cannot be enumerated is treated as non-empty.
Get-ChildItem -ErrorAction SilentlyContinue reports Access Denied as an
empty result, so checking emptiness BEFORE takeown passed on exactly the
locked directories this script targets (found by cross-family review
2026-08-26, before the script was ever run with -Apply).

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
    [switch]   $Apply,
    [switch]   $IncludeTestResidue
)

$ErrorActionPreference = 'Continue'

# $PSScriptRoot is not reliably bound inside a param() default on PS 5.1, so the
# repo-parent default is resolved here instead.
if (-not $Root) {
    $repo = Split-Path -Parent $PSScriptRoot
    $Root = Split-Path -Parent $repo
}

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($id)
$elevated = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

# WARN, do not gate. IsInRole is a PREDICTION about whether the deletes will
# work; takeown's actual result is EVIDENCE. An earlier version refused to run
# when this returned $false, which stopped a genuinely elevated session dead
# (reported 2026-08-26 from an elevated prompt). Since every delete is already
# fail-closed on provable emptiness, attempting and reporting the real outcome
# is strictly better than declining based on a guess.
if ($Apply -and -not $elevated) {
    Write-Warning @"
Not detected as elevated (running as $($id.Name)).
Proceeding anyway: the check can be wrong, and each delete is independently
gated on proving the directory is empty. If takeown cannot reach these
directories you will see FAIL lines with the actual ACL below -- that is the
real answer, not this warning.
"@
}

# Auto-protect anything git still knows about. A registered worktree is live
# work, and no cleanup script should be able to delete it by omission from a
# hand-typed keep-list.
$registered = @()
try {
    $repoRoot = Split-Path -Parent $PSScriptRoot
    $registered = git -C $repoRoot worktree list --porcelain 2>$null |
        Where-Object { $_ -like 'worktree *' } |
        ForEach-Object { Split-Path -Leaf ($_ -replace '^worktree ', '') }
} catch { }

$protected = @($Keep) + @($registered) | Where-Object { $_ } | Select-Object -Unique
if ($protected) { Write-Host "Protected: $($protected -join ', ')`n" }

$targets = Get-ChildItem -Path (Join-Path $Root $Filter) -Directory -ErrorAction SilentlyContinue |
    Where-Object { $protected -notcontains $_.Name }

if (-not $targets) { Write-Host 'Nothing to clear.'; exit 0 }

$cleared = 0; $failed = 0; $skipped = 0

function Test-DirectoryEmpty {
    <#
      Returns "empty", "has-files:<n>", or "unreadable".

      Only "empty" permits deletion. The three states are distinct on purpose:
      a dry run must be able to tell an operator that a directory holding real
      work will be SKIPPED, rather than lumping it in with the locked ones.

      FAIL CLOSED. Get-ChildItem -ErrorAction SilentlyContinue turns Access
      Denied into an EMPTY RESULT, which is indistinguishable from "no files".
      That is precisely the state these locked directories are in, so the
      original guard passed on every target it was meant to protect and the
      script went on to take ownership and recursively delete. An enumeration
      that errors means UNKNOWN, and unknown is never empty.
    #>
    param([string] $Path)

    $enumErrors = $null
    $items = @(Get-ChildItem -LiteralPath $Path -Recurse -Force `
        -ErrorAction SilentlyContinue -ErrorVariable enumErrors)
    if ($enumErrors) { return "unreadable" }     # cannot see inside -> never "empty"
    $files = @($items | Where-Object { -not $_.PSIsContainer })
    if ($files.Count -eq 0) { return "empty" }

    # A directory holding ONLY test output is still residue. These husks are not
    # empty -- they hold pytest caches and per-run temp trees, sometimes
    # thousands of files -- but none of it is work. Classified separately from
    # "has-files" so the operator opts in explicitly via -IncludeTestResidue and
    # anything with even one non-residue file still fails closed.
    # EXACT names only. An earlier version matched with StartsWith on prefixes
    # like ".claude" and ".tmp", which also matches ".claude/agent-memory" --
    # real, irreplaceable content -- and would have let -IncludeTestResidue
    # delete it recursively. Prefix matching cannot express "test output" safely,
    # so this is an exact allowlist and nothing else counts as residue.
    $residueRoots = @(".pytest_cache", ".pytest_tmp", ".tmp-pytest",
                      "__pycache__", ".ruff_cache", ".mypy_cache")
    $residuePatterns = @("^\.pytest_tmp_[A-Za-z0-9]+$", "^\.test-run-[A-Za-z0-9._-]+$",
                         "^\.tmp$", "^_test_tmp$", "^_test_tmp_[A-Za-z0-9._-]+$")
    $foreign = @($files | Where-Object {
        $rel = $_.FullName.Substring($Path.Length).TrimStart("\")
        $first = ($rel -split "\\")[0]
        $ok = $residueRoots -contains $first
        if (-not $ok) {
            foreach ($pat in $residuePatterns) { if ($first -match $pat) { $ok = $true; break } }
        }
        -not $ok
    })
    if ($foreign.Count -eq 0) { return "test-residue:$($files.Count)" }
    return "has-files:$($foreign.Count)"
}

foreach ($dir in $targets) {
    if (-not $Apply) {
        switch -Wildcard (Test-DirectoryEmpty -Path $dir.FullName) {
            "empty"      { Write-Host ("WOULD CLEAR  {0} (provably empty)" -f $dir.Name) }
            "has-files*" { Write-Host ("WOULD SKIP   {0} - {1}; holds real content" -f $dir.Name, $_) -ForegroundColor Yellow }
            "test-residue*" {
                if ($IncludeTestResidue) {
                    Write-Host ("WOULD CLEAR  {0} - {1} (test output only)" -f $dir.Name, $_)
                } else {
                    Write-Host ("WOULD SKIP   {0} - {1}; re-run with -IncludeTestResidue to clear" -f $dir.Name, $_) -ForegroundColor Yellow
                }
            }
            default      { Write-Host ("WOULD CLEAR  {0} (unreadable now; re-checked after takeown, skipped if not empty)" -f $dir.Name) }
        }
        continue
    }

    # /A assigns ownership to Administrators rather than the running user --
    # more reliable when the existing owner is a sandbox group.
    & takeown /F $dir.FullName /A /R /D Y > $null 2>&1
    # /reset restores inheritance from the parent, which already grants
    # Administrators Full.
    & icacls $dir.FullName /reset /T /C /Q > $null 2>&1

    # THE GATE. Now that access should exist, prove emptiness. If it is still
    # unreadable, or it holds files, do not delete -- report and move on.
    $verdict = Test-DirectoryEmpty -Path $dir.FullName
    $clearable = ($verdict -eq "empty") -or
                 ($IncludeTestResidue -and $verdict -like "test-residue*")
    if (-not $clearable) {
        if ($verdict -like "test-residue*") {
            Write-Host ("SKIP  {0} - {1}; re-run with -IncludeTestResidue" -f $dir.Name, $verdict) -ForegroundColor Yellow
        } elseif ($verdict -like "has-files*") {
            Write-Host ("SKIP  {0} - {1}; this is not sandbox residue" -f $dir.Name, $verdict) -ForegroundColor Yellow
        } else {
            Write-Host ("SKIP  {0} - still unreadable after takeown; refusing to delete blind" -f $dir.Name) -ForegroundColor Yellow
        }
        $skipped++
        continue
    }

    Remove-Item $dir.FullName -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path $dir.FullName) {
        Write-Host ("FAIL  {0} - still present after takeown+icacls" -f $dir.Name) -ForegroundColor Red
        Write-Host ("        running as: {0} (elevated={1})" -f $id.Name, $elevated)
        & takeown /F $dir.FullName /A 2>&1 | Select-Object -First 2 | ForEach-Object { "        takeown: $_" }
        & icacls $dir.FullName 2>&1 | Select-Object -First 4 | ForEach-Object { "        acl: $_" }
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
