param(
    [Parameter(Mandatory = $true)][string]$Artifact
)

$ErrorActionPreference = "Stop"
if (-not $env:SOURCE_DATE_EPOCH) {
    throw "SOURCE_DATE_EPOCH must be provisioned"
}
if (-not $env:WINDOWS_SIGNING_CERTIFICATE_BASE64 -or
    -not $env:WINDOWS_SIGNING_CERTIFICATE_PASSWORD) {
    throw "signing identity not provisioned: Windows Authenticode certificate"
}
if (-not (Test-Path -LiteralPath $Artifact -PathType Leaf)) {
    throw "artifact does not exist: $Artifact"
}

$certificateFile = Join-Path $env:RUNNER_TEMP "tinyassets-signing.pfx"
$certificateBytes = [Convert]::FromBase64String(
    $env:WINDOWS_SIGNING_CERTIFICATE_BASE64
)
[IO.File]::WriteAllBytes($certificateFile, $certificateBytes)
$password = ConvertTo-SecureString `
    $env:WINDOWS_SIGNING_CERTIFICATE_PASSWORD -AsPlainText -Force
$certificate = Import-PfxCertificate `
    -FilePath $certificateFile `
    -CertStoreLocation "Cert:\CurrentUser\My" `
    -Password $password
try {
    $expectedThumbprint = $env:WINDOWS_SIGNING_IDENTITY.Replace(" ", "").ToUpperInvariant()
    if ($certificate.Thumbprint.ToUpperInvariant() -ne $expectedThumbprint) {
        throw "provisioned Windows certificate does not match WINDOWS_SIGNING_IDENTITY"
    }
    & signtool.exe sign /fd SHA256 /sha1 $certificate.Thumbprint `
        /tr "http://timestamp.digicert.com" /td SHA256 $Artifact
    if ($LASTEXITCODE -ne 0) {
        throw "Authenticode signing failed"
    }
    & signtool.exe verify /pa /all $Artifact
    if ($LASTEXITCODE -ne 0) {
        throw "Authenticode signature verification failed"
    }
} finally {
    Remove-Item -LiteralPath $certificate.PSPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $certificateFile -Force -ErrorAction SilentlyContinue
}
