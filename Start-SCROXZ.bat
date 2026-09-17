@echo off
setlocal
cd /d "%~dp0"
py -3.11 --version >nul 2>&1
if errorlevel 1 (
  echo Install Python 3.11 for Windows from https://www.python.org/downloads/windows/
  echo Include the Python launcher and Tcl/Tk support during installation.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  py -3.11 -m venv .venv
  if errorlevel 1 goto fail
)
".venv\Scripts\python.exe" app.py
if errorlevel 1 goto fail
exit /b 0
:fail
echo SCROXZ could not start. Review the error above.
pause
exit /b 1
