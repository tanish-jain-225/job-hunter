@echo off
REM Unified test, quality, type & coverage runner for Windows
cd /d "%~dp0.."
python run_tests.py %*

