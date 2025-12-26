@echo off
setlocal
title GamesManager V3 - Local Setup

echo ==========================================
echo      GamesManager V3 - Local Setup
echo ==========================================

:: Ensure we are in the script's directory
cd /d "%~dp0"

:: 1. Check/Install Prerequisites
echo.
echo [1/3] Checking System Requirements...

:: Python Check
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python not found. Installing via Winget...
    winget install -e --id Python.Python.3.11 --accept-source-agreements --accept-package-agreements
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install Python. Please install manually.
        pause
        exit /b
    )
    echo Python installed. Please RESTART this script to refresh environment.
    pause
    exit /b
)

:: Node.js Check
node -v >nul 2>&1
if %errorlevel% neq 0 (
    echo Node.js not found. Installing via Winget...
    winget install -e --id OpenJS.NodeJS --accept-source-agreements --accept-package-agreements
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install Node.js. Please install manually.
        pause
        exit /b
    )
    echo Node.js installed. Please RESTART this script.
    pause
    exit /b
)

:: 2. Backend Setup (Local)
echo.
echo [2/3] Setting up Python Environment (Local)...
cd backend
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)
call venv\Scripts\activate.bat
echo Installing Python Packages...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
if %errorlevel% neq 0 echo [WARN] Pip install had issues.
cd ..

:: 3. Frontend Setup (Local)
echo.
echo [3/3] Setting up Frontend (Local)...
cd frontend
echo Installing Node Packages...
call npm install --silent
cd ..

echo.
echo ==========================================
echo        Local Setup Complete! 
echo ==========================================
echo You can now use 'dev_start.bat' or 'start_application.bat'
pause
