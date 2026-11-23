@echo off
setlocal
cd /d "%~dp0"
set "PY=%LOCALAPPDATA%\venvs\skerry\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
echo === Skerry: build ===
if not exist assets\brand\skerry.ico (
  echo ERROR: assets\brand\skerry.ico is missing
  exit /b 1
)
"%PY%" -m pip install -r requirements.txt pyinstaller || goto :err
"%PY%" -m PyInstaller build\skerry.spec --noconfirm --distpath dist --workpath build\work || goto :err
set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist %ISCC% (
  %ISCC% build\installer.iss || goto :err
  echo Installer created in dist\
) else (
  echo Inno Setup 6 not found: only dist\Skerry was built. Install Inno Setup to build the setup.
)
exit /b 0
:err
echo ERROR during the build
exit /b 1
