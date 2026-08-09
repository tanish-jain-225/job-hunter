@echo off
REM Command 2 helper for Windows: mark a job as applied
cd /d "%~dp0"
python -m jobhunt applied %*
