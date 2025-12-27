@echo off
cd /d "%~dp0"
echo Checking for updates...
git pull origin main
if %errorlevel% neq 0 (
    echo [WARN] Standard update failed. Attempting to stash local changes and retry...
    git stash
    git pull origin main
    if %errorlevel% neq 0 (
        echo [ERROR] Update failed. Please check your internet connection or git status.
        pause
        exit /b
    )
)

echo Updating dependencies...
if exist "backend\venv\Scripts\pip.exe" (
    call backend\venv\Scripts\pip.exe install -r backend\requirements.txt
)

echo Update complete! Restarting...
if exist "start.bat" (
    start "" "start.bat"
) else (
    echo [ERROR] start.bat not found.
    pause
)
exit
