@echo off
title Dashboard - First Time Setup
color 0A

echo.
echo  ============================================
echo    Dashboard - First Time Setup
echo    Run this ONCE on any new device
echo  ============================================
echo.

:: ── Step 1: Check Python ──────────────────────────────────────────────────
echo  [1/4] Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  ERROR: Python is not installed or not in PATH.
    echo.
    echo  Please install Python from: https://www.python.org/downloads/
    echo  Make sure to tick "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version') do echo  Found: %%i
echo.

:: ── Step 2: Upgrade pip ───────────────────────────────────────────────────
echo  [2/4] Upgrading pip...
python -m pip install --upgrade pip --quiet
echo  Done.
echo.

:: ── Step 3: Install requirements ─────────────────────────────────────────
echo  [3/4] Installing required libraries...
echo  (This may take a minute on first run)
echo.
python -m pip install -r "%~dp0requirements.txt"
if %errorlevel% neq 0 (
    echo.
    echo  ERROR: Some libraries failed to install.
    echo  Check your internet connection and try again.
    echo.
    pause
    exit /b 1
)
echo.

:: ── Step 4: Done ─────────────────────────────────────────────────────────
echo  [4/4] Setup complete!
echo.
echo  ============================================
echo    All done! You can now run the dashboard
echo    by double-clicking  run.bat
echo  ============================================
echo.
pause
