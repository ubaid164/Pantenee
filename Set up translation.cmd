@echo off
setlocal
pushd "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    py -3.12 -m venv .venv
    if errorlevel 1 goto setup_failed
)

".venv\Scripts\python.exe" -m pip install --only-binary=:all: --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu/ llama-cpp-python==0.3.36
if errorlevel 1 goto setup_failed
".venv\Scripts\python.exe" setup_translation.py
if errorlevel 1 goto setup_failed
echo Local translation is ready. Open Run with Python.cmd.
pause
popd
exit /b 0

:setup_failed
echo Translation setup could not finish. Check the error above and run this file again.
pause
popd
exit /b 1
