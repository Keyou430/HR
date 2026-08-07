@echo off
title Stop All - Replica Services
echo ============================================
echo   Stopping Replica Frontend ^& Backend
echo ============================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "& { $ports = @(8000, 5173); $labels = @{8000='Backend'; 5173='Frontend'}; foreach ($port in $ports) { $label = $labels[$port]; Write-Host \"[$label] Stopping port $port...\"; $pids = (Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue).OwningProcess | Sort-Object -Unique; if ($pids) { foreach ($p in $pids) { try { $proc = Get-Process -Id $p -ErrorAction Stop; Write-Host \"       Killing $($proc.ProcessName) (PID $p)\"; Stop-Process -Id $p -Force; } catch {} } } else { Write-Host '       No process found.' } }; Write-Host ''; Write-Host 'All Replica services stopped.' }"

echo.
pause
