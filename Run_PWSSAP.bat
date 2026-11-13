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
    :: 2. Check for system Python
    where python >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] Python was not found on your system!
        echo Please install Python 3.10+ from https://www.python.org or the Microsoft Store.
        echo Make sure to check "Add Python to PATH" during installation.
        echo.
        pause
        exit /b 1
    )
    
    echo [*] Setting up virtual environment in backend\venv...
    python -m venv backend\venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    set "PYTHON_EXE=backend\venv\Scripts\python.exe"
    
    echo [*] Installing required dependencies...
    "%PYTHON_EXE%" -m pip install --upgrade pip
    "%PYTHON_EXE%" -m pip install -r backend\requirements.txt
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
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
