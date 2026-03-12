@echo off
title Dashboard
python "%~dp0dashboard.py"
if %errorlevel% neq 0 (
    echo.
    echo  Something went wrong. Have you run setup.bat yet?
    echo.
    pause
)
