# Launch the workspace virtual environment; setup is explicit and never changes global Python.
$projectDir = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectDir '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Create .venv and install the project first. See docs/SETUP.md.'
}
Set-Location -LiteralPath $projectDir
& $pythonPath -m maya
exit $LASTEXITCODE
