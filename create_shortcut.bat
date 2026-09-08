@echo off
setlocal EnableExtensions
title Create Desktop Shortcut

cd /d "%~dp0"

set "TARGET=%~dp0run.bat"
set "WORKDIR=%~dp0"
set "ICON=%~dp0dashboard.ico"

echo.
echo  Creating Desktop shortcut...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "$desktop = [Environment]::GetFolderPath('Desktop');" ^
  "if (-not $desktop -or -not (Test-Path -LiteralPath $desktop)) {" ^
  "  $onedrive = Join-Path $env:USERPROFILE 'OneDrive\Desktop';" ^
  "  if (Test-Path -LiteralPath $onedrive) { $desktop = $onedrive }" ^
  "}" ^
  "if (-not $desktop -or -not (Test-Path -LiteralPath $desktop)) {" ^
  "  Write-Host 'ERROR: Desktop folder not found.';" ^
  "  Write-Host 'Tried: [Environment]::GetFolderPath(Desktop) and OneDrive\Desktop';" ^
  "  exit 1" ^
  "}" ^
  "$lnkPath = Join-Path $desktop 'Dashboard.lnk';" ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$s = $ws.CreateShortcut($lnkPath);" ^
  "$s.TargetPath = $env:TARGET;" ^
  "$s.WorkingDirectory = $env:WORKDIR;" ^
  "$s.Description = 'Open Dashboard';" ^
  "if (Test-Path -LiteralPath $env:ICON) { $s.IconLocation = $env:ICON };" ^
  "$s.Save();" ^
  "Write-Host ('Shortcut created: ' + $lnkPath);" ^
  "if (-not (Test-Path -LiteralPath $lnkPath)) { exit 1 }"

if errorlevel 1 (
    echo.
    echo  Something went wrong creating the shortcut.
    echo  You can still open the app by double-clicking run.bat
    echo.
    pause
    exit /b 1
)

echo.
echo  Shortcut created on your Desktop: Dashboard
echo  Double-click it anytime to open the dashboard.
echo.
pause
endlocal
