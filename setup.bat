@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Dashboard - First Time Setup
color 0A

cd /d "%~dp0"

echo.
echo  ============================================
echo    Dashboard - First Time Setup
echo    Run this ONCE on any new device
echo  ============================================
echo.
echo  Before you continue, make sure Python is installed:
echo.
echo    1. Install Python 3.11 or 3.12 from python.org
echo       https://www.python.org/downloads/
echo.
echo    2. During install, tick:
echo       [x] Add python.exe to PATH
echo.
echo    Recommended: Python 3.12
echo    Avoid Python 3.14+ if packages fail to install.
echo.
echo  If Python is already installed with PATH enabled, press any key.
echo.
pause
echo.

:: ── Step 1: Locate Python ────────────────────────────────────────────────
echo  [1/5] Checking Python installation...

set "PYEXE="
set "PYARGS="

:: Prefer the Windows py launcher targeting 3.10–3.13 (best wheel support)
where py >nul 2>&1
if %errorlevel%==0 (
    for %%V in (3.12 3.11 3.13 3.10 3) do (
        if not defined PYEXE (
            py -%%V -c "import sys" >nul 2>&1
            if !errorlevel!==0 (
                set "PYEXE=py"
                set "PYARGS=-%%V"
            )
        )
    )
)

:: Fallback: python on PATH
if not defined PYEXE (
    where python >nul 2>&1
    if %errorlevel%==0 (
        python -c "import sys" >nul 2>&1
        if !errorlevel!==0 (
            set "PYEXE=python"
            set "PYARGS="
        )
    )
)

:: Fallback: python3
if not defined PYEXE (
    where python3 >nul 2>&1
    if %errorlevel%==0 (
        python3 -c "import sys" >nul 2>&1
        if !errorlevel!==0 (
            set "PYEXE=python3"
            set "PYARGS="
        )
    )
)

if not defined PYEXE (
    echo.
    echo  ERROR: Python was not found.
    echo.
    echo  Install Python 3.11 or 3.12 from:
    echo    https://www.python.org/downloads/
    echo.
    echo  IMPORTANT during install:
    echo    [x] Add python.exe to PATH
    echo    [x] Disable path length limit  ^(optional but recommended^)
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('%PYEXE% %PYARGS% --version 2^>^&1') do set "PYVER=%%i"
echo  Found: !PYVER!  ^(%PYEXE% %PYARGS%^)

:: Require Python >= 3.10
%PYEXE% %PYARGS% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ERROR: Python 3.10 or newer is required. You have !PYVER!.
    echo  Please install Python 3.11 or 3.12 and re-run setup.bat.
    echo.
    pause
    exit /b 1
)

:: Warn on very new Python ^(wheels may be missing for some packages^)
%PYEXE% %PYARGS% -c "import sys; raise SystemExit(0 if sys.version_info < (3, 14) else 1)" >nul 2>&1
if errorlevel 1 (
    echo.
    echo  WARNING: Python 3.14+ detected. Some packages may not have
    echo  Windows wheels yet. If install fails, use Python 3.12 instead.
    echo.
)
echo.

:: ── Step 2: Prepare pip (do NOT upgrade pip itself) ──────────────────────
:: Upgrading pip on Windows often crashes with:
::   ValueError: Unable to find resource t64.exe in package pip._vendor.distlib
:: Existing pip is enough to install packages. Only refresh setuptools/wheel.
echo  [2/5] Preparing pip...
%PYEXE% %PYARGS% -m pip --version >nul 2>&1
if errorlevel 1 (
    echo  pip missing — repairing with ensurepip...
    %PYEXE% %PYARGS% -m ensurepip --upgrade >nul 2>&1
)
%PYEXE% %PYARGS% -m pip --version
if errorlevel 1 (
    echo.
    echo  ERROR: pip is broken on this PC.
    echo  Fix: reinstall Python 3.12 from python.org ^(tick Add to PATH^),
    echo  then re-run setup.bat.
    echo.
    pause
    exit /b 1
)
%PYEXE% %PYARGS% -m pip install --upgrade --prefer-binary "setuptools>=69" "wheel>=0.43"
if errorlevel 1 (
    echo  WARNING: Could not upgrade setuptools/wheel. Continuing anyway...
)
echo  Done.
echo.

:: ── Step 3: Install core requirements ────────────────────────────────────
echo  [3/5] Installing core libraries...
echo  ^(This may take a few minutes on first run^)
echo.

%PYEXE% %PYARGS% -m pip install --prefer-binary -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo.
    echo  First attempt failed — retrying once...
    echo.
    %PYEXE% %PYARGS% -m pip install --prefer-binary --upgrade -r "%~dp0requirements.txt"
)
if errorlevel 1 (
    echo.
    echo  ERROR: Core libraries failed to install.
    echo.
    echo  Common fixes:
    echo    1. Use Python 3.11 or 3.12 ^(not 3.14^) from python.org
    echo    2. Tick "Add Python to PATH" and re-open this window
    echo    3. Check internet / firewall / proxy
    echo    4. Run this setup.bat as Administrator
    echo.
    pause
    exit /b 1
)
echo  Core libraries installed.
echo.

:: ── Step 4: Optional packages (rembg etc.) ───────────────────────────────
echo  [4/5] Installing optional AI packages ^(rembg^)...
echo  ^(Safe to fail — only needed for BG Changer / BW Converter^)
echo.
%PYEXE% %PYARGS% -m pip install --prefer-binary -r "%~dp0requirements-optional.txt"
if errorlevel 1 (
    echo  Optional packages skipped. Dashboard will still run.
) else (
    echo  Optional packages installed.
)
echo.

:: ── Step 5: pywin32 post-install ─────────────────────────────────────────
echo  [5/5] Configuring Windows libraries ^(pywin32^)...
%PYEXE% %PYARGS% -c "import win32api" >nul 2>&1
if errorlevel 1 (
    %PYEXE% %PYARGS% -m pywin32_postinstall -install >nul 2>&1
)
%PYEXE% %PYARGS% -c "import customtkinter, pandas, openpyxl, PyPDF2, pypdf, requests; print('  Import check OK')"
if errorlevel 1 (
    echo.
    echo  WARNING: Some core imports still failed. Re-run setup.bat
    echo  or share the error text above for help.
    echo.
) else (
    echo  Import check passed.
)
echo.

echo  ============================================
echo    Setup complete!
echo.
echo    Next: double-click  create_shortcut.bat
echo    Then open the Dashboard shortcut daily,
echo    or double-click  run.bat
echo  ============================================
echo.
pause
endlocal
