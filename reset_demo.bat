@echo off
REM Clean, repeatable demo state. STOP the app first (Ctrl+C in its window).
cd /d "%~dp0"
echo This RESETS all demo data (users, orders, trips, wallets) and recreates your admin login.
choice /m "Continue"
if errorlevel 2 exit /b
"%LOCALAPPDATA%\RouteNexVenv\Scripts\python.exe" database\reset_demo.py
pause
