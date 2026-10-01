param(
    [Parameter(Mandatory = $true)][string]$Installer,
    [ValidateRange(1, 900)][int]$PhaseTimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"
$installerPath = (Resolve-Path -LiteralPath $Installer).Path
$installRoot = Join-Path $env:LOCALAPPDATA "Programs\TinyAssets"
$dataRoot = Join-Path $env:APPDATA "TinyAssets"
$tray = Join-Path $installRoot "TinyAssets.exe"
$uninstaller = Join-Path $installRoot "unins000.exe"
$startup = Join-Path $env:APPDATA `
    "Microsoft\Windows\Start Menu\Programs\Startup\TinyAssets Server.lnk"
$marker = Join-Path $dataRoot "clean-machine-content-marker.txt"

function Invoke-BoundedProcess {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList,
        [Parameter(Mandatory = $true)][string]$Phase
    )

    Write-Host "::notice title=Windows lifecycle phase::$Phase started; timeout=${PhaseTimeoutSeconds}s"
    $process = Start-Process -FilePath $FilePath `
        -ArgumentList $ArgumentList -PassThru
    try {
        Write-Host "::notice title=Windows lifecycle phase::$Phase started; root PID $($process.Id)"
        if (-not $process.WaitForExit($PhaseTimeoutSeconds * 1000)) {
            $diagnostics = Get-Process -ErrorAction SilentlyContinue |
                Where-Object {
                    $_.Id -eq $process.Id -or
                    $_.ProcessName -match "TinyAssets|unins"
                } |
                Select-Object Id, ProcessName, StartTime |
                Format-Table -AutoSize |
                Out-String
            Write-Host "::error title=Windows lifecycle timeout::$Phase timed out; root PID $($process.Id)"
            Write-Host $diagnostics
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
            throw "$Phase timed out after $PhaseTimeoutSeconds seconds"
        }
        if ($process.ExitCode -ne 0) {
            throw "$Phase failed with exit code $($process.ExitCode)"
        }
        Write-Host "::notice title=Windows lifecycle phase::$Phase completed; root PID $($process.Id)"
    }
    finally {
        $process.Dispose()
    }
}

function Invoke-Installer {
    param([Parameter(Mandatory = $true)][string]$Phase)

    Invoke-BoundedProcess -FilePath $installerPath -ArgumentList @(
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/TASKS=autostart"
    ) -Phase $Phase
}

function New-Shortcut {
    param([string]$Path, [string]$Target)
    $link = (New-Object -ComObject WScript.Shell).CreateShortcut($Path)
    $link.TargetPath = $Target
    $link.Save()
}

function Get-TrayStartupLinks {
    $shell = New-Object -ComObject WScript.Shell
    @(Get-ChildItem -LiteralPath (Split-Path $startup) -Filter "*.lnk" |
        Where-Object { $shell.CreateShortcut($_.FullName).TargetPath -ieq $tray })
}

# An earlier tray install named its shortcuts "TinyAssets", the same name the
# Electron chat app uses. The installer must remove the earlier tray's entry and
# leave a same-named chat-app shortcut alone.
$earlierStartup = Join-Path (Split-Path $startup) "TinyAssets.lnk"
$chatShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "TinyAssets.lnk"
New-Shortcut -Path $earlierStartup -Target $tray
New-Shortcut -Path $chatShortcut `
    -Target (Join-Path $env:LOCALAPPDATA "Programs\tinyassets-desktop\TinyAssets.exe")

Invoke-Installer -Phase "initial install"
if (Test-Path -LiteralPath $earlierStartup) {
    throw "the earlier tray's TinyAssets autostart entry survived the install"
}
if (-not (Test-Path -LiteralPath $chatShortcut -PathType Leaf)) {
    throw "the installer removed a TinyAssets shortcut that is not the tray's"
}
Remove-Item -LiteralPath $chatShortcut
if (-not (Test-Path -LiteralPath $tray -PathType Leaf)) {
    throw "installed tray executable is missing"
}
if (-not (Test-Path -LiteralPath $startup -PathType Leaf)) {
    throw "installer-owned autostart entry is missing"
}

New-Item -ItemType Directory -Force -Path $dataRoot | Out-Null
Set-Content -LiteralPath $marker -Value "preserve me"
$env:TINYASSETS_DATA_DIR = $dataRoot
Invoke-BoundedProcess -FilePath $tray `
    -ArgumentList @("--packaged-role", "health-probe") `
    -Phase "packaged health probe"

# Same-version repair must converge without a duplicate startup entry.
Invoke-Installer -Phase "same-version repair"
# Counted by target, so an entry under any name that launches the tray counts.
$startupEntries = Get-TrayStartupLinks
if ($startupEntries.Count -ne 1) {
    throw "repair produced $($startupEntries.Count) autostart entries"
}

Invoke-BoundedProcess -FilePath $uninstaller -ArgumentList @(
    "/VERYSILENT",
    "/SUPPRESSMSGBOXES",
    "/NORESTART"
) -Phase "uninstall"
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
