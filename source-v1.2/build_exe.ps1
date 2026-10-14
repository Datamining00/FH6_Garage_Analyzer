$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    py -3.12 -m venv (Join-Path $repoRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed.' }
}
& $pythonPath -m pip install -r (Join-Path $repoRoot 'verified-build-requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $pythonPath (Join-Path $repoRoot 'tools\build.py') --distribution all
if ($LASTEXITCODE -ne 0) { throw 'Build failed; inspect artifacts/validation logs.' }
