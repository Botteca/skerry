@echo off
rem Local build: PyInstaller -> dist\Skerry\, Inno Setup -> dist\Skerry-Setup-X.Y.Z.exe, plus dist\SHA256SUMS.txt.
rem The version comes only from skerry\__init__.py (read by tools\release.py). Releases are built by
rem .github\workflows\release.yml when a v* tag is pushed; this script is for local testing.
setlocal
cd /d "%~dp0"
set "PY=%LOCALAPPDATA%\venvs\skerry\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
echo === Skerry: build ===
if not exist assets\brand\skerry.ico (
  echo ERROR: assets\brand\skerry.ico is missing
  exit /b 1
)
for /f "usebackq delims=" %%v in (`"%PY%" tools\release.py version`) do set "VER=%%v"
if "%VER%"=="" goto :err
echo Version %VER%
"%PY%" -m pip install -r requirements.txt pyinstaller || goto :err
"%PY%" -m PyInstaller build\skerry.spec --noconfirm --distpath dist --workpath build\work || goto :err
set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist %ISCC% (
  %ISCC% /DAppVersion=%VER% build\installer.iss || goto :err
  "%PY%" tools\release.py sums dist\Skerry-Setup-%VER%.exe > dist\SHA256SUMS.txt || goto :err
  echo Installer and SHA256SUMS.txt created in dist\
) else (
  echo Inno Setup 6 not found: only dist\Skerry was built. Install Inno Setup to build the setup.
)
exit /b 0
:err
echo ERROR during the build
exit /b 1
