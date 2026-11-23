@echo off
rem Development start (no supervisor). Uses the venv outside the project if present (see setup_dev.bat).
cd /d "%~dp0"
set "PY=%LOCALAPPDATA%\venvs\skerry\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" app.py --no-supervise
