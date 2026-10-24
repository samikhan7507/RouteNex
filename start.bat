@echo off
REM DAILY start. Double-click this file, then open http://localhost:8000
REM Self-healing: if Python packages are missing it installs them; if the environment is broken it rebuilds it via setup.bat.
cd /d "%~dp0backend"
set "VENV=%LOCALAPPDATA%\RouteNexVenv"
set "PY=%VENV%\Scripts\python.exe"
if not exist "%PY%" goto needsetup
"%PY%" -c "import uvicorn, fastapi, sklearn" >nul 2>&1
if not errorlevel 1 goto run
echo.
echo Some Python packages are missing. Repairing (needs internet, 1-2 minutes)...
"%PY%" -m pip --version >nul 2>&1 || "%PY%" -m ensurepip --upgrade
"%PY%" -m pip install -q -r requirements.txt
"%PY%" -c "import uvicorn, fastapi" >nul 2>&1
if errorlevel 1 goto needsetup
:run
echo.
echo RouteNex running at http://localhost:8000   (press Ctrl+C to stop)
echo First start after an update trains the ML models in the background (about 10 seconds).
echo.
"%PY%" -m uvicorn app:app --reload
pause
exit /b
:needsetup
echo.
echo The Python environment is missing or broken. Rebuilding it now (needs internet, 2-3 minutes)...
call "%~dp0setup.bat"
echo.
echo Setup is done. Close this window and double-click start.bat again.
pause
