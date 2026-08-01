param(
    [Parameter(Mandatory = $false)]
    [string]$Repo,
    [string]$TaskName = "TinyAssets OpenSpec Drain",
    [string]$GuardTaskName,
    [switch]$Uninstall,
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"
if (-not $IsWindows -and $PSVersionTable.PSEdition -eq "Core") {
    throw "OpenSpec drain autostart is supported only on Windows."
}

if (-not $GuardTaskName) {
    $GuardTaskName = "$TaskName Guard"
}

function Remove-DrainTask {
    param([string]$Name)
    $existing = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    if ($existing) {
        Stop-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $Name -Confirm:$false
    }
}

if ($Uninstall) {
    Remove-DrainTask -Name $TaskName
    Remove-DrainTask -Name $GuardTaskName
    Write-Output "Uninstalled scheduled tasks: $TaskName; $GuardTaskName"
    exit 0
}

if (-not $Repo) {
    $Repo = Split-Path -Parent $PSScriptRoot
}
$repoPath = (Resolve-Path -LiteralPath $Repo).Path
$trayScript = Join-Path $repoPath "scripts\openspec_drain_tray.ps1"
$launcherScript = Join-Path $repoPath "scripts\launch_openspec_drain_tray.vbs"
$watchdogScript = Join-Path $repoPath "scripts\openspec_drain_watchdog.py"
$supervisorScript = Join-Path $repoPath "scripts\openspec_drain_supervisor.py"
foreach ($required in @($trayScript, $launcherScript, $watchdogScript, $supervisorScript)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required drain file is missing: $required"
    }
}

$primaryArguments = "//B //Nologo `"$launcherScript`" `"$repoPath`""
$guardArguments = "$primaryArguments --preserve-stop"
$primaryAction = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $primaryArguments `
    -WorkingDirectory $repoPath
$guardAction = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $guardArguments `
    -WorkingDirectory $repoPath
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$recoveryTrigger = New-ScheduledTaskTrigger -Daily -At ([DateTime]::Today)
$recoveryTrigger.Repetition = New-CimInstance `
    -ClassName MSFT_TaskRepetitionPattern `
    -Namespace Root/Microsoft/Windows/TaskScheduler `
    -ClientOnly `
    -Property @{
        Interval = "PT1M"
        Duration = "P1D"
        StopAtDurationEnd = $false
    }
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

Remove-DrainTask -Name $TaskName
Remove-DrainTask -Name $GuardTaskName

if (-not $NoStart) {
    $comparison = [System.StringComparison]::OrdinalIgnoreCase
    $observerProcesses = Get-CimInstance Win32_Process | Where-Object {
        $commandLine = [string]$_.CommandLine
        $isTray = (
            $commandLine.IndexOf($trayScript, $comparison) -ge 0 -and
            $commandLine.IndexOf($repoPath, $comparison) -ge 0
        )
        $isWatchdog = (
            $commandLine.IndexOf($watchdogScript, $comparison) -ge 0 -and
            $commandLine.IndexOf(" run ", $comparison) -ge 0 -and
            $commandLine.IndexOf($repoPath, $comparison) -ge 0
        )
        $isTray -or $isWatchdog
    }
    foreach ($process in $observerProcesses) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $primaryAction `
    -Trigger $logonTrigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Starts one bounded TinyAssets OpenSpec drain in the interactive user session at sign-in." `
    -Force | Out-Null

Register-ScheduledTask `
    -TaskName $GuardTaskName `
    -Action $guardAction `
    -Trigger $recoveryTrigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Relaunches the hidden OpenSpec drain tray after failure without clearing an intentional session stop." `
    -Force | Out-Null

if (-not $NoStart) {
    Start-ScheduledTask -TaskName $TaskName

    $healthPath = Join-Path $repoPath "output\openspec-drain-watchdog\health.json"
    $deadline = [DateTimeOffset]::Now.AddSeconds(45)
    $verified = $false
    do {
        Start-Sleep -Milliseconds 500
        try {
            $health = Get-Content -LiteralPath $healthPath -Raw | ConvertFrom-Json
            $updated = [DateTimeOffset]::Parse([string]$health.updated_at)
            $fresh = ([DateTimeOffset]::Now - $updated).TotalSeconds -le 15
            $processes = Get-CimInstance Win32_Process
            $watchdogCount = @($processes | Where-Object {
                $_.Name -ieq "python.exe" -and
                ([string]$_.CommandLine).IndexOf($watchdogScript, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and
                ([string]$_.CommandLine).IndexOf(" run ", [System.StringComparison]::OrdinalIgnoreCase) -ge 0
            }).Count
            $trayCount = @($processes | Where-Object {
                $_.Name -ieq "powershell.exe" -and
                ([string]$_.CommandLine).IndexOf($trayScript, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and
                ([string]$_.CommandLine).IndexOf($repoPath, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
            }).Count
            $supervisorCount = @($processes | Where-Object {
                $_.Name -ieq "python.exe" -and
                ([string]$_.CommandLine).IndexOf($supervisorScript, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and
                ([string]$_.CommandLine).IndexOf(" run ", [System.StringComparison]::OrdinalIgnoreCase) -ge 0
            }).Count
            $verified = (
                [int]$health.watchdog_version -eq 2 -and
                [bool]$health.controller_alive -and
                $fresh -and
                $watchdogCount -eq 1 -and
                $trayCount -eq 1 -and
                $supervisorCount -eq 1
            )
        }
        catch {
            $verified = $false
        }
    } while (-not $verified -and [DateTimeOffset]::Now -lt $deadline)

    if (-not $verified) {
        throw "Drain observer activation did not prove version 2 fresh health with exactly one tray, watchdog, and supervisor."
    }
}

$task = Get-ScheduledTask -TaskName $TaskName
Write-Output "Installed scheduled tasks: $TaskName; $GuardTaskName"
Write-Output "State: $($task.State)"
Write-Output "Controller repo: $repoPath"
