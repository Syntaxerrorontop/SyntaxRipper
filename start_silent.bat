@echo off
cd /d "%~dp0"

:: 1. Update Code
git pull origin main >nul 2>nul

:: 2. Update Dependencies (Quietly)
if exist "backend\venv\Scripts\python.exe" (
    "backend\venv\Scripts\python.exe" -m pip install -r backend\requirements.txt --disable-pip-version-check --no-warn-script-location >nul 2>nul
)

:: 3. Launch App
call start.bat
