# ship.ps1 — push the prepared website-ship.bundle to GitHub.
# Run from Windows PowerShell. Uses YOUR git credentials.
#
# Current bundle: branch website/fix-live-crashes (one commit beyond main).
# Fixes the live-state crashes found by the post-deploy crawl.

$ErrorActionPreference = 'Stop'
$bundle = Join-Path $PSScriptRoot 'website-ship.bundle'
if (-not (Test-Path $bundle)) {
  Write-Error "Bundle not found at $bundle"
  exit 1
}

$workdir = Join-Path $env:TEMP 'wf-ship'
if (Test-Path $workdir) {
  Write-Host "Removing stale $workdir ..."
  Remove-Item -Recurse -Force $workdir
}

Write-Host "1/4  Cloning Jonnyton/TinyAssets main into $workdir ..."
git clone --depth=1 --branch=main https://github.com/Jonnyton/TinyAssets.git $workdir
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Set-Location $workdir

Write-Host "2/4  Fetching bundle $bundle ..."
git fetch $bundle 'refs/heads/website/fix-live-crashes:refs/heads/website/fix-live-crashes'
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "3/4  Pushing branch website/fix-live-crashes to origin ..."
git push -u origin website/fix-live-crashes
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "4/4  Pushed. Fast-forward main to ship the fix:"
Write-Host "     git push origin website/fix-live-crashes:main"
Write-Host ""
Write-Host "Or open a PR:"
Write-Host "     https://github.com/Jonnyton/TinyAssets/compare/main...website/fix-live-crashes?expand=1"
Write-Host ""
Write-Host "After merge, .github/workflows/deploy-site.yml redeploys to GitHub Pages"
Write-Host "and tinyassets.io serves the patched site (/wiki, /graph fixed; favicon.ico"
Write-Host "200; no more hydration warnings)."
