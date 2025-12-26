@echo off
setlocal
title GamesManager V3

:: Ensure we are in the correct directory
cd /d "%~dp0"

:: 1. Activate Python Virtual Environment
if not exist "backend\venv" (
    echo [ERROR] Virtual environment not found. Please run 'setup.bat' first.
    exit /b 1
)

call backend\venv\Scripts\activate.bat

:: 2. Start Electron Frontend
cd frontend
call npm start

:: Deactivate on exit
if defined VIRTUAL_ENV call deactivate
exit /b 0