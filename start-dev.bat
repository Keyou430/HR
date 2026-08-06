@echo off
chcp 65001 >nul
title HR Platform - Dev Environment

echo ============================================
echo   HR Platform - Development Environment
echo ============================================
echo.

echo [1/3] Checking Docker...
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker not found! Please install Docker Desktop.
    pause
    exit /b 1
)
echo        Docker found.

echo [2/3] Checking .env...
cd /d "%~dp0backend"
if not exist .env (
    echo [INFO]  .env not found - copying from .env.example
    copy .env.example .env >nul
    echo [INFO]  Please edit backend\.env with your settings.
)
cd /d "%~dp0"

echo [3/3] Starting development services...
docker compose -f docker/compose.base.yml -f docker/compose.dev.yml up -d
if %errorlevel% neq 0 (
    echo [ERROR] Docker compose failed to start.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Development Environment Ready
echo ============================================
echo.
echo   API docs:  http://localhost:8000/docs
echo   Health:    http://localhost:8000/health
echo   PostgreSQL: localhost:5432
echo.
echo   Start frontend (separate terminal):
echo     cd frontend ^&^& npm run dev
echo.
echo ============================================
echo   Press any key to close (containers stay running)
echo ============================================
pause >nul
