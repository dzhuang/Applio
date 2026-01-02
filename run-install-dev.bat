@echo off
title Applio Dev Installer
echo ========================================
echo  Applio Dev Environment Installer
echo  (Uses virtual environment)
echo ========================================
echo.

REM Redirect caches to local directory to save C drive space
set "CURRENT_DIR=%~dp0"
set "UV_CACHE_DIR=%CURRENT_DIR%.uv_cache"
set "PIP_CACHE_DIR=%CURRENT_DIR%.pip_cache"
set "HF_HOME=%CURRENT_DIR%.hf_cache"
set "TORCH_HOME=%CURRENT_DIR%.torch_cache"

REM Ensure cache directories exist
if not exist ".uv_cache" mkdir ".uv_cache"
if not exist ".pip_cache" mkdir ".pip_cache"
if not exist ".hf_cache" mkdir ".hf_cache"
if not exist ".torch_cache" mkdir ".torch_cache"

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH.
    echo Please ensure Python is installed and added to PATH.
    pause
    exit /b 1
)

echo Found Python:
python --version
echo.

REM Check for existing virtual environment
set "VENV_DIR="
if exist ".venv\Scripts\python.exe" (
    set "VENV_DIR=.venv"
    echo Found existing virtual environment: .venv
) else if exist ".env\Scripts\python.exe" (
    set "VENV_DIR=.env"
    echo Found existing virtual environment: .env
)

REM Create .venv if no virtual environment exists
if "%VENV_DIR%"=="" (
    echo No virtual environment found. Creating .venv...
    python -m venv .venv
    if errorlevel 1 goto :error
    set "VENV_DIR=.venv"
    echo Virtual environment created: .venv
)
echo.

REM Activate virtual environment
echo Activating virtual environment: %VENV_DIR%
call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 goto :error

REM Install uv if not available
pip show uv >nul 2>&1
if errorlevel 1 (
    echo Installing uv package installer...
    pip install uv
    if errorlevel 1 goto :error
)

echo.
echo Installing dependencies...
echo This may take a while...
echo.

uv pip install --upgrade setuptools
if errorlevel 1 goto :error

uv pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cu128 --index-strategy unsafe-best-match
if errorlevel 1 goto :error

echo.
echo ========================================
echo  Installation complete!
echo  Virtual environment: %VENV_DIR%
echo  Run 'run-applio-dev.bat' to start.
echo ========================================
echo.
pause
exit /b 0

:error
echo.
echo ERROR: Installation failed. Check the output above.
pause
exit /b 1
