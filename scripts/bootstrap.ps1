param(
    [switch]$SetupOnly,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$RefreshArgs
)

$ErrorActionPreference = 'Stop'
$BootstrapVersion = '0.9.5'
$PythonVersion = '3.13.9'

function Get-PlatformAsset([string]$Architecture) {
    switch ($Architecture.ToUpperInvariant()) {
        'AMD64' { return @('uv-x86_64-pc-windows-msvc.zip', '515dc53d7553f1357d0abc1f70acd921fbb9e30230b1d9a08737236daa6ee920') }
        'ARM64' { return @('uv-aarch64-pc-windows-msvc.zip', '4c615aa19e37b2ec7da3370a25a562bb0061ab005081e4539702c059715dc2b0') }
        default { throw "Unsupported Windows architecture: $Architecture. Use 64-bit Windows (x64 or ARM64)." }
    }
}

function Assert-FileHash([string]$Path, [string]$Expected) {
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    if ($actual -ne $Expected) { throw "Download checksum failed: $Path. Delete this archive and retry; no downloaded program was executed." }
}

function Get-EnvironmentKey([string]$Root, [string]$Machine, [string]$Architecture) {
    $bytes = [Text.Encoding]::UTF8.GetBytes("$Root|$Machine|$Architecture|$PythonVersion")
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($hasher.ComputeHash($bytes))).Replace('-', '').Substring(0, 16).ToLowerInvariant() }
    finally { $hasher.Dispose() }
}

function Invoke-Checked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE): $Program $($Arguments -join ' ')" }
}

function Invoke-QuantBootstrap {
    $root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
    Set-Location -LiteralPath $root
    $logDir = Join-Path $root 'outputs\launcher_logs'
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    $logPath = Join-Path $logDir ("launch-{0}-{1}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'), $PID)
    $transcriptStarted = $false
    try {
        Start-Transcript -LiteralPath $logPath -Force | Out-Null
        $transcriptStarted = $true
        Write-Host 'Quant Research Lab v0.11 - prepare environment and refresh reports'
        Write-Host "Project: $root"
        Write-Host "Log: $logPath"
        $arch = $env:PROCESSOR_ARCHITEW6432
        if (-not $arch) { $arch = $env:PROCESSOR_ARCHITECTURE }
        $asset = Get-PlatformAsset $arch
        $bootstrapDir = Join-Path $root ".cache\bootstrap\uv-$BootstrapVersion-$arch"
        New-Item -ItemType Directory -Path $bootstrapDir -Force | Out-Null
        $archive = Join-Path $bootstrapDir $asset[0]
        $uv = Join-Path $bootstrapDir 'uv.exe'
        if (-not (Test-Path -LiteralPath $archive)) {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            $download = "$archive.partial"
            Write-Host 'Downloading the pinned uv runtime from the official Astral release...'
            Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/astral-sh/uv/releases/download/$BootstrapVersion/$($asset[0])" -OutFile $download -TimeoutSec 180
            Assert-FileHash $download $asset[1]
            Move-Item -LiteralPath $download -Destination $archive -Force
        }
        Assert-FileHash $archive $asset[1]
        # Re-extract a verified archive so a copied executable is never trusted alone.
        Expand-Archive -LiteralPath $archive -DestinationPath $bootstrapDir -Force
        if (-not (Test-Path -LiteralPath $uv)) { throw 'The verified uv archive does not contain uv.exe.' }
        $machine = $env:COMPUTERNAME
        try {
            $machineGuid = (Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Cryptography' -Name MachineGuid).MachineGuid
            $machine = "$machine|$machineGuid"
        } catch {
            # Some managed devices deny registry reads; the host name is the fallback.
        }
        $key = Get-EnvironmentKey $root $machine $arch
        $runtimeDir = Join-Path $root ".cache\runtime\$key"
        $env:UV_PYTHON_INSTALL_DIR = Join-Path $runtimeDir 'python'
        $env:UV_CACHE_DIR = Join-Path $root '.cache\uv'
        $env:UV_PYTHON_PREFERENCE = 'only-managed'
        $env:UV_NO_PROGRESS = '1'
        # UTF-8 console output without changing Windows locale path handling.
        # Python UTF-8 mode makes libcurl reject non-ASCII CA-file paths (error 77).
        $env:PYTHONUTF8 = '0'
        $env:PYTHONIOENCODING = 'utf-8'
        $venv = Join-Path $runtimeDir 'venv'
        $python = Join-Path $venv 'Scripts\python.exe'
        Write-Host "Preparing Python $PythonVersion in the project cache (no administrator access)..."
        Invoke-Checked $uv @('python', 'install', $PythonVersion, '--no-bin')
        if (-not (Test-Path -LiteralPath $python)) {
            Invoke-Checked $uv @('venv', '--python', $PythonVersion, $venv)
        }
        Invoke-Checked $python @('-c', 'import sys; assert sys.version_info[:3] == (3, 13, 9), sys.version')
        Write-Host 'Installing or checking project dependencies...'
        Invoke-Checked $uv @('--quiet', '--quiet', 'pip', 'install', '--python', $python, '--editable', $root)
        if ($SetupOnly) {
            Write-Host "Ready. Project Python: $python"
            Write-Host 'Double-click START_V011.cmd to update all reports.'
        } else {
            Write-Host 'Downloading current data and calculating reports using the current date...'
            Invoke-Checked $python (@('-m', 'quant_research', 'refresh', '--open') + $RefreshArgs)
            Write-Host 'Refresh completed successfully.'
        }
        return 0
    } catch {
        Write-Host "FAILED: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host 'Check internet access to github.com and pypi.org, available disk space, and the log below.'
        Write-Host "Log: $logPath"
        return 1
    } finally {
        if ($transcriptStarted) { Stop-Transcript | Out-Null }
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    $result = Invoke-QuantBootstrap
    exit $result
}
