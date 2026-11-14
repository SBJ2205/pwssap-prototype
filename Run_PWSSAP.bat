@echo off
title PWSSAP Timetable Management System
color 0B
cd /d "%~dp0"

echo ================================================================
echo   PWSSAP Timetable Management System - Windows Launcher
echo ================================================================
echo.

:: 1. Check for Python virtual environment in backend\venv
set "PYTHON_EXE="
if exist "backend\venv\Scripts\python.exe" (
    set "PYTHON_EXE=backend\venv\Scripts\python.exe"
) else (
    :: 2. Check for system Python (either 'python' or Windows 'py' launcher)
    set "SYS_PY="
    where python >nul 2>&1
    if %errorlevel% equ 0 (
        set "SYS_PY=python"
    ) else (
        where py >nul 2>&1
        if %errorlevel% equ 0 (
            set "SYS_PY=py -3"
        )
    )

    if not defined SYS_PY (
        echo [ERROR] Python was not found on your system!
        echo.
        echo Please install Python (3.10, 3.11, or 3.12) from:
        echo   https://www.python.org/downloads/
        echo.
        echo IMPORTANT: During installation, be sure to check the box:
        echo   "[x] Add python.exe to PATH"
        echo.
        pause
        exit /b 1
    )
    
    echo [*] Setting up local environment (one-time setup)...
    echo [*] Creating virtual environment in backend\venv...
    %SYS_PY% -m venv backend\venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    set "PYTHON_EXE=backend\venv\Scripts\python.exe"
    
    echo [*] Installing required packages (first time only, requires internet)...
    "%PYTHON_EXE%" -m pip install --upgrade pip
    "%PYTHON_EXE%" -m pip install -r backend\requirements.txt
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install dependencies. Please check your internet connection.
        pause
        exit /b 1
    )
    echo [*] Setup complete!
)

echo [*] Starting PWSSAP Timetable Application...
echo [*] The application will open automatically in your browser.
echo.
"%PYTHON_EXE%" run_app.py

if %errorlevel% neq 0 (
    echo.
    echo Application stopped.
    pause
)
