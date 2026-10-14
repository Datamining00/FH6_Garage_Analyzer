@echo off
setlocal
cd /d "%~dp0\.."

set "PYTHON_EXE="
where py >nul 2>nul && set "PYTHON_EXE=py -3"
if not defined PYTHON_EXE (
  where python >nul 2>nul && set "PYTHON_EXE=python"
)
if not defined PYTHON_EXE (
  echo ERROR: Python 3 was not found in PATH.
  pause
  exit /b 1
)

set "DBFILE=%~1"
if not defined DBFILE (
  for /f "usebackq delims=" %%I in (`powershell -NoProfile -STA -Command "Add-Type -AssemblyName System.Windows.Forms; $d=New-Object System.Windows.Forms.OpenFileDialog; $d.Title='Select extracted/readable FH6 SQLite database'; $d.Filter='SQLite database (*.sqlite;*.db)|*.sqlite;*.db|All files (*.*)|*.*'; if($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK){$d.FileName}"`) do set "DBFILE=%%I"
)
if not defined DBFILE (
  echo No database selected.
  exit /b 1
)
if not exist "%DBFILE%" (
  echo ERROR: Database does not exist: %DBFILE%
  pause
  exit /b 1
)

set "OUTDIR=%LOCALAPPDATA%\FH6 Assistant\Diagnostics"
if not exist "%OUTDIR%" mkdir "%OUTDIR%"
set "OUTFILE=%OUTDIR%\FER_FXX_05_wheelspec_realdb.json"

echo FH6 WheelSpec RealDB Diagnostic
echo ------------------------------------------------------------
echo Database: %DBFILE%
echo Output  : %OUTFILE%
echo Car ID  : 1006
echo Mode    : READ-ONLY

echo.
%PYTHON_EXE% tools\validate_wheel_spec_real_db.py --db "%DBFILE%" --output "%OUTFILE%" --car-id 1006
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo ERROR: Diagnostic failed with exit code %RC%.
  echo The selected database was opened read-only and was not intentionally modified.
  pause
  exit /b %RC%
)

echo.
echo SUCCESS: %OUTFILE%
explorer /select,"%OUTFILE%"
pause
exit /b 0
