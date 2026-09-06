@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "ROOT=%~dp0.."
set "INSPECTOR=%ROOT%\tools\inspect_vehicle_morph.py"

if not exist "%INSPECTOR%" (
  echo ERROR: inspect_vehicle_morph.py was not found.
  echo Expected: %INSPECTOR%
  pause
  exit /b 2
)

set "ARCHIVE=%~1"
if not defined ARCHIVE (
  set "PICKFILE=%TEMP%\fh6_wheel_morph_pick_%RANDOM%_%RANDOM%.txt"
  powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -Command ^
    "Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.OpenFileDialog; $d.Filter = 'FH6 vehicle ZIP (*.zip)|*.zip|All files (*.*)|*.*'; $d.Title = 'Select FH6 vehicle ZIP'; if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { [System.IO.File]::WriteAllText($env:PICKFILE, $d.FileName) }"
  if not exist "%PICKFILE%" (
    echo No archive selected.
    exit /b 1
  )
  set /p "ARCHIVE="<"%PICKFILE%"
  del /q "%PICKFILE%" >nul 2>&1
)

if not exist "%ARCHIVE%" (
  echo ERROR: Vehicle ZIP does not exist:
  echo %ARCHIVE%
  pause
  exit /b 2
)

for %%F in ("%ARCHIVE%") do set "STEM=%%~nF"

if defined LOCALAPPDATA (
  set "OUTDIR=%LOCALAPPDATA%\FH6 Assistant\Diagnostics"
) else (
  set "OUTDIR=%TEMP%\FH6 Assistant\Diagnostics"
)
if not exist "%OUTDIR%" mkdir "%OUTDIR%" >nul 2>&1
set "OUTPUT=%OUTDIR%\%STEM%_morph_w3.json"

set "PYLAUNCH="
set "PYARGS="
where py.exe >nul 2>&1
if not errorlevel 1 (
  py.exe -3.12 -c "import sys" >nul 2>&1
  if not errorlevel 1 (
    set "PYLAUNCH=py.exe"
    set "PYARGS=-3.12"
  ) else (
    py.exe -3 -c "import sys" >nul 2>&1
    if not errorlevel 1 (
      set "PYLAUNCH=py.exe"
      set "PYARGS=-3"
    )
  )
)

if not defined PYLAUNCH (
  where python.exe >nul 2>&1
  if not errorlevel 1 set "PYLAUNCH=python.exe"
)

if not defined PYLAUNCH (
  echo ERROR: Python 3 was not found.
  echo Install Python 3.12+ or run this from the FH6 Assistant source environment.
  pause
  exit /b 2
)

echo FH6 Wheel Morph Diagnostic
echo ------------------------------------------------------------
echo Archive: %ARCHIVE%
echo Output : %OUTPUT%
echo Mode   : READ-ONLY
echo.

pushd "%ROOT%" >nul
"%PYLAUNCH%" %PYARGS% "%INSPECTOR%" "%ARCHIVE%" --output "%OUTPUT%"
set "RC=%ERRORLEVEL%"
popd >nul

if not "%RC%"=="0" (
  echo.
  echo ERROR: Diagnostic failed with exit code %RC%.
  echo The source ZIP was not modified.
  pause
  exit /b %RC%
)

echo.
echo Diagnostic completed successfully.
echo Result: %OUTPUT%
start "" explorer.exe /select,"%OUTPUT%"
pause
exit /b 0
