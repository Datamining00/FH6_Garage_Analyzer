@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "APP=%~dp0FH6 Assistant v1.4.exe"
if not exist "%APP%" set "APP=%~dp0FH6 Assistant v1.4 Portable\FH6 Assistant v1.4.exe"
if not exist "%APP%" (
  echo ERROR: FH6 Assistant v1.4.exe was not found beside this launcher.
  echo Use this launcher from the W3 build artifact root or Portable folder.
  pause
  exit /b 2
)

set "GLB=%~1"
if not defined GLB call :pick_glb
if not defined GLB exit /b 1
if not exist "%GLB%" (
  echo ERROR: GLB does not exist:
  echo %GLB%
  pause
  exit /b 2
)

set "PAINT=%~2"
if not defined PAINT call :pick_paint
if not defined PAINT exit /b 1
if not exist "%PAINT%" (
  echo ERROR: C_livery paint source does not exist:
  echo %PAINT%
  pause
  exit /b 2
)

set "VEHICLE=%~3"
if not defined VEHICLE call :pick_vehicle
if not defined VEHICLE exit /b 1
if not exist "%VEHICLE%" (
  echo ERROR: Vehicle ZIP does not exist:
  echo %VEHICLE%
  pause
  exit /b 2
)

if defined LOCALAPPDATA (
  set "OUTDIR=%LOCALAPPDATA%\FH6 Assistant\Diagnostics"
) else (
  set "OUTDIR=%TEMP%\FH6 Assistant\Diagnostics"
)
set "CACHE=%OUTDIR%\P3FCache"
if not exist "%OUTDIR%" mkdir "%OUTDIR%" >nul 2>&1
if not exist "%CACHE%" mkdir "%CACHE%" >nul 2>&1
for %%F in ("%GLB%") do set "STEM=%%~nF"
set "OUTPUT=%OUTDIR%\%STEM%_manufacturer_materialbin_p3f.json"

echo FH6 Paint P3F Manufacturer Materialbin Diagnostic
echo ------------------------------------------------------------
echo GLB     : %GLB%
echo C_livery: %PAINT%
echo Vehicle : %VEHICLE%
echo Cache   : %CACHE%
echo Output  : %OUTPUT%
echo Mode    : FH6 GAME/SAVE READ-ONLY; diagnostic derivatives only
echo.

start "" /wait "%APP%" --p3f-materialbin-diagnostic --glb "%GLB%" --paint "%PAINT%" --vehicle "%VEHICLE%" --cache "%CACHE%" --output "%OUTPUT%"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo ERROR: Paint P3F diagnostic failed with exit code %RC%.
  echo FH6 game/save inputs were not modified.
  pause
  exit /b %RC%
)

if not exist "%OUTPUT%" (
  echo.
  echo ERROR: Diagnostic process returned success but no JSON output was created.
  pause
  exit /b 3
)

echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$r = Get-Content -LiteralPath $env:OUTPUT -Raw | ConvertFrom-Json; Write-Host ('Validation : ' + $r.validation_status); Write-Host ('P3D       : ' + $r.p3d_status); Write-Host ('Candidates: ' + $r.candidate_count); Write-Host ('Resolved  : ' + $r.exact_resolved_count); Write-Host ('Blocked   : ' + $r.blocked_count); Write-Host ('Unresolved: ' + $r.unresolved_count); Write-Host ('Helper    : ' + $r.helper_revision)"
echo.
echo Result: %OUTPUT%
start "" explorer.exe /select,"%OUTPUT%"
pause
exit /b 0

:pick_glb
set "PICKFILE=%TEMP%\fh6_p3f_glb_%RANDOM%_%RANDOM%.txt"
if exist "%PICKFILE%" del /q "%PICKFILE%" >nul 2>&1
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -Command ^
  "Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.OpenFileDialog; $d.Filter = 'FH6 converted GLB (*.glb)|*.glb|All files (*.*)|*.*'; $d.Title = 'Select current FH6 converted GLB'; if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { [System.IO.File]::WriteAllText($env:PICKFILE, $d.FileName) }"
if not exist "%PICKFILE%" exit /b 1
set /p "GLB="<"%PICKFILE%"
del /q "%PICKFILE%" >nul 2>&1
exit /b 0

:pick_paint
set "PICKFILE=%TEMP%\fh6_p3f_paint_%RANDOM%_%RANDOM%.txt"
if exist "%PICKFILE%" del /q "%PICKFILE%" >nul 2>&1
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -Command ^
  "Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.OpenFileDialog; $d.Filter = 'FH6 C_livery|C_livery|All files (*.*)|*.*'; $d.Title = 'Select matching C_livery paint source'; if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { [System.IO.File]::WriteAllText($env:PICKFILE, $d.FileName) }"
if not exist "%PICKFILE%" exit /b 1
set /p "PAINT="<"%PICKFILE%"
del /q "%PICKFILE%" >nul 2>&1
exit /b 0

:pick_vehicle
set "PICKFILE=%TEMP%\fh6_p3f_vehicle_%RANDOM%_%RANDOM%.txt"
if exist "%PICKFILE%" del /q "%PICKFILE%" >nul 2>&1
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -Command ^
  "Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.OpenFileDialog; $d.Filter = 'FH6 vehicle archive (*.zip)|*.zip|All files (*.*)|*.*'; $d.Title = 'Select matching FH6 vehicle ZIP'; if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { [System.IO.File]::WriteAllText($env:PICKFILE, $d.FileName) }"
if not exist "%PICKFILE%" exit /b 1
set /p "VEHICLE="<"%PICKFILE%"
del /q "%PICKFILE%" >nul 2>&1
exit /b 0
