param(
    [string]$Root = "C:\Users\Jonathan\Projects\Workflow-live-data-snapshot",
    [string[]]$Exclude = @("community-pool", "daemon_wikis", "wiki")
)

$ErrorActionPreference = "Stop"

$now = (Get-Date).ToUniversalTime()
$timestamp = $now.ToString("yyyy-MM-ddTHH:mm:ssZ")
$migrationId = $now.ToString("yyyyMMddTHHmmssZ")
$alphabet = "0123456789abcdefghjkmnpqrstvwxyz".ToCharArray()

function Write-Utf8NoBom {
    param([string]$Path, [string]$Text)
    $dir = Split-Path -Parent $Path
    if ($dir -and -not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir | Out-Null
    }
    [System.IO.File]::WriteAllText($Path, $Text, [System.Text.UTF8Encoding]::new($false))
}

function Test-SerialUniverseId {
    param([string]$Name)
    return $Name -match '^u-[0-9a-hjkmnp-tv-z]{26}$'
}

function Encode-FiveBitNumber {
    param(
        [Int64]$Value,
        [int]$CharCount
    )
    $chars = New-Object char[] $CharCount
    for ($i = $CharCount - 1; $i -ge 0; $i--) {
        $chars[$i] = $alphabet[[int]($Value -band 31)]
        $Value = [Int64][Math]::Floor($Value / 32)
    }
    return -join $chars
}

function Encode-RandomBase32 {
    param([byte[]]$Bytes)
    $chars = New-Object System.Collections.Generic.List[char]
    $buffer = 0
    $bits = 0
    foreach ($byte in $Bytes) {
        $buffer = ($buffer -shl 8) -bor [int]$byte
        $bits += 8
        while ($bits -ge 5) {
            $index = ($buffer -shr ($bits - 5)) -band 31
            $chars.Add($alphabet[$index]) | Out-Null
            $bits -= 5
            if ($bits -eq 0) {
                $buffer = 0
            } else {
                $buffer = $buffer -band ((1 -shl $bits) - 1)
            }
        }
    }
    if ($bits -gt 0) {
        $index = ($buffer -shl (5 - $bits)) -band 31
        $chars.Add($alphabet[$index]) | Out-Null
    }
    return -join $chars.ToArray()
}

function New-LowerUlid {
    $timePart = Encode-FiveBitNumber -Value ([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()) -CharCount 10
    $random = New-Object byte[] 10
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($random)
    } finally {
        $rng.Dispose()
    }
    $randomPart = Encode-RandomBase32 -Bytes $random
    return "$timePart$randomPart"
}

function Test-UniverseDirectory {
    param([System.IO.DirectoryInfo]$Dir)
    if ($Exclude -contains $Dir.Name) {
        return $false
    }
    if (Test-SerialUniverseId -Name $Dir.Name) {
        return $false
    }
    $markers = @(
        "index.md",
        "soul.md",
        "canon",
        "PROGRAM.md",
        "branch_tasks.json",
        "status.json",
        "notes.json",
        "ledger.json",
        "work_targets.json",
        ".runtime_status.json"
    )
    foreach ($marker in $markers) {
        if (Test-Path -LiteralPath (Join-Path $Dir.FullName $marker)) {
            return $true
        }
    }
    return $false
}

$rootPath = (Resolve-Path -LiteralPath $Root).ProviderPath
$rootPrefix = $rootPath.TrimEnd('\') + '\'
$aliasesPath = Join-Path $rootPath "universe_id_aliases.json"
$activePath = Join-Path $rootPath ".active_universe"

$moved = New-Object System.Collections.Generic.List[object]
$skipped = New-Object System.Collections.Generic.List[string]

foreach ($dir in Get-ChildItem -LiteralPath $rootPath -Directory -Force | Sort-Object Name) {
    if ($Exclude -contains $dir.Name) {
        $skipped.Add("$($dir.Name) - infrastructure directory") | Out-Null
        continue
    }
    if (Test-SerialUniverseId -Name $dir.Name) {
        $skipped.Add("$($dir.Name) - already serial") | Out-Null
        continue
    }
    if (-not (Test-UniverseDirectory -Dir $dir)) {
        $skipped.Add("$($dir.Name) - no universe markers") | Out-Null
        continue
    }

    do {
        $newId = "u-$(New-LowerUlid)"
        $targetPath = Join-Path $rootPath $newId
    } while (Test-Path -LiteralPath $targetPath)

    $sourcePath = (Resolve-Path -LiteralPath $dir.FullName).ProviderPath
    $targetFullPath = [System.IO.Path]::GetFullPath($targetPath)

    if (-not $sourcePath.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to move source outside root: $sourcePath"
    }
    if (-not $targetFullPath.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to move target outside root: $targetFullPath"
    }

    Move-Item -LiteralPath $sourcePath -Destination $targetFullPath

    $moved.Add([ordered]@{
        legacy_id = $dir.Name
        universe_id = $newId
        legacy_path = $sourcePath
        current_path = $targetFullPath
        migrated_at = $timestamp
        legacy_id_role = "compatibility-alias-only"
    }) | Out-Null
}

if ($moved.Count -gt 0) {
    $existingAliases = @()
    if (Test-Path -LiteralPath $aliasesPath -PathType Leaf) {
        $backupPath = Join-Path $rootPath "universe_id_aliases.$migrationId.bak.json"
        Copy-Item -LiteralPath $aliasesPath -Destination $backupPath -Force
        try {
            $existing = Get-Content -Raw -LiteralPath $aliasesPath | ConvertFrom-Json
            if ($existing.aliases) {
                $existingAliases = @($existing.aliases)
            }
        } catch {
            $existingAliases = @()
        }
    }

    $aliasDoc = [ordered]@{
        schema = 1
        migrated_at = $timestamp
        description = "Legacy descriptive universe ids are compatibility aliases only. The immutable universe_id is the storage directory and identity key."
        aliases = @($existingAliases + $moved)
    }
    Write-Utf8NoBom -Path $aliasesPath -Text (($aliasDoc | ConvertTo-Json -Depth 8) + "`n")

    if (Test-Path -LiteralPath $activePath -PathType Leaf) {
        $active = (Get-Content -Raw -LiteralPath $activePath).Trim()
        foreach ($entry in $moved) {
            if ($active -eq $entry.legacy_id) {
                Write-Utf8NoBom -Path $activePath -Text "$($entry.universe_id)`n"
                break
            }
        }
    }
}

Write-Host "Moved $($moved.Count) universe directories."
if ($moved.Count -gt 0) {
    Write-Host "Aliases: $aliasesPath"
}
