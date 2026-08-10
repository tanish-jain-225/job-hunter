@echo off
:: Setup Windows Task Scheduler for Daily Job Hunter Digest
:: Runs python auto.py every day at 9:00 AM

set TASK_NAME=JobHunterDailyDigest
set SCRIPT_DIR=%~dp0
set SCRIPT_PATH=%SCRIPT_DIR%auto.py

echo =========================================================
echo  Setting up Windows Scheduled Task: %TASK_NAME%
echo  Target: %SCRIPT_PATH%
echo  Schedule: Daily at 9:00 AM
echo =========================================================

schtasks /create /tn "%TASK_NAME%" /tr "python \"%SCRIPT_PATH%\"" /sc daily /st 09:00 /f

if %ERRORLEVEL% EQU 0 (
    echo.
    echo SUCCESS: Task '%TASK_NAME%' created successfully!
    echo It will run automatically every day at 09:00 AM.
) else (
    echo.
    echo ERROR: Failed to create scheduled task. Try running this script as Administrator.
)
pause
