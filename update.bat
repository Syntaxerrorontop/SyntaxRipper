@echo off
echo Checking for updates...
git pull
if %errorlevel% neq 0 (
    echo Update failed (Git error).
    pause
    exit /b
)

echo Updating dependencies...
call backend\venv\Scripts\pip.exe install -r backend\requirements.txt

echo Update complete! Restarting...
start "" "start.bat"
exit
