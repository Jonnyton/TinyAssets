param(
    [Parameter(Mandatory = $false)]
    [string]$Repo,
    [ValidateSet("codex", "claude")]
    [string]$Provider = "codex",
    [switch]$PreserveStop
)

$ErrorActionPreference = "Stop"
if (-not $Repo) {
    $Repo = Split-Path -Parent $PSScriptRoot
}
$repoPath = (Resolve-Path -LiteralPath $Repo).Path
$watchdogScript = Join-Path $repoPath "scripts\openspec_drain_watchdog.py"
$watchdogDir = Join-Path $repoPath "output\openspec-drain-watchdog"
$healthPath = Join-Path $watchdogDir "health.json"
$stopPath = Join-Path $watchdogDir "stop.request"
$restartPath = Join-Path $watchdogDir "restart.request"
New-Item -ItemType Directory -Path $watchdogDir -Force | Out-Null

$createdNew = $false
$trayMutex = New-Object System.Threading.Mutex(
    $true,
    "Local\TinyAssetsOpenSpecDrainTray",
    [ref]$createdNew
)
if (-not $createdNew) {
    $trayMutex.Dispose()
    exit 0
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$watchdogArgs = @(
    $watchdogScript,
    "run",
    "--repo", $repoPath,
    "--provider", $Provider
)

$script:lastHealth = ""
$script:lastState = ""
$script:watchdogLaunchError = ""
$script:lastWatchdogRecoveryAt = [DateTimeOffset]::MinValue
$watchdogRecoveryCooldownSeconds = 60
$script:notify = New-Object System.Windows.Forms.NotifyIcon
$script:notify.Icon = [System.Drawing.SystemIcons]::Application
$script:notify.Text = "TinyAssets OpenSpec drain: starting"
$script:notify.Visible = $true

$menu = New-Object System.Windows.Forms.ContextMenuStrip
$statusItem = $menu.Items.Add("Status: starting")
$statusItem.Enabled = $false
$menu.Items.Add("-") | Out-Null
$openItem = $menu.Items.Add("Open active run")
$logItem = $menu.Items.Add("Watch live status")
$restartItem = $menu.Items.Add("Restart drain")
$stopItem = $menu.Items.Add("Stop until next sign-in")
$menu.Items.Add("-") | Out-Null
$exitItem = $menu.Items.Add("Exit indicator (drain keeps running)")
$script:notify.ContextMenuStrip = $menu

function Start-DrainWatchdog {
    try {
        Start-Process `
            -FilePath "py.exe" `
            -ArgumentList $watchdogArgs `
            -WorkingDirectory $repoPath `
            -WindowStyle Hidden | Out-Null
        $script:watchdogLaunchError = ""
        return $true
    }
    catch {
        $script:watchdogLaunchError = "watchdog failed to start: $($_.Exception.Message)"
        $script:notify.BalloonTipTitle = "OpenSpec drain is down"
        $script:notify.BalloonTipText = $script:watchdogLaunchError
        $script:notify.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Error
        $script:notify.ShowBalloonTip(5000)
        return $false
    }
}

function Read-DrainHealth {
    if (-not (Test-Path -LiteralPath $healthPath)) {
        return $null
    }
    try {
        $health = Get-Content -LiteralPath $healthPath -Raw | ConvertFrom-Json
        $updated = [DateTimeOffset]::Parse($health.updated_at)
        if (([DateTimeOffset]::Now - $updated).TotalSeconds -gt 30) {
            $health.health = "down"
            $health.message = "watchdog health is stale"
        }
        return $health
    }
    catch {
        return $null
    }
}

function Request-WatchdogRecovery {
    param($Health)

    if (Test-Path -LiteralPath $stopPath) {
        return
    }

    $needsRecovery = ($null -eq $Health) -or (
        [string]$Health.message -eq "watchdog health is stale"
    )
    if (-not $needsRecovery) {
        return
    }

    $now = [DateTimeOffset]::Now
    $elapsed = ($now - $script:lastWatchdogRecoveryAt).TotalSeconds
    if ($elapsed -lt $watchdogRecoveryCooldownSeconds) {
        return
    }

    $script:lastWatchdogRecoveryAt = $now
    Start-DrainWatchdog | Out-Null
}

function Set-DrainTrayState {
    $health = Read-DrainHealth
    Request-WatchdogRecovery -Health $health
    if ($null -eq $health) {
        $state = "down"
        $message = if ($script:watchdogLaunchError) {
            $script:watchdogLaunchError
        } else {
            "health unavailable"
        }
        $identity = ""
        $activeRun = $watchdogDir
    }
    else {
        $state = [string]$health.health
        $message = [string]$health.message
        $identity = [string]$health.identity
        $activeRun = if ($health.active_run) {
            [string]$health.active_run
        } else {
            $watchdogDir
        }
    }

    switch ($state) {
        "running" {
            $script:notify.Icon = [System.Drawing.SystemIcons]::Information
            $label = "running"
        }
        "waiting" {
            $script:notify.Icon = [System.Drawing.SystemIcons]::Warning
            $label = "waiting"
        }
        default {
            $script:notify.Icon = [System.Drawing.SystemIcons]::Error
            $label = "DOWN"
        }
    }

    $tooltip = "TinyAssets drain: $label"
    if ($identity) {
        $tooltip = "$tooltip - $identity"
    }
    if ($tooltip.Length -gt 63) {
        $tooltip = $tooltip.Substring(0, 63)
    }
    $script:notify.Text = $tooltip
    $statusItem.Text = "Status: $label - $message"
    $openItem.Tag = $activeRun

    if ($script:lastHealth -and $script:lastHealth -ne $state -and $state -eq "down") {
        $script:notify.BalloonTipTitle = "OpenSpec drain is down"
        $script:notify.BalloonTipText = $message
        $script:notify.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Error
        $script:notify.ShowBalloonTip(5000)
    }
    $script:lastHealth = $state
}

$openItem.Add_Click({
    $target = [string]$openItem.Tag
    if (-not $target) {
        $target = $watchdogDir
    }
    Start-Process -FilePath "explorer.exe" -ArgumentList @($target) | Out-Null
})

$logItem.Add_Click({
    $watch = @"
`$healthPath = '$healthPath'
while (`$true) {
    Clear-Host
    if (Test-Path -LiteralPath `$healthPath) {
        `$health = Get-Content -LiteralPath `$healthPath -Raw | ConvertFrom-Json
        Write-Host 'TinyAssets OpenSpec Drain' -ForegroundColor Cyan
        Write-Host "Health: `$(`$health.health)   Mode: `$(`$health.mode)"
        Write-Host "Identity: `$(`$health.identity)"
        Write-Host "Message: `$(`$health.message)"
        Write-Host "Attempts: `$(`$health.attempts)   Merged: `$(`$health.completed_slices)   Failures: `$(`$health.consecutive_failures)"
        if (`$health.active_run) {
            `$log = Join-Path `$health.active_run 'supervisor.log'
            Write-Host ''
            Write-Host 'Latest supervisor log:' -ForegroundColor Yellow
            Get-Content -LiteralPath `$log -Tail 12 -ErrorAction SilentlyContinue
        }
    } else {
        Write-Host 'Watchdog health is unavailable.' -ForegroundColor Red
    }
    Write-Host ''
    Write-Host 'Refreshes every 10 seconds. Closing this window does not stop the drain.' -ForegroundColor DarkGray
    Start-Sleep -Seconds 10
}
"@
    $encoded = [Convert]::ToBase64String(
        [Text.Encoding]::Unicode.GetBytes($watch)
    )
    Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList @("-NoExit", "-EncodedCommand", $encoded) `
        -WindowStyle Normal | Out-Null
})

$restartItem.Add_Click({
    Start-DrainWatchdog | Out-Null
    Start-Sleep -Milliseconds 1000
    Set-Content -LiteralPath $restartPath -Value "restart requested $(Get-Date -Format o)"
    $script:notify.ShowBalloonTip(
        3000,
        "OpenSpec drain",
        "Restart requested; the active worker may finish first.",
        [System.Windows.Forms.ToolTipIcon]::Info
    )
})

$stopItem.Add_Click({
    Set-Content -LiteralPath $stopPath -Value "stop requested $(Get-Date -Format o)"
    $script:notify.ShowBalloonTip(
        3000,
        "OpenSpec drain",
        "Stop requested until the next Windows sign-in.",
        [System.Windows.Forms.ToolTipIcon]::Info
    )
})

$exitItem.Add_Click({
    [System.Windows.Forms.Application]::ExitThread()
})

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 5000
$timer.Add_Tick({ Set-DrainTrayState })
$timer.Start()
if ((-not $PreserveStop) -or (-not (Test-Path -LiteralPath $stopPath))) {
    $watchdogStarted = Start-DrainWatchdog
    if ($watchdogStarted) {
        $script:lastWatchdogRecoveryAt = [DateTimeOffset]::Now
    }
}
Set-DrainTrayState

try {
    [System.Windows.Forms.Application]::Run()
}
finally {
    $timer.Stop()
    $timer.Dispose()
    $script:notify.Visible = $false
    $script:notify.Dispose()
    $trayMutex.ReleaseMutex()
    $trayMutex.Dispose()
}
