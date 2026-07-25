param(
    [string]$Root = "C:\Users\Jonathan\Projects\Workflow-live-data-snapshot",
    [string[]]$LegacyDirs = @("self", "soul", "_legacy_brain_preserved"),
    [string[]]$EmptyLegacyFiles = @("notes.json", "activity.log")
)

$ErrorActionPreference = "Stop"

$baselineTop = @(
    "index.md",
    "log.md",
    "soul.md",
    "soul.edit.md",
    "identity.md",
    "founder.md",
    "orgchart.md",
    "projects.md",
    "goals.md",
    "body.md",
    "origin.md",
    "soul_versions"
)

function Test-SerialUniverseId {
    param([string]$Name)
    return $Name -match '^u-[0-9a-hjkmnp-tv-z]{26}$'
}

$rootPath = (Resolve-Path -LiteralPath $Root).ProviderPath
$rootPrefix = $rootPath.TrimEnd('\') + '\'
$removed = New-Object System.Collections.Generic.List[string]
$leftInPlace = New-Object System.Collections.Generic.List[string]

foreach ($universe in Get-ChildItem -LiteralPath $rootPath -Directory -Force | Sort-Object Name) {
    if (-not (Test-SerialUniverseId -Name $universe.Name)) {
        continue
    }

    foreach ($legacyName in $LegacyDirs) {
        $target = Join-Path $universe.FullName $legacyName
        if (-not (Test-Path -LiteralPath $target -PathType Container)) {
            continue
        }

        $targetFull = (Resolve-Path -LiteralPath $target).ProviderPath
        if (-not $targetFull.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to remove target outside root: $targetFull"
        }

        Remove-Item -LiteralPath $targetFull -Recurse -Force
        $removed.Add("$($universe.Name)/$legacyName") | Out-Null
    }

    foreach ($legacyName in $EmptyLegacyFiles) {
        $target = Join-Path $universe.FullName $legacyName
        if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
            continue
        }

        $targetFull = (Resolve-Path -LiteralPath $target).ProviderPath
        if (-not $targetFull.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to remove target outside root: $targetFull"
        }

        $removeEmptyLegacyFile = $false
        if ($legacyName -eq "activity.log") {
            $removeEmptyLegacyFile = ((Get-Item -LiteralPath $targetFull).Length -eq 0)
        } elseif ($legacyName -eq "notes.json") {
            $text = [System.IO.File]::ReadAllText($targetFull).Trim()
            $removeEmptyLegacyFile = ($text -eq "[]")
        }

        if ($removeEmptyLegacyFile) {
            Remove-Item -LiteralPath $targetFull -Force
            $removed.Add("$($universe.Name)/$legacyName") | Out-Null
        }
    }

    $extra = Get-ChildItem -LiteralPath $universe.FullName -Force |
        Where-Object { $baselineTop -notcontains $_.Name } |
        Select-Object -ExpandProperty Name
    if ($extra.Count -gt 0) {
        $leftInPlace.Add("$($universe.Name): " + (($extra | Sort-Object) -join ", ")) | Out-Null
    }
}

Write-Host "Removed stale brain artifacts: $($removed.Count)"
Write-Host "Non-baseline runtime/canon/data markers left in place: $($leftInPlace.Count)"
