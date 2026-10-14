@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "APP=%~dp0FH6 Material Shader Parameter Diagnostic.exe"
if not exist "%APP%" (
  echo ERROR: FH6 Material Shader Parameter Diagnostic.exe was not found beside this launcher.
  echo Use this launcher from the Material Shader Parameter Diagnostic artifact root.
  pause
  exit /b 2
)

if defined LOCALAPPDATA (
  set "OUTDIR=%LOCALAPPDATA%\FH6 Assistant\Diagnostics"
) else (
  set "OUTDIR=%TEMP%\FH6 Assistant\Diagnostics"
)
if not exist "%OUTDIR%" mkdir "%OUTDIR%" >nul 2>&1

"%APP%" --self-check > "%OUTDIR%\material_shader_parameter_self_check.json"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo ERROR: Material/shader parameter diagnostic self-check failed with exit code %RC%.
  echo Self-check: %OUTDIR%\material_shader_parameter_self_check.json
  pause
  exit /b %RC%
)

set "P3F=%~1"
if not defined P3F call :pick_p3f
if not defined P3F exit /b 1
if not exist "%P3F%" (
  echo ERROR: P3F JSON does not exist:
  echo %P3F%
  pause
  exit /b 2
)

for %%F in ("%P3F%") do set "STEM=%%~nF"
set "OUTPUT=%OUTDIR%\%STEM%_material_shader_parameters.json"

echo FH6 Material + Shader Parameter Diagnostic
echo ------------------------------------------------------------
echo P3F   : %P3F%
echo Output: %OUTPUT%
echo Input : exact cached materialbin/shaderbin paths from P3F JSON
echo Rule  : NameHash + Type; material override wins over shader default
echo Mode  : FH6 GAME/SAVE READ-ONLY; rendering disabled
echo.

"%APP%" --p3f "%P3F%" --output "%OUTPUT%"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo ERROR: Material/shader parameter diagnostic failed with exit code %RC%.
  if exist "%OUTPUT%" echo Diagnostic evidence: %OUTPUT%
  echo If a cached materialbin/shaderbin path is missing, rerun the current P3F diagnostic first.
  echo FH6 game/save inputs were not modified.
  pause
  exit /b %RC%
)

if not exist "%OUTPUT%" (
  echo ERROR: Diagnostic returned success but no JSON output was created.
  pause
  exit /b 3
)

echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$r = Get-Content -LiteralPath $env:OUTPUT -Raw | ConvertFrom-Json; $c = $r.parameter_composition; Write-Host ('Status    : ' + $r.status); Write-Host ('P3F      : ' + $r.p3f_validation_status); Write-Host ('Targets  : ' + $c.target_count); Write-Host ('Composed : ' + $c.composed_count); Write-Host ('Failed   : ' + $c.failed_count); Write-Host ('Helper   : ' + $r.helper_revision)"
echo.
echo Result: %OUTPUT%
start "" explorer.exe /select,"%OUTPUT%"
pause
exit /b 0

:pick_p3f
set "PICKFILE=%TEMP%\fh6_material_parameters_%RANDOM%_%RANDOM%.txt"
if exist "%PICKFILE%" del /q "%PICKFILE%" >nul 2>&1
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -Command ^
  "Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.OpenFileDialog; $d.Filter = 'FH6 P3F diagnostic JSON (*.json)|*.json|All files (*.*)|*.*'; $d.Title = 'Select the current FH6 manufacturer materialbin P3F JSON'; if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { [System.IO.File]::WriteAllText($env:PICKFILE, $d.FileName) }"
if not exist "%PICKFILE%" exit /b 1
set /p "P3F="<"%PICKFILE%"
del /q "%PICKFILE%" >nul 2>&1
exit /b 0
