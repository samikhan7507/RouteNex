@echo off
REM Run AFTER start.bat is running. Checks everything that can go wrong on stage.
cd /d "%~dp0"
"%LOCALAPPDATA%\RouteNexVenv\Scripts\python.exe" tools\preflight.py
pause
