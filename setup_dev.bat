@echo off
rem Create the dev venv OUTSIDE the project (%LOCALAPPDATA%\venvs\skerry) and install the requirements.
rem Does not upgrade pip: with an EDR active, upgrading pip is the step that gets corrupted.
setlocal
cd /d "%~dp0"
set "VENV=%LOCALAPPDATA%\venvs\skerry"
if not exist "%VENV%\Scripts\python.exe" (
  python -m venv "%VENV%" || goto :err
)
"%VENV%\Scripts\python.exe" -m pip install --disable-pip-version-check --no-cache-dir -r requirements.txt || goto :err
echo.
echo Done. Start with:  .\run_dev.bat
exit /b 0
:err
echo ERROR: if you see "file in use by another process", add %VENV% to the antivirus/EDR exclusions and retry.
exit /b 1
