@echo off
setlocal EnableDelayedExpansion
rem =====================================================================
rem  CorridorKey 2.0 - one-click source setup for Windows
rem
rem  Prepares this source checkout so you can run CorridorKey without
rem  following the manual steps in README.md:
rem
rem    1. Finds/creates a Python 3.11 virtual environment (venv)
rem    2. Installs pinned CUDA 12.8 PyTorch 2.9.1 and requirements.txt
rem    3. Downloads the model weights and foundation models (~5 GB;
rem       re-running skips files that are already present)
rem    4. Checks for ffmpeg on your PATH and keeps a copy next to the
rem       app files (needed for the portable build)
rem    5. Optionally builds the portable runtime folder via
rem       tools\make_portable.ps1, after which the whole folder is
rem       self-contained and can be copied to another compatible PC
rem
rem  Usage:
rem    setup_portable.bat             interactive prompt at the end
rem    setup_portable.bat /PORTABLE   also build the portable runtime
rem
rem  Requires: Windows x64, an NVIDIA GPU with a current driver, and
rem  Python 3.11 (winget install Python.Python.3.11 if missing).
rem =====================================================================
cd /d "%~dp0"

if /i "%~1"=="/PORTABLE" set "WANT_PORTABLE=Y"

echo.
echo === CorridorKey 2.0 source setup (Windows) ===
echo Working directory: %cd%
echo.

rem ---------------------------------------------------------------------
rem 1. Find a Python 3.11 interpreter
rem ---------------------------------------------------------------------
set "PYCMD="
py -3.11 --version >nul 2>nul
if !errorlevel!==0 set "PYCMD=py -3.11"
if not defined PYCMD (
    set "PYVER="
    python --version >nul 2>nul
    if !errorlevel!==0 for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PYVER=%%v"
    if "!PYVER:~0,5!"=="3.11." set "PYCMD=python"
)
if not defined PYCMD (
    set "PYVER="
    python3 --version >nul 2>nul
    if !errorlevel!==0 for /f "tokens=2" %%v in ('python3 --version 2^>^&1') do set "PYVER=%%v"
    if "!PYVER:~0,5!"=="3.11." set "PYCMD=python3"
)
if not defined PYCMD (
    echo ERROR: Python 3.11 (Windows x64) is required and was not found.
    echo Install it with:
    echo     winget install Python.Python.3.11
    echo or from https://www.python.org/downloads/
    echo then re-run this script.
    echo.
    pause
    exit /b 1
)
echo Using interpreter: %PYCMD%
%PYCMD% --version

rem ---------------------------------------------------------------------
rem 2. Virtual environment
rem ---------------------------------------------------------------------
set "VENV_PY=venv\Scripts\python.exe"
if exist "%VENV_PY%" (
    echo Reusing existing venv (delete the venv folder to rebuild it).
) else (
    echo.
    echo Creating venv...
    %PYCMD% -m venv venv
    if errorlevel 1 (
        echo.
        echo ERROR: venv creation failed.
        pause
        exit /b 1
    )
)
"%VENV_PY%" --version

rem ---------------------------------------------------------------------
rem 3. Pinned PyTorch (CUDA 12.8) + remaining dependencies
rem ---------------------------------------------------------------------
echo.
echo Installing PyTorch 2.9.1 and torchvision 0.24.1 (CUDA 12.8 wheels).
echo This download is about 2.5 GB and can take a while...
"%VENV_PY%" -m pip install torch==2.9.1 torchvision==0.24.1 --index-url https://download.pytorch.org/whl/cu128
if errorlevel 1 (
    echo.
    echo ERROR: PyTorch installation failed. Check your network and re-run.
    pause
    exit /b 1
)
echo.
echo Installing the remaining dependencies (requirements.txt)...
"%VENV_PY%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: dependency installation failed. Re-run this script to retry.
    pause
    exit /b 1
)

