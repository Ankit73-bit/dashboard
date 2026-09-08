@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Dashboard

cd /d "%~dp0"

set "PYEXE="
set "PYARGS="

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

if not defined PYEXE (
    where python >nul 2>&1
    if %errorlevel%==0 (
        set "PYEXE=python"
        set "PYARGS="
    )
)

if not defined PYEXE (
    echo.
    echo  Python was not found. Install Python 3.11/3.12 and tick
    echo  "Add Python to PATH", then run setup.bat.
    echo.
    pause
    exit /b 1
)

%PYEXE% %PYARGS% "%~dp0dashboard.py"
set "ERR=%errorlevel%"

if not "%ERR%"=="0" (
    echo.
    echo  Something went wrong ^(exit code %ERR%^).
    echo  1. Run setup.bat once on this device
    echo  2. Prefer Python 3.11 or 3.12 from python.org
    echo  3. If you see ModuleNotFoundError, re-run setup.bat
    echo.
    pause
)

endlocal
exit /b %ERR%
