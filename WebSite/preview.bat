@echo off
:: ================================================================
::  preview.bat  -  Workflow site live preview (hidden + persistent)
::
::  Double-click. Browser pops up. No terminal to manage.
::    - First click ever: installs deps (~1 min), starts vite hidden,
::      opens http://localhost:5173/
::    - Every subsequent click: detects vite is already running,
::      just opens the browser tab
::    - Server persists in the background until you reboot OR run
::      preview-stop.bat
::
::  Why persistent (not tab-bound): vite uses ~80MB RAM idle and
::  every reopen is instant. Tab-bound lifecycles add complexity
::  for marginal benefit. To free the port, run preview-stop.bat.
::
::  Multi-session: any browser tab open to localhost:5173 ? yours,
::  mine, anyone else's ? receives HMR updates over a websocket.
::  All open tabs auto-update on every save. Nothing extra to do.
:: ================================================================

setlocal
set "URL=http://localhost:5173/"
:: Preview rule (host, 2026-06-10): the preview always shows the NEXT
:: version of the site (the rebuild in progress), never the current site
:: -- the live URL already shows the current one. Prefer the rebuild
:: worktree while it exists; fall back to this checkout automatically
:: once the rebuild merges and the worktree is removed.
set "SITE=%~dp0..\.claude\worktrees\fable-website-rebuild\WebSite\site"
if not exist "%SITE%" set "SITE=%~dp0site"

:: First-run install if node_modules missing.
if not exist "%SITE%\node_modules" (
  echo Installing dependencies first run, ~1 minute...
  pushd "%SITE%"
  call npm install
  if errorlevel 1 (
    echo Setup failed. Make sure Node.js 18+ is installed.
    pause
    exit /b 1
  )
  popd
)

:: All the lifecycle work runs in PowerShell. Uses raw .NET TCP probe
:: (sub-second per attempt) instead of Test-NetConnection (2-5s each)
:: so the 60-attempt window covers a real ~60s cold start, not 15s of
:: actual checking inside a 15s window.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$port = 5173;" ^
  "function TcpAlive([int]$p) { $c = New-Object Net.Sockets.TcpClient; try { $r = $c.BeginConnect('127.0.0.1', $p, $null, $null); $ok = $r.AsyncWaitHandle.WaitOne(250); if ($ok -and $c.Connected) { $c.EndConnect($r) | Out-Null; return $true } else { return $false } } catch { return $false } finally { $c.Close() } };" ^
  "if (TcpAlive $port) {" ^
  "  Write-Host 'preview already running - opening browser tab';" ^
  "  Start-Process $env:URL;" ^
  "} else {" ^
  "  Write-Host 'starting vite dev server (hidden)...';" ^
  "  $cmd = 'Set-Location ''' + $env:SITE + '''; npm run dev -- --port 5173 --strictPort';" ^
  "  Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile','-Command',$cmd;" ^
  "  Write-Host 'waiting for dev server to come up (up to 60s on first cold start)...';" ^
  "  $ready = $false;" ^
  "  for ($i = 0; $i -lt 120; $i++) {" ^
  "    Start-Sleep -Milliseconds 500;" ^
  "    if (TcpAlive $port) { $ready = $true; break };" ^
  "    if ($i -eq 20) { Write-Host '  ...still starting (this is normal first time)' };" ^
  "    if ($i -eq 60) { Write-Host '  ...vite is compiling, hang on' };" ^
  "  };" ^
  "  if ($ready) {" ^
  "    Start-Process $env:URL;" ^
  "    Write-Host 'opened. server stays alive in the background.';" ^
  "  } else {" ^
  "    Write-Host 'WARN: server did not respond within 60s. Opening browser anyway - you may need to F5 once.';" ^
  "    Start-Process $env:URL;" ^
  "  };" ^
  "}"

:: Launcher exits immediately. Hidden vite keeps running in the background.
exit /b 0
