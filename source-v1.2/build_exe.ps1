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

$metadataJson = & $python -c "import json; from fh6garage.build_metadata import build_metadata; print(json.dumps(build_metadata()))"
if ($LASTEXITCODE -ne 0) {
    throw "Unable to load build metadata."
}
$metadata = $metadataJson | ConvertFrom-Json
$standardExe = "$($metadata.standard_name).exe"

if ($Distribution -in @("Standard", "All")) {
    & $python -m PyInstaller --clean --noconfirm (Join-Path $PSScriptRoot $metadata.standard_spec)
    $standard = Join-Path $PSScriptRoot ("dist\" + $standardExe)
    if (-not (Test-Path $standard)) {
        throw "Standard build was not created: $standard"
    }
    Write-Host "Standard build: $standard"
}

if ($Distribution -in @("Portable", "All")) {
    & $python -m PyInstaller --clean --noconfirm (Join-Path $PSScriptRoot $metadata.portable_spec)
    $portable = Join-Path $PSScriptRoot ("dist\" + $metadata.portable_dir_name)
    if (-not (Test-Path (Join-Path $portable $standardExe))) {
        throw "Portable build was not created: $portable"
    }
    Write-Host "Portable build: $portable"
}
