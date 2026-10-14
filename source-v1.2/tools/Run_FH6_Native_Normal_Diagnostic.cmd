@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "ROOT=%~dp0.."
set "ANALYZER=%ROOT%\tools\analyze_native_normal_texture.py"

if not exist "%ANALYZER%" (
  echo ERROR: analyze_native_normal_texture.py was not found.
  echo Expected: %ANALYZER%
  pause
  exit /b 2
)

set "GLB=%~1"
if defined GLB goto glb_selected
call :pick_glb
if errorlevel 1 (
  echo No GLB selected.
  exit /b 1
)

:glb_selected
if not exist "%GLB%" (
  echo ERROR: GLB does not exist:
  echo %GLB%
  pause
  exit /b 2
)

if not exist "%GLB%.native_textures.json" (
  echo ERROR: Native texture manifest was not found.
  echo Expected: %GLB%.native_textures.json
  echo Use a current W3 native-material conversion output.
  pause
  exit /b 2
)

for %%F in ("%GLB%") do set "STEM=%%~nF"

if defined LOCALAPPDATA (
  set "OUTDIR=%LOCALAPPDATA%\FH6 Assistant\Diagnostics"
) else (
  set "OUTDIR=%TEMP%\FH6 Assistant\Diagnostics"
)
if not exist "%OUTDIR%" mkdir "%OUTDIR%" >nul 2>&1
set "OUTPUT=%OUTDIR%\%STEM%_native_normal_bc5.json"

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

echo FH6 Native Normal Texture Diagnostic
echo ------------------------------------------------------------
echo GLB    : %GLB%
echo Output : %OUTPUT%
echo Mode   : READ-ONLY / R-X G-Y +Z HYPOTHESIS ONLY
echo.

pushd "%ROOT%" >nul
"%PYLAUNCH%" %PYARGS% "%ANALYZER%" "%GLB%" --output "%OUTPUT%"
set "RC=%ERRORLEVEL%"
popd >nul

if not "%RC%"=="0" (
  echo.
  echo ERROR: Native normal diagnostic failed with exit code %RC%.
  echo The source GLB, DDS derivatives, and FH6 game data were not modified.
  pause
  exit /b %RC%
)

echo.
echo Diagnostic completed successfully.
echo Y orientation remains unproven until geometry or authoritative shader evidence is checked.
echo Result: %OUTPUT%
start "" explorer.exe /select,"%OUTPUT%"
pause
exit /b 0

:pick_glb
set "PICKFILE=%TEMP%\fh6_native_normal_pick_%RANDOM%_%RANDOM%.txt"
if exist "%PICKFILE%" del /q "%PICKFILE%" >nul 2>&1
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -Command ^
  "Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.OpenFileDialog; $d.Filter = 'FH6 converted GLB (*.glb)|*.glb|All files (*.*)|*.*'; $d.Title = 'Select current FH6 converted GLB'; if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { [System.IO.File]::WriteAllText($env:PICKFILE, $d.FileName) }"
if not exist "%PICKFILE%" exit /b 1
set /p "GLB="<"%PICKFILE%"
del /q "%PICKFILE%" >nul 2>&1
if not defined GLB exit /b 1
exit /b 0
