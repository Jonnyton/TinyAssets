param(
    [Parameter(Mandatory = $true)][string]$Version,
    [Parameter(Mandatory = $true)][ValidateSet("x86_64", "arm64")][string]$Architecture
)

$ErrorActionPreference = "Stop"
if (-not $env:SOURCE_DATE_EPOCH) {
    throw "SOURCE_DATE_EPOCH must be provisioned for reproducible builds"
}

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

python -m PyInstaller --noconfirm --clean `
    --distpath "packaging/dist/windows" `
    --workpath "packaging/build/windows" `
    "packaging/windows/TinyAssets.spec"
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller Windows build failed"
}

$iscc = Get-Command "iscc.exe" -ErrorAction SilentlyContinue
if (-not $iscc) {
    $fallback = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    if (-not (Test-Path -LiteralPath $fallback)) {
        throw "Inno Setup compiler is not installed"
    }
    $iscc = Get-Item -LiteralPath $fallback
}

& $iscc.Source "/DAppVersion=$Version" "/DArchitecture=$Architecture" `
    "packaging/windows/TinyAssets.iss"
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup build failed"
}
