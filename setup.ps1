$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'scripts\bootstrap.ps1') -SetupOnly
exit $LASTEXITCODE
