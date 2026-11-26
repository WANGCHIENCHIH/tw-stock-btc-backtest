@echo off
setlocal
cd /d "%~dp0"
python beginner.py %*
set result=%errorlevel%
if not defined CI pause
exit /b %result%
