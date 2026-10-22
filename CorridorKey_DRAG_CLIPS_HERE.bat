@echo off
setlocal
rem CorridorKey 2.0 launcher. Drag a clip or folder onto this file, or
rem double-click it and drop the clip into the window when asked.
cd /d "%~dp0"
set "PATH=%~dp0;%~dp0venv\Scripts;%PATH%"
set "PYTHONUTF8=1"
set "PYTHONUNBUFFERED=1"
set "OPENCV_IO_ENABLE_OPENEXR=1"

if exist "runtime\python.exe" (
    set "PYTHON=runtime\python.exe"
) else if exist "venv\Scripts\python.exe" (
    set "PYTHON=venv\Scripts\python.exe"
) else (
    echo Python is missing. Restore the portable runtime folder or complete the venv setup.
    pause
    exit /b 1
)

"%PYTHON%" corridorkey_launcher.py %*
set "CORRIDORKEY_EXIT=%ERRORLEVEL%"

echo.
pause
exit /b %CORRIDORKEY_EXIT%