rem ---------------------------------------------------------------------
rem 4. Model weights + foundation models (~5 GB, idempotent)
rem ---------------------------------------------------------------------
echo.
echo Downloading model weights and foundation models (about 5 GB;
echo files that are already present are skipped)...
"%VENV_PY%" scripts\download_weights.py
if errorlevel 1 (
    echo.
    echo ERROR: weight download failed. Re-run this script later to resume.
    pause
    exit /b 1
)

rem ---------------------------------------------------------------------
rem 5. ffmpeg
rem ---------------------------------------------------------------------
echo.
if not exist ffmpeg.exe (
    set "FFMPEG_PATH="
    where ffmpeg >nul 2>nul
    if errorlevel 1 (
        echo WARNING: ffmpeg was not found on your PATH.
        echo CorridorKey needs ffmpeg to encode its video outputs.
        echo Install it with:
        echo     winget install Gyan.FFmpeg
        echo or from https://www.gyan.dev/ffmpeg/builds/  (add to PATH)
        echo then re-open this terminal and re-run this script.
    ) else (
        for /f "delims=" %%f in ('where ffmpeg') do if not defined FFMPEG_PATH set "FFMPEG_PATH=%%f"
        if defined FFMPEG_PATH (
            set "FFMPEG_PATH=!FFMPEG_PATH:"=!"
            copy /y "%FFMPEG_PATH%" ffmpeg.exe >nul
            if errorlevel 1 (
                echo WARNING: could not copy ffmpeg.exe next to the app files.
            ) else (
                echo ffmpeg found on PATH; copied ffmpeg.exe next to the app files.
            )
        )
    )
) else (
    echo ffmpeg.exe already present next to the app files.
)

rem ---------------------------------------------------------------------
rem 6. Optional portable runtime build
rem ---------------------------------------------------------------------
set "WANT="
if defined WANT_PORTABLE set "WANT=Y"
if not defined WANT (
    echo.
    set /p WANT=Build the portable runtime folder now? [Y/N]: 
)
if /i not "!WANT:~0,1!"=="Y" goto :done

echo.
echo Checking for the Visual Studio C++ app-local redistributable
echo (required by the portable build)...
set "VCREDIST="
for /d %%d in ("C:\Program Files\Microsoft Visual Studio\*\*\VC\Redist\MSVC\*\x64\Microsoft.VC*.CRT") do if not defined VCREDIST set "VCREDIST=%%~d"
if not defined VCREDIST for /d %%d in ("C:\Program Files (x86)\Microsoft Visual Studio\*\*\VC\Redist\MSVC\*\x64\Microsoft.VC*.CRT") do if not defined VCREDIST set "VCREDIST=%%~d"
if not defined VCREDIST (
    echo The Microsoft.VC143.CRT app-local redistributable was not found.
    echo The portable build needs it. Install Visual Studio 2022 Build
    echo Tools with the "C++ Build Tools" workload, for example:
    echo     winget install Microsoft.VisualStudio.2022.BuildTools
    echo then re-run this script. Skipping the portable build.
    echo.
    goto :done
)

echo.
echo Building the portable runtime (copies the Python runtime and all
echo installed packages, including CUDA PyTorch, into runtime\)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\make_portable.ps1"
if errorlevel 1 (
    echo.
    echo Portable build failed (see message above). The venv still works:
    echo use CorridorKey_DRAG_CLIPS_HERE.bat as usual.
    goto :done
)
echo.
echo Portable runtime built. runtime\ plus ffmpeg.exe, weights\, vfms\
echo and the app files make a self-contained folder; see PORTABLE_README.txt.

:done
echo.
echo === Setup complete ===
echo You can now run CorridorKey_DRAG_CLIPS_HERE.bat (drag a clip onto it).
echo Requires an NVIDIA GPU (RTX 30-series or newer; 4 GB VRAM up to 1440p,
echo 6 GB for 4K) with a current driver.
echo.
pause
exit /b 0
