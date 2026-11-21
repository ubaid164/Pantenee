@echo off
setlocal
pushd "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    py -3.12 -m venv .venv
    if errorlevel 1 goto setup_failed
)

".venv\Scripts\python.exe" -c "import faster_whisper, sounddevice" >nul 2>&1
if errorlevel 1 (
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto setup_failed
)

".venv\Scripts\python.exe" pantenee.py
if errorlevel 1 goto setup_failed
popd
exit /b 0

:setup_failed
echo The Python launch failed. Install an approved 64-bit Python 3.12 with Tkinter and check the error above.
pause
popd
exit /b 1
