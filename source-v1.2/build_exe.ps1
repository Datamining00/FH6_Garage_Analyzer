param(
    [ValidateSet("Standard", "Portable", "All")]
    [string]$Distribution = "All"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$venv = Join-Path $PSScriptRoot ".build-venv"
if (-not (Test-Path $venv)) {
    py -3 -m venv $venv
}

$python = Join-Path $venv "Scripts\python.exe"
& $python -m pip install --upgrade pip
& $python -m pip install -r .\requirements.txt pyinstaller

if ($Distribution -in @("Standard", "All")) {
    & $python -m PyInstaller --clean --noconfirm .\FH6_Assistant_v1.3.3.spec
    $standard = Join-Path $PSScriptRoot "dist\FH6 Assistant v1.3.3 Beta.exe"
    if (-not (Test-Path $standard)) {
        throw "Standard build was not created: $standard"
    }
    Write-Host "Standard build: $standard"
}

if ($Distribution -in @("Portable", "All")) {
    & $python -m PyInstaller --clean --noconfirm .\FH6_Assistant_v1.3.3_portable.spec
    $portable = Join-Path $PSScriptRoot "dist\FH6 Assistant v1.3.3 Beta Portable"
    if (-not (Test-Path (Join-Path $portable "FH6 Assistant v1.3.3 Beta.exe"))) {
        throw "Portable build was not created: $portable"
    }
    Write-Host "Portable build: $portable"
}
