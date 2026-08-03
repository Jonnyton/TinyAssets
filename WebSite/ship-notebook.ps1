# ship-notebook.ps1 — ship the daemon's-notebook redesign to GitHub.
#
# Creates a fresh worktree from main (your live checkout stays untouched),
# copies in the 18 changed files from C:\Users\Jonathan\Projects\Workflow\,
# runs npm install + build to verify, commits to branch
# website/notebook-redesign, and pushes to origin. Prints the PR URL.
#
# Usage: from Windows PowerShell:
#   cd C:\Users\Jonathan\Projects\Workflow\WebSite
#   .\ship-notebook.ps1
#
# Run with -SkipBuild to push without running the local build (faster but
# unverified). Run with -DryRun to do everything except the push.

param(
  [switch]$SkipBuild,
  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

# ── Paths ─────────────────────────────────────────────────────────────
$LiveRepo  = 'C:\Users\Jonathan\Projects\Workflow'
$WorkRepo  = 'C:\Users\Jonathan\Projects\Workflow-notebook-ship'
$Branch    = 'website/notebook-redesign'
$Commit    = 'site: notebook redesign — cover, chapters, MCP playground, brain graph nav'

# ── 1. Sanity: live repo + files exist ───────────────────────────────
if (-not (Test-Path $LiveRepo)) {
  Write-Error "Live repo not found at $LiveRepo"
  exit 1
}

# Files we ship (18 total — modified + new — all relative to repo root)
$Files = @(
  # rewritten chapter pages
  'WebSite/site/src/routes/+page.svelte',
  'WebSite/site/src/routes/loop/+page.svelte',
  'WebSite/site/src/routes/connect/+page.svelte',
  'WebSite/site/src/routes/wiki/+page.svelte',
  'WebSite/site/src/routes/graph/+page.svelte',
  'WebSite/site/src/routes/status/+page.svelte',
  # new routes
  'WebSite/site/src/routes/notebook/+page.svelte',
  'WebSite/site/src/routes/loop-v2/+page.svelte',
  # chrome
  'WebSite/site/src/lib/components/TopNav.svelte',
  'WebSite/site/src/lib/components/MoodPill.svelte',
  # new notebook components
  'WebSite/site/src/lib/components/ChapterFolio.svelte',
  'WebSite/site/src/lib/components/CiteTheLoop.svelte',
  'WebSite/site/src/lib/components/Footnote.svelte',
  'WebSite/site/src/lib/components/RingSummon.svelte',
  'WebSite/site/src/lib/components/SceneBreak.svelte',
  'WebSite/site/src/lib/components/TableOfContents.svelte',
  # MCP playground client
  'WebSite/site/src/lib/mcp/playground.ts',
  # prerender list update
  'WebSite/site/svelte.config.js'
)

Write-Host "Checking $($Files.Count) source files exist in live repo..."
foreach ($f in $Files) {
  $abs = Join-Path $LiveRepo $f
  if (-not (Test-Path $abs)) {
    Write-Error "Missing source file: $abs"
    exit 1
  }
}
Write-Host "  all $($Files.Count) source files present"

# ── 2. Prepare fresh worktree from main ──────────────────────────────
if (Test-Path $WorkRepo) {
  Write-Host "Removing stale worktree at $WorkRepo ..."
  Push-Location $LiveRepo
  git worktree remove --force $WorkRepo 2>$null
  Pop-Location
  if (Test-Path $WorkRepo) {
    Remove-Item -Recurse -Force $WorkRepo
  }
}

Write-Host "1/5  Creating worktree at $WorkRepo from main..."
Push-Location $LiveRepo
git fetch origin main
if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }
git worktree add -B $Branch $WorkRepo origin/main
if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }
Pop-Location

# ── 3. Copy modified + new files into the worktree ───────────────────
Write-Host "2/5  Copying $($Files.Count) files into worktree..."
foreach ($f in $Files) {
  $src = Join-Path $LiveRepo $f
  $dst = Join-Path $WorkRepo $f
  $dstDir = Split-Path $dst -Parent
  if (-not (Test-Path $dstDir)) {
    New-Item -ItemType Directory -Force -Path $dstDir | Out-Null
  }
  Copy-Item $src $dst -Force
}

# ── 4. Optional local build verification ─────────────────────────────
if (-not $SkipBuild) {
  Write-Host "3/5  Installing deps + building locally to verify..."
  Push-Location (Join-Path $WorkRepo 'WebSite\site')
  Write-Host "     (this can take ~60s on cold node_modules)"
  npm install --silent
  if ($LASTEXITCODE -ne 0) {
    Pop-Location
    Write-Error "npm install failed in worktree"
    exit $LASTEXITCODE
  }
  npm run build
  if ($LASTEXITCODE -ne 0) {
    Pop-Location
    Write-Error "BUILD FAILED. Fix the error above and re-run. Worktree left at $WorkRepo for inspection."
    exit $LASTEXITCODE
  }
  Pop-Location
  Write-Host "     build green ✓"
} else {
  Write-Host "3/5  Skipping build (-SkipBuild specified)"
}

# ── 5. Commit + push ─────────────────────────────────────────────────
Write-Host "4/5  Committing to $Branch ..."
Push-Location $WorkRepo
git add WebSite/
if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }

# Show what we're about to commit
git status --short

git commit -m $Commit
if ($LASTEXITCODE -ne 0) {
  Pop-Location
  Write-Error "Nothing to commit, or commit failed."
  exit $LASTEXITCODE
}

if ($DryRun) {
  Write-Host ""
  Write-Host "5/5  -DryRun set — NOT pushing. Worktree at $WorkRepo has the commit."
  Write-Host "     To push now: cd $WorkRepo; git push -u origin $Branch"
  Pop-Location
  exit 0
}

Write-Host "5/5  Pushing $Branch to origin..."
git push -u origin $Branch
if ($LASTEXITCODE -ne 0) {
  Pop-Location
  Write-Error "Push failed. Worktree at $WorkRepo retained for retry."
  exit $LASTEXITCODE
}

Pop-Location

Write-Host ""
Write-Host "─────────────────────────────────────────────────────────────"
Write-Host "Pushed $Branch."
Write-Host ""
Write-Host "Open a PR:"
Write-Host "  https://github.com/Jonnyton/Workflow/compare/main...$($Branch)?expand=1"
Write-Host ""
Write-Host "Or fast-forward main directly (if you trust the diff):"
Write-Host "  cd $WorkRepo"
Write-Host "  git push origin $($Branch):main"
Write-Host ""
Write-Host "After merge, .github/workflows/deploy-site.yml redeploys"
Write-Host "to GitHub Pages and tinyassets.io serves the new site."
Write-Host "─────────────────────────────────────────────────────────────"
