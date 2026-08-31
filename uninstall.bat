@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"
set "DIR=%~dp0"

echo =====================================
echo   NIM Router Uninstaller
echo =====================================
echo.


where pm2 >nul 2>nul
if %errorlevel% equ 0 (
    echo Stopping and deleting nim-router from PM2...
    pm2 stop nim-router >nul 2>nul
    pm2 delete nim-router >nul 2>nul
    pm2 save >nul 2>nul
    echo [✓] PM2 process removed.
)

if exist .venv (
    set /p REMOVE_VENV="Remove Python virtual environment (.venv)? (y/N): "
    if /i "!REMOVE_VENV!"=="y" (
        rmdir /s /q .venv
        echo [✓] Removed .venv folder.
    )
)

echo Cleaning temporary logs and cache...
del /q *.log >nul 2>nul
if exist __pycache__ rmdir /s /q __pycache__
if exist tests\__pycache__ rmdir /s /q tests\__pycache__
echo [✓] Logs and cache cleaned.

if exist .env (
    set /p REMOVE_ENV="Delete .env file (containing your NVIDIA_API_KEY)? (y/N): "
    if /i "!REMOVE_ENV!"=="y" (
        del /q .env
        echo [✓] Removed .env file.
    )
)

echo.
echo [✓] Uninstallation complete!
echo.
pause
