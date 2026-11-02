[CmdletBinding()]
param(
    [int]$Port = 8090,
    [int]$StartupTimeoutSeconds = 30
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root

$listenerIds = @(
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
)
foreach ($listenerId in $listenerIds) {
    $listener = Get-CimInstance Win32_Process -Filter "ProcessId = $listenerId"
    if (-not $listener -or $listener.CommandLine -notmatch 'app[\\/]main\.py') {
        throw "Port $Port is owned by a process that is not this app (PID $listenerId). Stop it manually and retry."
    }
    Write-Host "Stopping the CricketCanClubs app on port $Port (PID $listenerId)..."
    Stop-Process -Id $listenerId -Force
}

$stopDeadline = (Get-Date).AddSeconds(15)
do {
    $remaining = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    if (-not $remaining.Count) { break }
    Start-Sleep -Milliseconds 300
} while ((Get-Date) -lt $stopDeadline)
if (@(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue).Count) {
    throw "Port $Port is still busy after stopping the app."
}

$pythonPath = $env:CRICKET_APP_PYTHON
if (-not $pythonPath) {
    $venvPython = Join-Path $root '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $venvPython) {
        $pythonPath = $venvPython
    } else {
        $pythonCommand = Get-Command python.exe -ErrorAction Stop
        $pythonPath = $pythonCommand.Source
    }
}
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Python executable not found: $pythonPath"
}

$stdoutLog = Join-Path $env:TEMP 'CricketCanClubsApp-local.out.log'
$stderrLog = Join-Path $env:TEMP 'CricketCanClubsApp-local.err.log'
$oldPort = $env:PORT
try {
    $env:PORT = [string]$Port
    $appProcess = Start-Process -FilePath $pythonPath `
        -ArgumentList 'app\main.py' `
        -WorkingDirectory $root `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog `
        -PassThru
} finally {
    if ($null -eq $oldPort) { Remove-Item Env:PORT -ErrorAction SilentlyContinue }
    else { $env:PORT = $oldPort }
}

$deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
$healthy = $false
do {
    if ($appProcess.HasExited) { break }
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 2
        if ($health.status -eq 'ok') { $healthy = $true; break }
    } catch {
        Start-Sleep -Seconds 1
    }
} while ((Get-Date) -lt $deadline)

if (-not $healthy) {
    $details = if (Test-Path -LiteralPath $stderrLog) { Get-Content -LiteralPath $stderrLog -Tail 30 | Out-String } else { '' }
    throw "App did not become healthy on port $Port. Logs: $stdoutLog and $stderrLog`n$details"
}

Write-Host "CricketCanClubs app is healthy at http://127.0.0.1:$Port (PID $($appProcess.Id))."
Write-Host "Logs: $stdoutLog and $stderrLog"