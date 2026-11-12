@echo off
title WisprWin
cd /d "%~dp0"
.venv\Scripts\python.exe main.py
echo.
echo WisprWin stopped. Press any key to close.
pause >nul
