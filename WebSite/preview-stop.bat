@echo off
:: ================================================================
::  preview-stop.bat  -  Kill the hidden Workflow preview server
::
::  Double-click to free port 5173 / stop the background vite dev
::  server started by preview.bat. Safe to run even if nothing is
::  running.
:: ================================================================

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$port = 5173;" ^
  "$conns = @();" ^
  "try { $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue } catch {};" ^
  "if (-not $conns) { Write-Host ('nothing listening on port ' + $port); exit 0 };" ^
  "$pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique;" ^
  "foreach ($procId in $pids) {" ^
  "  try {" ^
  "    $p = Get-Process -Id $procId -ErrorAction SilentlyContinue;" ^
  "    if ($p) {" ^
  "      Write-Host ('stopping ' + $p.ProcessName + ' (pid ' + $procId + ')');" ^
  "      Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue;" ^
  "    };" ^
  "  } catch {};" ^
  "};" ^
  "Write-Host 'preview stopped.'"

timeout /t 2 >nul
exit /b 0
