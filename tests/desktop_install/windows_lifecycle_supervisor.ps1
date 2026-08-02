param(
    [Parameter(Mandatory = $true)][string]$Installer,
    [string]$LifecycleScript = (Join-Path $PSScriptRoot "windows_lifecycle.ps1"),
    [ValidateRange(1, 900)][int]$PhaseTimeoutSeconds = 180,
    [ValidateRange(1, 3600)][int]$TotalTimeoutSeconds = 300,
    [ValidateRange(1, 60)][int]$CleanupTimeoutSeconds = 10,
    [ValidateRange(1024, 10485760)][int]$MaxCaptureBytesPerStream = 262144
)

$ErrorActionPreference = "Stop"
$installerPath = (Resolve-Path -LiteralPath $Installer).Path
$lifecyclePath = (Resolve-Path -LiteralPath $LifecycleScript).Path
$tempRoot = if ($env:RUNNER_TEMP) {
    $env:RUNNER_TEMP
}
else {
    [System.IO.Path]::GetTempPath()
}
$captureId = [Guid]::NewGuid().ToString("N")
$stdoutPath = Join-Path $tempRoot "tinyassets-windows-lifecycle-$captureId.stdout.log"
$stderrPath = Join-Path $tempRoot "tinyassets-windows-lifecycle-$captureId.stderr.log"
$shellPath = (Get-Process -Id $PID).Path

function Write-CapturedOutput {
    param(
        [Parameter(Mandatory = $true)][string]$StandardOutput,
        [Parameter(Mandatory = $true)][string]$StandardError,
        [Parameter(Mandatory = $true)][int]$MaxBytes
    )

    foreach ($capture in @(
            @{ Path = $StandardOutput; Name = "stdout"; IsError = $false },
            @{ Path = $StandardError; Name = "stderr"; IsError = $true }
        )) {
        if (-not (Test-Path -LiteralPath $capture.Path -PathType Leaf)) {
            continue
        }

        $stream = [System.IO.File]::Open(
            $capture.Path,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read,
            [System.IO.FileShare]::ReadWrite
        )
        try {
            $observedBytes = $stream.Length
            $replayBytes = [int][Math]::Min($observedBytes, $MaxBytes)
            $buffer = New-Object byte[] $replayBytes
            $offset = 0
            while ($offset -lt $replayBytes) {
                $read = $stream.Read($buffer, $offset, $replayBytes - $offset)
                if ($read -eq 0) {
                    break
                }
                $offset += $read
            }
            $text = [System.Text.Encoding]::UTF8.GetString($buffer, 0, $offset)
            if ($capture.IsError) {
                [Console]::Error.Write($text)
            }
            else {
                [Console]::Out.Write($text)
            }
            $finalObservedBytes = [Math]::Max($observedBytes, $stream.Length)
            if ($finalObservedBytes -gt $offset) {
                Write-Host "::warning title=Windows lifecycle capture::$($capture.Name) truncated at $MaxBytes bytes; observed at least $finalObservedBytes bytes"
            }
        }
        finally {
            $stream.Dispose()
        }
    }
}

function Stop-ProcessTreeBounded {
    param(
        [Parameter(Mandatory = $true)][int]$ProcessId,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )

    $taskkillPath = Join-Path $env:SystemRoot "System32\taskkill.exe"
    $killer = Start-Process -FilePath $taskkillPath -ArgumentList @(
        "/PID",
        "$ProcessId",
        "/T",
        "/F"
    ) -PassThru -WindowStyle Hidden
    try {
        if (-not $killer.WaitForExit($TimeoutSeconds * 1000)) {
            try {
                $killer.Kill()
            }
            catch {
                Write-Warning "taskkill for lifecycle PID $ProcessId did not stop cleanly"
            }
            return $false
        }
        return $killer.ExitCode -eq 0
    }
    finally {
        $killer.Dispose()
    }
}

$childArguments = @(
    "-NoLogo",
    "-NoProfile",
    "-NonInteractive",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    "`"$lifecyclePath`"",
    "-Installer",
    "`"$installerPath`"",
    "-PhaseTimeoutSeconds",
    "$PhaseTimeoutSeconds"
)
$process = Start-Process -FilePath $shellPath `
    -ArgumentList $childArguments `
    -PassThru `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath
$timedOut = $false
$exitCode = $null

try {
    Write-Host "::notice title=Windows lifecycle supervisor::child PID $($process.Id); total deadline $TotalTimeoutSeconds seconds"
    if (-not $process.WaitForExit($TotalTimeoutSeconds * 1000)) {
        $timedOut = $true
        Write-Host "::error title=Windows lifecycle total timeout::child PID $($process.Id) exceeded $TotalTimeoutSeconds seconds"
        try {
            $cleanupCompleted = Stop-ProcessTreeBounded `
                -ProcessId $process.Id `
                -TimeoutSeconds $CleanupTimeoutSeconds
            if (-not $cleanupCompleted) {
                Write-Warning "bounded process-tree cleanup did not confirm lifecycle termination"
            }
        }
        catch {
            Write-Warning "bounded process-tree cleanup failed: $($_.Exception.Message)"
        }
        $process.WaitForExit($CleanupTimeoutSeconds * 1000) | Out-Null
    }
    else {
        $exitCode = $process.ExitCode
    }
}
finally {
    $process.Dispose()
    Write-CapturedOutput `
        -StandardOutput $stdoutPath `
        -StandardError $stderrPath `
        -MaxBytes $MaxCaptureBytesPerStream
    Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
}

if ($timedOut) {
    throw "total lifecycle timed out after $TotalTimeoutSeconds seconds"
}
if ($exitCode -ne 0) {
    throw "Windows lifecycle child failed with exit code $exitCode"
}
