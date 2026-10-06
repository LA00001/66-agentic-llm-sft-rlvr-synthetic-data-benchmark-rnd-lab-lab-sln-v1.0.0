@echo off
setlocal
echo [v0.38][BUILD249_TEST262] Skill gap proof modules
set FAIL=0
echo --- RLVR/GRPO-style optimization on a Transformer policy ---
"%LOCALAPPDATA%\PortfolioFoundry\cache\runtimes\v048\e7638c6f1caec3a8b00147bb\Scripts\python.exe" "%~dp0skill-upgrades\transformer-rlvr-proof\test_skill.py"
if errorlevel 1 set FAIL=1
"%LOCALAPPDATA%\PortfolioFoundry\cache\runtimes\v048\e7638c6f1caec3a8b00147bb\Scripts\python.exe" "%~dp0skill-upgrades\transformer-rlvr-proof\implementation.py"
if errorlevel 1 set FAIL=1
echo --- Executable office and cybersecurity benchmark oracles ---
"%LOCALAPPDATA%\PortfolioFoundry\cache\runtimes\v031\req-f1945cd6c19e56b3\Scripts\python.exe" "%~dp0skill-upgrades\office-cyber-benchmarks\test_skill.py"
if errorlevel 1 set FAIL=1
"%LOCALAPPDATA%\PortfolioFoundry\cache\runtimes\v031\req-f1945cd6c19e56b3\Scripts\python.exe" "%~dp0skill-upgrades\office-cyber-benchmarks\implementation.py"
if errorlevel 1 set FAIL=1
exit /b %FAIL%
