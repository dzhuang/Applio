@echo off

if /i "%cd%"=="C:\Windows\System32" (
    color 0C
    echo Applio does not require administrator permissions and should be run as a regular user.
    echo.
    pause
    exit /b 1
)

setlocal
set "CURRENT_DIR=%~dp0"
set "HF_HOME=%CURRENT_DIR%.hf_cache"
set "TORCH_HOME=%CURRENT_DIR%.torch_cache"

for %%F in ("%~dp0.") do set "folder_name=%%~nF"

title %folder_name% (Dev)

REM Check for existing virtual environment
set "VENV_DIR="
if exist ".venv\Scripts\python.exe" (
    set "VENV_DIR=.venv"
) else if exist ".env\Scripts\python.exe" (
    set "VENV_DIR=.env"
)

REM Error if no virtual environment exists
if "%VENV_DIR%"=="" (
    color 0C
    echo ERROR: No virtual environment found.
    echo Please run 'run-install-dev.bat' first to create and set up the environment.
    echo.
    echo Expected: .venv or .env directory with Python
    pause
    exit /b 1
)

echo Using virtual environment: %VENV_DIR%
echo Starting Applio (Dev Mode)...
echo.

"%VENV_DIR%\Scripts\python.exe" app.py --open
echo.
pause
