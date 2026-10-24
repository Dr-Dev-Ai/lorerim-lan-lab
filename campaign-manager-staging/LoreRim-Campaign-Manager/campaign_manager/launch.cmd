@echo off
cd /d "%~dp0\.."
where py >nul 2>nul
if errorlevel 1 goto trypython
py -3 -m campaign_manager gui
if errorlevel 1 pause
exit /b
:trypython
where python >nul 2>nul
if errorlevel 1 goto missing
python -m campaign_manager gui
if errorlevel 1 pause
exit /b
:missing
echo Python 3.11 or later with Tkinter is required. No game files have been changed.
pause
