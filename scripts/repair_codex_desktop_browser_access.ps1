param(
    [string[]] $ThreadIds = @(
        "019ede3b-e609-7d63-b93b-b8607519485d",
        "019ee21d-48ff-73a0-aecf-7fb28616cfa7"
    ),
    [switch] $SkipAcl,
    [switch] $SkipStatePatch,
    [switch] $NoRestart
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string] $Message)
    Write-Host ""
    Write-Host "== $Message =="
}

function Backup-File {
    param([string] $Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    $stamp = Get-Date -Format "yyyyMMddHHmmss"
    $backup = "$Path.bak-browser-access-$stamp"
    Copy-Item -LiteralPath $Path -Destination $backup
    return $backup
}

function Invoke-IcaclsGrant {
    param(
        [string] $Path,
        [string] $Grant
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        Write-Host "skip missing path: $Path"
        return
    }

    Write-Host "grant $Grant on $Path"
    & icacls $Path /grant $Grant /T /C
    if ($LASTEXITCODE -ne 0) {
        throw "icacls failed for $Path with exit code $LASTEXITCODE"
    }
}

function Find-Python {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) {
        return [pscustomobject]@{
            Exe = $cmd.Source
            Args = @()
        }
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return [pscustomobject]@{
            Exe = $py.Source
            Args = @("-3")
        }
    }

    return $null
}

$who = (whoami).Trim()
if ($who -match "codexsandboxoffline") {
    throw "Run this from a normal Windows PowerShell, not from inside a Codex sandbox shell. Current user: $who"
}

$codexHome = Join-Path $env:USERPROFILE ".codex"
$statePath = Join-Path $codexHome ".codex-global-state.json"
$configPath = Join-Path $codexHome "config.toml"
$runtimeRoot = Join-Path $env:LOCALAPPDATA "OpenAI\Codex\runtimes"
$binRoot = Join-Path $env:LOCALAPPDATA "OpenAI\Codex\bin"
$codexTmp = Join-Path $codexHome "tmp"
$nodeReplState = Join-Path $codexHome "node_repl"
$group = "$env:COMPUTERNAME\CodexSandboxUsers"

Write-Step "Stop Codex runtime processes"
Stop-Process -Name Codex,node_repl -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3
$stillRunning = Get-Process -Name Codex,node_repl -ErrorAction SilentlyContinue
if ($stillRunning) {
    $stillRunning | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}
$stillRunning = Get-Process -Name Codex,node_repl -ErrorAction SilentlyContinue
if ($stillRunning) {
    throw "Codex/node_repl processes are still running. Close Codex Desktop and rerun this script."
}

Write-Step "Back up Codex state"
$stateBackup = Backup-File $statePath
$configBackup = Backup-File $configPath
if ($stateBackup) { Write-Host "state backup: $stateBackup" }
if ($configBackup) { Write-Host "config backup: $configBackup" }

if ($SkipAcl) {
    Write-Step "Skip filesystem ACL repair"
    Write-Host "ACL repair skipped by -SkipAcl."
} else {
    Write-Step "Repair filesystem ACLs"
    Invoke-IcaclsGrant -Path $runtimeRoot -Grant "${group}:(OI)(CI)RX"
    Invoke-IcaclsGrant -Path $binRoot -Grant "${group}:(OI)(CI)RX"
    Invoke-IcaclsGrant -Path $codexTmp -Grant "${group}:(OI)(CI)M"
    Invoke-IcaclsGrant -Path $nodeReplState -Grant "${group}:(OI)(CI)M"
}

if (-not $SkipStatePatch) {
    Write-Step "Repair stale per-thread permission state"
    $pythonCmd = Find-Python
    if (-not $pythonCmd) {
        throw "Python was not found on PATH, so the JSON state patch could not run. ACLs were repaired; rerun with Python available or with -SkipStatePatch."
    }

    $env:REPAIR_CODEX_STATE_PATH = $statePath
    $env:REPAIR_CODEX_THREAD_IDS = ($ThreadIds -join ";")
    $patchScript = @'
import json
import os
import time
from pathlib import Path

state = Path(os.environ["REPAIR_CODEX_STATE_PATH"])
thread_ids = [x for x in os.environ.get("REPAIR_CODEX_THREAD_IDS", "").split(";") if x]

data = json.loads(state.read_text(encoding="utf-8-sig"))
atom = data.setdefault("electron-persisted-atom-state", {})
atom.setdefault("agent-mode-by-host-id", {})["local"] = "full-access"
atom.setdefault("preferred-non-full-access-agent-mode-by-host-id", {})["local"] = None

perms = atom.setdefault("heartbeat-thread-permissions-by-id", {})
for tid in thread_ids:
    perms[tid] = {
        "approvalPolicy": "never",
        "approvalsReviewer": "user",
        "sandboxPolicy": {"type": "dangerFullAccess"},
    }

tmp = state.with_name(f".codex-global-state.json.tmp-browser-access-{int(time.time())}")
tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
tmp.replace(state)
print("patched thread ids:", ", ".join(thread_ids) if thread_ids else "(none)")
'@

    $pythonArgs = @($pythonCmd.Args)
    $patchScript | & $pythonCmd.Exe @pythonArgs
}

Write-Step "Verify repaired ACL targets"
$nodeReplExes = Get-ChildItem -LiteralPath $runtimeRoot -Filter node_repl.exe -Recurse -ErrorAction SilentlyContinue
foreach ($exe in $nodeReplExes) {
    Write-Host $exe.FullName
    & icacls $exe.FullName | Select-String -Pattern "CodexSandboxUsers|Successfully processed"
}

Write-Step "Next step"
if ($NoRestart) {
    Write-Host "Codex was left stopped. Start Codex Desktop manually, then ask the thread to probe node_repl."
} else {
    $app = Get-StartApps | Where-Object { $_.Name -like "Codex*" } | Select-Object -First 1
    if ($app) {
        Write-Host "Starting Codex Desktop: $($app.Name)"
        Start-Process "shell:AppsFolder\$($app.AppID)"
    } else {
        Write-Host "Codex Start menu entry was not found. Start Codex Desktop manually."
    }
}

Write-Host ""
Write-Host "Repair completed. After Codex opens, ask it to run: nodeRepl.write('node_repl alive')"
