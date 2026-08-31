@echo off
setlocal enabledelayedexpansion

if not exist nim-router.py (
    set "INSTALL_DIR=%USERPROFILE%\nim-router"
    if not exist "!INSTALL_DIR!" (
        git clone https://github.com/PatrickLmbn/nim-router.git "!INSTALL_DIR!"
    )
    cd /d "!INSTALL_DIR!"
)

echo.
echo  ________   ___  _____ ______   
echo ^|\   ___  ^|\  ^|\   _ \  _   \  
echo \ \  \\ \  \ \  \ \  \\\__\ \  \ 
echo  \ \  \\ \  \ \  \ \  \\|__| \  \ 
echo   \ \  \\ \  \ \  \ \  \    \ \  \ 
echo    \ \__\ \__\ \__\ \__\    \ \__\
echo     \|__| \|__|\|__|\|__|     \|__|
echo             R O U T E R
echo.
echo === Universal Multi-Provider Free Model Router ===
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please download and install Python 3.8+ from https://www.python.org/
    exit /b 1
)

python -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python version must be 3.8 or higher.
    exit /b 1
)

echo [✓] Python found.

echo.
echo Installing Python dependencies...
python -m pip install -r requirements.txt
python -m pip install -e . >nul 2>nul

echo.
if not exist .env (
    if exist .env.example (
        copy .env.example .env >nul
        echo [✓] Created .env from .env.example.
        echo.
        echo === Multi-Provider API Key Setup ===
        set /p key1="Enter NVIDIA API Key (Recommended): "
        set /p groq_key="Enter Groq Free API Key (Optional): "
        set /p cerebras_key="Enter Cerebras Free API Key (Optional): "
        set /p or_key="Enter OpenRouter API Key (Optional): "
        set /p opencode_key="Enter OpenCode API Key (Optional): "
        
        if not "!key1!"=="" (
            echo NVIDIA_API_KEYS=!key1! >> .env
        )
        if not "!groq_key!"=="" (
            echo GROQ_API_KEYS=!groq_key! >> .env
        )
        if not "!cerebras_key!"=="" (
            echo CEREBRAS_API_KEYS=!cerebras_key! >> .env
        )
        if not "!or_key!"=="" (
            echo OPENROUTER_API_KEY=!or_key! >> .env
        )
        if not "!opencode_key!"=="" (
            echo OPENCODE_API_KEY=!opencode_key! >> .env
        )
        echo [✓] Saved API keys to .env
        echo (Tip: Use 'nim keys' anytime to manage or add multiple keys per provider!)
    )
) else (
    echo [✓] .env file already exists.
)

echo.
set "BIN_DIR=%USERPROFILE%\AppData\Local\Microsoft\WindowsApps"
if not exist "!BIN_DIR!" (
    mkdir "!BIN_DIR!"
)

set "CUR_DIR=%CD%"
(
    echo @echo off
    echo python "%CUR_DIR%\nim-router.py" %%*
) > "!BIN_DIR!\nim.bat"
(
    echo @echo off
    echo python "%CUR_DIR%\nim-router.py" %%*
) > "!BIN_DIR!\nimrouter.bat"

echo [✓] Installed 'nim' CLI command to !BIN_DIR!\nim.bat

echo.
where pm2 >nul 2>nul
if %errorlevel% equ 0 (
    echo [✓] PM2 is installed on your system.
    set /p start_pm2="Do you want to start nim-router in the background with PM2 now? (y/N): "
    if /i "!start_pm2!"=="y" (
        pm2 start nim-router.py --name nim-router --interpreter python
        echo [✓] nim-router started in background with PM2.
        echo Use 'nim logs' to view logs or 'nim stop' to stop.
    ) else (
        echo Setup complete! You can start the server anytime with: nim
    )
) else (
    echo Setup complete! You can start the router with: nim
)

endlocal
