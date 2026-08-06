@echo off
chcp 65001 >nul
title Stop All - Replica Services
echo ============================================
echo   Stopping Replica Frontend ^& Backend
echo ============================================
echo.

:: ── Backend (port 8000) ──────────────────────────────────
set "BACKEND_PORT=8000"
echo [1/2] Stopping backend (port %BACKEND_PORT%)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%BACKEND_PORT% " ^| findstr "LISTENING" 2^>nul') do (
    set "PID=%%a"
    goto :found_backend
)
echo        No backend process found on port %BACKEND_PORT%.
goto :frontend

:found_backend
taskkill /PID %PID% /F >nul 2>&1
if %errorlevel% equ 0 (
    echo        Backend process (PID %PID%) stopped.
) else (
    echo        Failed to stop PID %PID%.
)

:frontend
:: ── Frontend (port 5173 — Vite default) ──────────────────
set "FRONTEND_PORT=5173"
echo [2/2] Stopping frontend (port %FRONTEND_PORT%)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%FRONTEND_PORT% " ^| findstr "LISTENING" 2^>nul') do (
    set "PID=%%a"
    goto :found_frontend
)
echo        No frontend process found on port %FRONTEND_PORT%.
goto :done

:found_frontend
taskkill /PID %PID% /F >nul 2>&1
if %errorlevel% equ 0 (
    echo        Frontend process (PID %PID%) stopped.
) else (
    echo        Failed to stop PID %PID%.
)

:done
echo.
echo ============================================
echo   All Replica services stopped.
echo ============================================
pause >nul
