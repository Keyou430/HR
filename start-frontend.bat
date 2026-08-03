@echo off
chcp 65001 >nul
title Replica Frontend - Vite Dev Server (Port 5173)

echo ============================================
echo   Replica Frontend - Vite Dev Server
echo ============================================
echo.

cd /d "%~dp0frontend"

echo [1/2] Checking Node.js...
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js not found! Please install Node.js 18+ and add it to PATH.
    pause
    exit /b 1
)
echo        Node.js found:
node --version

echo [2/2] Installing dependencies...
call npm install
if %errorlevel% neq 0 (
    echo [ERROR] npm install failed!
    pause
    exit /b 1
)

echo.
echo Starting Vite dev server on http://localhost:5173
echo API proxy: /api -^> http://127.0.0.1:8000
echo.
echo ============================================
echo.

call npm run dev

pause
