@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo ============================================================
echo Middle/Senior ML engineer (GigaCode R&D) · Portfolio Application · v0.31
echo ============================================================
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\RuntimeManager.ps1" -OpenBrowser
exit /b %errorlevel%
