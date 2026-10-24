@echo off
REM ONE-TIME setup (run again only if something breaks). Double-click this file.
cd /d "%~dp0"
set "VENV=%LOCALAPPDATA%\RouteNexVenv"
echo Creating Python 3.12 environment in %VENV% (outside OneDrive)...
if exist "%VENV%" rmdir /s /q "%VENV%"
py -3.12 -m venv "%VENV%"
if errorlevel 1 (echo.& echo Python 3.12 not found. Install it with: winget install -e --id Python.Python.3.12& pause& exit /b 1)
"%VENV%\Scripts\python.exe" -m ensurepip --upgrade >nul 2>&1
"%VENV%\Scripts\python.exe" -m pip install --upgrade pip
"%VENV%\Scripts\python.exe" -m pip install -r backend\requirements-dev.txt
if errorlevel 1 (echo.& echo Install failed. Check your internet and try again, or send me a screenshot of this window.& pause& exit /b 1)
if not exist backend\.env copy backend\.env.example backend\.env
if not exist database\routenex.db "%VENV%\Scripts\python.exe" database\seed.py --reset
echo.
echo Setup finished. From now on just double-click start.bat
pause
