@echo off
title Friday AI Assistant
cd /d "%~dp0"
echo ======================================================================
echo                F.R.I.D.A.Y.  -  P E R S O N A L   A I
echo            "Cloud-Brain, Local-Body" Autonomous System
echo ======================================================================
echo Starting Friday System Tray Daemon and Jarvis HUD...
".\.venv\Scripts\python.exe" -m friday.system.tray
if errorlevel 1 (
    echo.
    echo [!] Friday encountered an issue. Starting interactive CLI fallback...
    ".\.venv\Scripts\python.exe" main.py
    pause
)
