@echo off
setlocal
set "DIR=%~dp0"
if exist "%DIR%.venv\Scripts\python.exe" (
    "%DIR%.venv\Scripts\python.exe" "%DIR%nim-router.py" %*
) else (
    python "%DIR%nim-router.py" %*
)
