@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

echo ===================================
echo   NVIDIA NIM Router Windows Setup
echo ===================================
echo.

:: 1. Detect Python
set PYTHON_CMD=
where python >nul 2>nul
if %errorlevel% equ 0 (
    set PYTHON_CMD=python
) else (
    where py >nul 2>nul
    if %errorlevel% equ 0 (
        set PYTHON_CMD=py -3
    )
)

if "%PYTHON_CMD%"=="" (
    echo [ERROR] Python is not installed or not added to PATH.
    echo.
    echo Please install Python 3.8+ from https://www.python.org/downloads/
    echo (Make sure to check "Add python.exe to PATH" during installation)
    echo.
    echo Or install via Windows Package Manager:
    echo   winget install Python.Python.3.11
    echo.
    pause
    exit /b 1
)

for /f "delims=" %%v in ('%PYTHON_CMD% --version 2^>^&1') do echo [✓] Found %%v

:: 2. Install Dependencies
echo.
echo Installing Python dependencies...
%PYTHON_CMD% -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo [!] Standard pip install failed. Creating virtual environment (.venv)...
    %PYTHON_CMD% -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install dependencies in virtual environment.
        pause
        exit /b 1
    )
    echo [✓] Dependencies installed in .venv
) else (
    echo [✓] Dependencies installed successfully.
)

:: 3. Configure .env
echo.
if not exist .env (
    if exist .env.example (
        copy .env.example .env >nul
        echo [✓] Created .env from .env.example
        
        set /p USER_KEY="Enter your NVIDIA API Key (leave empty to configure later in .env): "
        if not "!USER_KEY!"=="" (
            powershell -Command "(Get-Content .env) -replace '^NVIDIA_API_KEY=.*', 'NVIDIA_API_KEY=!USER_KEY!' | Set-Content .env"
            echo [✓] NVIDIA_API_KEY saved to .env
        ) else (
            echo [!] Remember to set your NVIDIA_API_KEY in .env before running.
        )
    )
) else (
    echo [✓] .env file already exists.
)

:: 4. Background service / PM2 options
echo.
where pm2 >nul 2>nul
if %errorlevel% equ 0 (
    echo [✓] PM2 is installed on your system.
    set /p START_PM2="Do you want to start nim-router with PM2 now? (y/N): "
    if /i "!START_PM2!"=="y" (
        pm2 start ecosystem.config.js
        echo [✓] nim-router started in background with PM2.
        echo Use 'pm2 logs nim-router' to view logs or 'pm2 stop nim-router' to stop.
    ) else (
        echo Setup complete! You can start the server anytime with: python nim-router.py
    )
) else (
    echo Setup complete!
    echo To start the router in the foreground:
    echo   python nim-router.py
    echo.
    echo (Optional) To run in background with PM2, install Node.js then run:
    echo   npm install -g pm2
    echo   pm2 start ecosystem.config.js
)

echo.
pause
