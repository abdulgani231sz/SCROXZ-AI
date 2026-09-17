@echo off
setlocal
cd /d "%~dp0"
py -3.11 --version >nul 2>&1
if errorlevel 1 (
  echo Install Python 3.11 with the Python launcher first.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  py -3.11 -m venv .venv
  if errorlevel 1 goto fail
)
".venv\Scripts\python.exe" -m pip install -r requirements-optional.txt
if errorlevel 1 goto fail
echo PDF, screen capture, local microphone and online Hindi/English voice packages installed.
echo Online voice requires internet and asks permission before sending reply text.
echo The microphone model downloads on first use. Allow time for the download.
pause
exit /b 0
:fail
echo Installation failed. Read the error above and check the internet connection.
pause
exit /b 1
