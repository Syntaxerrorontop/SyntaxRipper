@echo off
setlocal EnableDelayedExpansion

set "APP_NAME=SyntaxRipper"
set "INSTALL_DIR=%LOCALAPPDATA%\%APP_NAME%"
set "CONFIG_DIR=%APPDATA%\%APP_NAME%"
set "REPO_URL=https://github.com/Syntaxerrorontop/SyntaxRipper.git"
:: NOTE: Replace REPO_URL above with your actual Git URL before distributing!

echo ========================================================
echo      %APP_NAME% Full Installer
echo ========================================================

:: 1. Check & Install Dependencies via Winget
echo [1/5] Checking System Dependencies...

:: Check for Winget
where winget >nul 2>nul
if %errorlevel% neq 0 (
    echo    [!] Winget not found. Please install Winget or manually install Git and Python.
    pause
    exit /b 1
)

set "RESTART_NEEDED=0"

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo    -> Python not found. Installing via Winget...
    winget install Python.Python.3.11 -e --silent --accept-package-agreements --accept-source-agreements
    set "RESTART_NEEDED=1"
) else (
    echo    -> Python is installed.
)

where git >nul 2>nul
if %errorlevel% neq 0 (
    echo    -> Git not found. Installing via Winget...
    winget install Git.Git -e --silent --accept-package-agreements --accept-source-agreements
    set "RESTART_NEEDED=1"
) else (
    echo    -> Git is installed.
)

:: Refresh Environment Variables if anything was installed
if "%RESTART_NEEDED%"=="1" (
    echo    -> Refreshing PATH...
    for /f "tokens=*" %%i in ('powershell -NoProfile -Command "[System.Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path', 'User')"') do set "PATH=%%i"
)

:: 2. Handle AppData (Config) Migration
echo [2/5] Managing Configuration...
if exist "%CONFIG_DIR%" (
    echo    -> Found existing configuration. Backing up...
    mkdir "%TEMP%\SyntaxRipperBackup" >nul 2>nul
    copy "%CONFIG_DIR%\Config\userconfig.json" "%TEMP%\SyntaxRipperBackup\" >nul 2>nul
    copy "%CONFIG_DIR%\Config\games.json" "%TEMP%\SyntaxRipperBackup\" >nul 2>nul
    
    echo    -> Wiping old AppData...
    rmdir /s /q "%CONFIG_DIR%"
    
    echo    -> Restoring configuration...
    mkdir "%CONFIG_DIR%\Config"
    copy "%TEMP%\SyntaxRipperBackup\userconfig.json" "%CONFIG_DIR%\Config\" >nul 2>nul
    copy "%TEMP%\SyntaxRipperBackup\games.json" "%CONFIG_DIR%\Config\" >nul 2>nul
    rmdir /s /q "%TEMP%\SyntaxRipperBackup"
) else (
    echo    -> No existing config found. Fresh install.
)

:: 3. Clone / Update Application
echo [3/5] Installing Application Files...
if exist "%INSTALL_DIR%\.git" (
    echo    -> Updating existing installation...
    cd /d "%INSTALL_DIR%"
    git pull
) else (
    echo    -> Cloning repository...
    if exist "%INSTALL_DIR%" rmdir /s /q "%INSTALL_DIR%"
    git clone "%REPO_URL%" "%INSTALL_DIR%"
    if %errorlevel% neq 0 (
        echo    [!] Failed to clone repository. check REPO_URL in script.
        echo    [!] Fallback: Copying current folder...
        xcopy /s /e /y "%~dp0*" "%INSTALL_DIR%\"
    )
)

:: 4. Setup Python Env
echo [4/5] Setting up Python Environment...
cd /d "%INSTALL_DIR%"
call setup.bat

:: 5. Create Shortcuts
echo [5/5] Creating Start Menu Shortcut...
set "ICON_PATH=%INSTALL_DIR%\frontend\assets\Syntaxripper.ico"
set "TARGET_EXE=%INSTALL_DIR%\Start.vbs"
set "START_MENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs"

powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%START_MENU%\%APP_NAME%.lnk'); $s.TargetPath = '%TARGET_EXE%'; $s.IconLocation = '%ICON_PATH%'; $s.WorkingDirectory = '%INSTALL_DIR%'; $s.Save()"

echo.
echo ========================================================
echo      Installation Complete!
echo ========================================================
echo.
pause
