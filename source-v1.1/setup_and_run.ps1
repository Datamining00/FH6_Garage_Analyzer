$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$runtimeRoot = Join-Path $env:LOCALAPPDATA 'FH6GarageAnalyzer'
$venvDir = Join-Path $runtimeRoot 'venv'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'
$env:PYTHONDONTWRITEBYTECODE = '1'

New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null

function New-SharedVenv {
    $candidates = @(
        @{ Cmd = 'py'; Args = @('-3.13') },
        @{ Cmd = 'py'; Args = @('-3.12') },
        @{ Cmd = 'py'; Args = @('-3') },
        @{ Cmd = 'python'; Args = @() }
    )

    foreach ($candidate in $candidates) {
        try {
            & $candidate.Cmd @($candidate.Args) --version *> $null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "Creating runtime environment at $venvDir ..."
                & $candidate.Cmd @($candidate.Args) -m venv $venvDir
                if (Test-Path $venvPython) { return }
            }
        }
        catch { }
    }

    throw 'Python 3.12 or newer was not found.'
}

if (-not (Test-Path $venvPython)) {
    New-SharedVenv
}

Write-Host 'Checking PySide6...'
& $venvPython -c 'import PySide6; print(PySide6.__version__)' *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Installing dependencies into LocalAppData runtime...'
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r requirements.txt
}

Write-Host 'Starting FH6 Assistant...'
& $venvPython -B app.py
