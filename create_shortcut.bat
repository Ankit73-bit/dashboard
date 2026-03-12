@echo off
title Create Desktop Shortcut

:: Path to run.bat in this folder
set "TARGET=%~dp0run.bat"

:: Desktop shortcut path
set "SHORTCUT=%USERPROFILE%\Desktop\Dashboard.lnk"

:: Optional icon
set "ICON=%~dp0dashboard.ico"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath = '%TARGET%'; $s.WorkingDirectory = '%~dp0'; $s.Description = 'Open Dashboard'; if (Test-Path '%ICON%') { $s.IconLocation = '%ICON%' }; $s.Save()"

if exist "%SHORTCUT%" (
    echo.
    echo ✓ Shortcut created on your Desktop: Dashboard
    echo Double-click it anytime to open the dashboard.
    echo.
) else (
    echo.
    echo Something went wrong.
    echo.
)

pause