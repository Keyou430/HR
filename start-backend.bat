@echo off
chcp 65001 >nul
title Replica Backend

cd /d "%~dp0backend"

python --version >nul 2>&1
if %errorlevel% neq 0 (
  echo Python not found
  pause
  exit /b 1
)

pip install -r requirements.txt -q 2>nul

echo.
echo Starting Replica Backend - http://localhost:8000
echo.
set DEBUG=false
python main.py
pause >nul
