@echo off
title Vasudha Real Estate Platform - Patel Om
color 0B

:: Ensure current working directory is always the script folder
cd /d "%~dp0"

echo ================================================================
echo           VASUDHA REAL ESTATE PRICE PREDICTION
echo           Ahmedabad Property Valuation Platform
echo           Architected ^& Developed by Patel Om
echo ================================================================
echo.

:: Detect Python executable
where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set PY_CMD=python
) else (
    where py >nul 2>nul
    if %ERRORLEVEL% EQU 0 (
        set PY_CMD=py
    ) else (
        echo [ERROR] Python is not installed or not found in system PATH.
        echo Please download and install Python from https://www.python.org/
        echo Make sure to check "Add Python to PATH" during installation.
        echo.
        pause
        exit /b 1
    )
)

echo [1/3] Checking dependencies...
%PY_CMD% -m pip install -r requirements.txt --quiet --no-warn-script-location
if %ERRORLEVEL% NEQ 0 (
    echo [WARNING] Dependency check encountered an issue, attempting to proceed...
)

echo.
echo [2/3] Starting Vasudha Real Estate Server...
echo [3/3] Opening browser at http://127.0.0.1:5000 ...
echo.
echo ----------------------------------------------------------------
echo   Server is running at: http://127.0.0.1:5000
echo   Keep this black window OPEN while using the application.
echo   To close the app, simply close this window.
echo ----------------------------------------------------------------
echo.

:: Open browser with a 2-second delay so Flask server starts listening first
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:5000"

:: Start the Flask application
%PY_CMD% frontend.py

echo.
echo Application stopped.
pause
