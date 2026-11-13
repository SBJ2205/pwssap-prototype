@echo off
title Create PWSSAP Desktop Shortcut
color 0A
cd /d "%~dp0"

echo ================================================================
echo   Create PWSSAP Desktop Shortcut
echo ================================================================
echo.

set "TARGET_BAT=%~dp0Run_PWSSAP.bat"
set "SHORTCUT_PATH=%USERPROFILE%\Desktop\PWSSAP Timetable App.lnk"

echo Creating Desktop Shortcut:
echo   "%SHORTCUT_PATH%"
echo.

powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT_PATH%'); $s.TargetPath = '%TARGET_BAT%'; $s.WorkingDirectory = '%~dp0'; $s.Description = 'PWSSAP Timetable Management System'; $s.Save()"

if %errorlevel% equ 0 (
    echo [SUCCESS] Desktop shortcut created successfully!
    echo You can now double-click "PWSSAP Timetable App" directly on your Desktop.
) else (
    echo [ERROR] Failed to create shortcut.
)

echo.
pause
