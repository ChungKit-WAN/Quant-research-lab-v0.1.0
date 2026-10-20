$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    $launcherCommand = Get-Command py -ErrorAction SilentlyContinue
    $knownPython = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'
    if ($pythonCommand) {
        & $pythonCommand.Source -m venv .venv
    } elseif (Test-Path -LiteralPath $knownPython) {
        & $knownPython -m venv .venv
    } elseif ($launcherCommand) {
        & $launcherCommand.Source -3 -m venv .venv
    } else {
        throw 'Python was not found. Install Python 3.11 or newer, then run setup.ps1 again.'
    }
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the project Python environment.' }
}
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check the error above.' }
Write-Host 'Ready. Run: .\.venv\Scripts\python.exe main.py'
