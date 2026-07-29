param(
    [Parameter(Mandatory = $false)]
    [string]$Repo,
    [string]$TaskName = "TinyAssets OpenSpec Drain",
    [switch]$Uninstall,
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"
if (-not $IsWindows -and $PSVersionTable.PSEdition -eq "Core") {
    throw "OpenSpec drain autostart is supported only on Windows."
}

if ($Uninstall) {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }
    Write-Output "Uninstalled scheduled task: $TaskName"
    exit 0
}

if (-not $Repo) {
    $Repo = Split-Path -Parent $PSScriptRoot
}
$repoPath = (Resolve-Path -LiteralPath $Repo).Path
$trayScript = Join-Path $repoPath "scripts\openspec_drain_tray.ps1"
$watchdogScript = Join-Path $repoPath "scripts\openspec_drain_watchdog.py"
$supervisorScript = Join-Path $repoPath "scripts\openspec_drain_supervisor.py"
foreach ($required in @($trayScript, $watchdogScript, $supervisorScript)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required drain file is missing: $required"
    }
}

$arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$trayScript`" -Repo `"$repoPath`""
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument $arguments `
    -WorkingDirectory $repoPath
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Starts and visibly monitors one bounded TinyAssets OpenSpec drain at Windows sign-in." `
    -Force | Out-Null

if (-not $NoStart) {
    Start-ScheduledTask -TaskName $TaskName
}

$task = Get-ScheduledTask -TaskName $TaskName
Write-Output "Installed scheduled task: $TaskName"
Write-Output "State: $($task.State)"
Write-Output "Controller repo: $repoPath"
