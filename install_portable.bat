@echo off
setlocal EnableDelayedExpansion

set "APP_NAME=SyntaxRipper"
set "INSTALL_DIR=%~dp0"
:: Remove trailing backslash
if "%INSTALL_DIR:~-1%"=="\" set "INSTALL_DIR=%INSTALL_DIR:~0,-1%"

echo ========================================================
echo      %APP_NAME% Portable Installer
echo ========================================================

:: 1. Enable Portable Mode
echo. > "%INSTALL_DIR%\portable.mode"
echo [1/4] Portable Mode Enabled (marker file created).

:: 2. Check & Install Dependencies via Winget
echo [2/4] Checking System Dependencies...

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo    -> Python not found. Installing via Winget...
    winget install Python.Python.3.11 -e --silent --accept-package-agreements --accept-source-agreements
)

where git >nul 2>nul
if %errorlevel% neq 0 (
    echo    -> Git not found. Installing via Winget...
    winget install Git.Git -e --silent --accept-package-agreements --accept-source-agreements
)

where node >nul 2>nul
if %errorlevel% neq 0 (
    echo    -> Node.js not found. Installing via Winget...
    winget install OpenJS.NodeJS -e --silent --accept-package-agreements --accept-source-agreements
)

:: 3. Setup Python Env
echo [3/4] Setting up Python Environment...
call setup.bat

:: 4. Create Local Shortcut
echo [4/4] Creating Portable Shortcut...
set "ICON_PATH=%INSTALL_DIR%\frontend\assets\Syntaxripper.ico"
set "TARGET_EXE=%INSTALL_DIR%\Start.vbs"

powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%INSTALL_DIR%\%APP_NAME%_Portable.lnk'); $s.TargetPath = '%TARGET_EXE%'; $s.IconLocation = '%ICON_PATH%'; $s.WorkingDirectory = '%INSTALL_DIR%'; $s.Save()"

echo.
echo ========================================================
echo      Portable Installation Complete!
echo ========================================================
echo All data, configs, and games will be stored in:
echo %INSTALL_DIR%
echo.
pause
