@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\RuntimeManager.ps1" -Smoke
if errorlevel 1 exit /b %errorlevel%
echo RUNTIME / UI SMOKE PASS
