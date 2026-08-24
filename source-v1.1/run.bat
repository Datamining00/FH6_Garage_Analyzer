@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "HIDDEN_MODE=0"
if /i "%~1"=="--hidden" set "HIDDEN_MODE=1"

set "APP_DATA=%LOCALAPPDATA%\FH6GarageAnalyzer"
set "VENV_DIR=%APP_DATA%\venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "PYTHONDONTWRITEBYTECODE=1"

if not exist "%APP_DATA%" mkdir "%APP_DATA%" >nul 2>&1

echo ========================================
echo   FH6 Assistant - Launcher

echo   App folder : %CD%
echo   Runtime    : %VENV_DIR%
echo ========================================
echo.

rem 1) Keep the Python environment OUTSIDE the application folder.
if not exist "%VENV_PY%" (
    echo [1/3] Creating Python virtual environment in LocalAppData...

    py -3.13 --version >nul 2>&1
    if not errorlevel 1 (
        py -3.13 -m venv "%VENV_DIR%"
        goto :venv_created
    )

    py -3.12 --version >nul 2>&1
    if not errorlevel 1 (
        py -3.12 -m venv "%VENV_DIR%"
        goto :venv_created
    )

    py -3 --version >nul 2>&1
    if not errorlevel 1 (
        py -3 -m venv "%VENV_DIR%"
        goto :venv_created
    )

    python --version >nul 2>&1
    if not errorlevel 1 (
        python -m venv "%VENV_DIR%"
        goto :venv_created
    )

    echo.
    echo [ERROR] Python 3 was not found.
    echo Install Python 3.12 or newer, then run this file again.
    goto :failed
)

:venv_created
if not exist "%VENV_PY%" (
    echo.
    echo [ERROR] Failed to create the virtual environment.
    goto :failed
)

rem 2) Install dependencies only when PySide6 is missing.
echo [2/3] Checking dependencies...
"%VENV_PY%" -c "import PySide6; print(PySide6.__version__)" >nul 2>&1
if errorlevel 1 (
    echo PySide6 is not installed in the shared runtime.
    echo Installing requirements...
    "%VENV_PY%" -m pip install --upgrade pip
    if errorlevel 1 goto :pip_failed

    "%VENV_PY%" -m pip install -r requirements.txt
    if errorlevel 1 goto :pip_failed
) else (
    rem Avoid CMD command-substitution quoting around python.exe paths.
    "%VENV_PY%" -c "import PySide6; print('PySide6 ' + PySide6.__version__ + ' found.')"
)

rem 3) Read the remembered save path again on every launch. No save copy/cache is made.
echo [3/3] Starting FH6 Assistant...
echo.
"%VENV_PY%" -B app.py
set "APP_EXIT=%ERRORLEVEL%"

if not "%APP_EXIT%"=="0" (
    echo.
    echo [ERROR] Application exited with code %APP_EXIT%.
    goto :failed
)

exit /b 0

:pip_failed
echo.
echo [ERROR] Dependency installation failed.
echo Check the messages above and your Internet connection.
goto :failed

:failed
echo.
if "%HIDDEN_MODE%"=="1" exit /b 1
pause
exit /b 1
