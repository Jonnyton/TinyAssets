$ErrorActionPreference = "Continue"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$AndroidDir = Join-Path $RepoRoot "clients\android"

function Find-AndroidStudio {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Android Studio\bin\studio64.exe"),
        (Join-Path $env:ProgramFiles "Android\Android Studio\bin\studio64.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Android\Android Studio\bin\studio64.exe")
    )

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return $candidate
        }
    }

    $cmd = Get-Command studio64.exe -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    return $null
}

function Get-JavaMajorVersion {
    $java = Get-Command java.exe -ErrorAction SilentlyContinue
    if (-not $java) {
        return $null
    }

    $versionText = (& java -version) 2>&1 | Select-Object -First 1
    if ($versionText -match '"(?<major>\d+)(\.|")') {
        $major = [int]$Matches.major
        if ($major -eq 1 -and $versionText -match '"1\.(?<legacy>\d+)') {
            return [int]$Matches.legacy
        }
        return $major
    }

    return $null
}

function Confirm-DefaultYes {
    param([Parameter(Mandatory = $true)][string]$Prompt)

    $answer = Read-Host "$Prompt [Y/n]"
    return ($answer -eq "" -or $answer -match "^(y|yes)$")
}

Write-Host "TinyAssets Android" -ForegroundColor Cyan
Write-Host "Project: $AndroidDir"

$winget = Get-Command winget.exe -ErrorAction SilentlyContinue
$javaMajor = Get-JavaMajorVersion
if (-not $javaMajor -or $javaMajor -lt 17) {
    Write-Host ""
    $javaLabel = "not found"
    if ($javaMajor) {
        $javaLabel = [string]$javaMajor
    }
    Write-Host "JDK 17 is required. Current Java major: $javaLabel" -ForegroundColor Yellow
    if ($winget) {
        if (Confirm-DefaultYes "Install JDK 17 with winget now?") {
            winget install --exact --id EclipseAdoptium.Temurin.17.JDK --accept-package-agreements --accept-source-agreements
            $javaMajor = Get-JavaMajorVersion
        }
    } else {
        Write-Host "Install JDK 17, then reopen this shortcut."
    }
}

$studio = Find-AndroidStudio
if (-not $studio) {
    Write-Host ""
    Write-Host "Android Studio is not installed or not on PATH." -ForegroundColor Yellow
    if ($winget) {
        if (Confirm-DefaultYes "Install Android Studio with winget now?") {
            winget install --exact --id Google.AndroidStudio --accept-package-agreements --accept-source-agreements
            $studio = Find-AndroidStudio
        }
    } else {
        Write-Host "Install Android Studio, then reopen this shortcut."
    }

    if (-not $studio) {
        Start-Process explorer.exe -ArgumentList "`"$AndroidDir`""
        return
    }
}

Write-Host ""
Write-Host "Opening Android Studio..."
Start-Process -FilePath $studio -ArgumentList "`"$AndroidDir`""

Write-Host ""
Write-Host "After Android Studio syncs, run the app target on an emulator or device."
Write-Host "For command-line checks later:"
Write-Host "  cd `"$AndroidDir`""
Write-Host "  .\scripts\doctor.ps1"
