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
    "Microsoft\Windows\Start Menu\Programs\Startup\TinyAssets.lnk"
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
        Write-Host "::notice title=Windows lifecycle phase::$Phase completed"
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

Invoke-Installer -Phase "initial install"
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
$startupEntries = @(Get-ChildItem -LiteralPath (Split-Path $startup) `
    -Filter "TinyAssets.lnk")
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
