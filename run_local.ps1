# One-command local start for Windows (PowerShell). Needs only Docker Desktop (running).
#   Run from the repo folder:   powershell -ExecutionPolicy Bypass -File run_local.ps1
# Opens http://localhost:8080 - log in as admin / admin12345, or demo / demo12345! (sample client).
# Stop with:  docker compose down      Start over (wipes data):  docker compose down -v
# Not 'Stop': Windows PowerShell 5.1 would turn docker's progress messages on
# stderr into errors. Each step checks $LASTEXITCODE instead.
$ErrorActionPreference = 'Continue'
Set-Location $PSScriptRoot

function Fail($msg) { Write-Host "`nERROR: $msg" -ForegroundColor Red; exit 1 }

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Fail 'Docker is not installed. Install Docker Desktop, start it, then run this again.' }
docker info *> $null
if ($LASTEXITCODE -ne 0) { Fail 'Docker is installed but not running. Open Docker Desktop, wait until it says "running", then run this again.' }

Write-Host 'Building and starting Controva (first run downloads ~200 MB, takes a few minutes)...'
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { Fail 'docker compose could not start the app (see the message above). If port 8080 is busy, run:  $env:APP_PORT=8090; .\run_local.ps1' }

$port = if ($env:APP_PORT) { $env:APP_PORT } else { '8080' }
Write-Host -NoNewline 'Waiting for the app'
$ok = $false
for ($i = 0; $i -lt 60; $i++) {
    try { Invoke-WebRequest -UseBasicParsing "http://localhost:$port/health" -TimeoutSec 2 | Out-Null; $ok = $true; break } catch { }
    Write-Host -NoNewline '.'; Start-Sleep -Seconds 2
}
Write-Host ''
if (-not $ok) { Fail 'The app did not come up. Run "docker compose logs app" to see why.' }

Write-Host "`nControva is running at http://localhost:$port" -ForegroundColor Green
Write-Host '  admin / admin12345   (you - sees every company)'
Write-Host '  demo  / demo12345!   (sample client company)'
Start-Process "http://localhost:$port"
