@echo off
setlocal
cd /d "%~dp0"

set "PYEXE="
set "PYARG="
where py >nul 2>nul
if not errorlevel 1 (
    set "PYEXE=py"
    set "PYARG=-3"
) else (
    where python >nul 2>nul
    if not errorlevel 1 set "PYEXE=python"
)

if not defined PYEXE (
    echo Python 3 was not found.
    echo Install Python 3.12 or newer and run this launcher again.
    pause
    exit /b 1
)

set "SCRIPT=%~dp0run_wheel_morph_bake_diagnostic.py"
set "BASIS=ForzaLiveryStudio wheel_sizes.json game-DB-derived candidate; local FH6 RealDB not yet independently cross-verified"

if "%~1"=="" (
    "%PYEXE%" %PYARG% "%SCRIPT%" ^
      --front-width-mm 245 ^
      --front-wheel-diameter-in 19 ^
      --rear-width-mm 345 ^
      --rear-wheel-diameter-in 19 ^
      --spec-basis "%BASIS%"
) else (
    "%PYEXE%" %PYARG% "%SCRIPT%" "%~1" ^
      --front-width-mm 245 ^
      --front-wheel-diameter-in 19 ^
      --rear-width-mm 345 ^
      --rear-wheel-diameter-in 19 ^
      --spec-basis "%BASIS%"
)

set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
    echo Diagnostic completed. Return wheel_morph_four_way_report.json and the combined GLB for review.
) else (
    echo Diagnostic failed with exit code %RC%.
)
pause
exit /b %RC%
