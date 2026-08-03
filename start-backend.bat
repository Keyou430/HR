@echo off
chcp 65001 >nul
title Replica Backend - FastAPI (Port 8000)

echo ============================================
echo   Replica Backend - FastAPI Server
echo ============================================
echo.

cd /d "%~dp0backend"

echo [1/2] Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found! Please install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)
echo        Python found:
python --version

echo [2/2] Installing dependencies...
pip install -r requirements.txt -q
if %errorlevel% neq 0 (
    echo [WARN] Some dependencies may have failed to install.
)

echo.
echo Starting FastAPI server on http://0.0.0.0:8000
echo API docs: http://localhost:8000/docs
echo.
echo ============================================
echo.

python main.py

pause
