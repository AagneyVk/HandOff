@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -m pip install -r host\requirements.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m host.app
if errorlevel 1 goto failed
exit /b 0
:failed
echo HandOff could not start. Check that Python 3.12 or newer is installed and your internet connection works.
pause
exit /b 1
