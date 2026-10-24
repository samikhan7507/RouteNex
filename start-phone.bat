@echo off
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File demo.ps1
pause
