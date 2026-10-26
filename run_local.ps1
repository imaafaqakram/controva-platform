# One-command local start for Windows (PowerShell).
#   Needs: Docker Desktop (running) and Python 3.10+.
#   Run from the repo folder:   powershell -ExecutionPolicy Bypass -File run_local.ps1
# Then open http://localhost:8080 and log in as admin / admin12345 (first run).
# Not 'Stop': Windows PowerShell 5.1 would turn docker/pip progress messages on
# stderr into errors. Each step checks $LASTEXITCODE instead.
$ErrorActionPreference = 'Continue'
Set-Location $PSScriptRoot

function Fail($msg) { Write-Host "`nERROR: $msg" -ForegroundColor Red; exit 1 }

# Docker running?
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Fail 'Docker is not installed. Install Docker Desktop, start it, then run this again.' }
docker info *> $null
if ($LASTEXITCODE -ne 0) { Fail 'Docker is installed but not running. Open Docker Desktop, wait until it says "running", then run this again.' }

# Python 3.10+? ("python" on Windows can be the Microsoft Store stub, so check the version.)
$py = $null
foreach ($c in @('python', 'py')) {
    if (Get-Command $c -ErrorAction SilentlyContinue) {
        $v = & $c -c "import sys; print(sys.version_info >= (3, 10))" 2>$null
        if ($v -eq 'True') { $py = $c; break }
    }
}
if (-not $py) { Fail 'Python 3.10 or newer was not found. Install it from python.org (tick "Add python.exe to PATH"), then run this again.' }

# Settings file
if (-not (Test-Path .env)) { Copy-Item .env.example .env; Write-Host 'Created .env from .env.example' }
$dbPass = (Get-Content .env | Where-Object { $_ -match '^LEADGEN_DB_PASS=' }) -replace '^LEADGEN_DB_PASS=', ''
if (-not $dbPass) { Fail 'LEADGEN_DB_PASS is missing from .env' }

# Database
Write-Host 'Starting the database (Docker)...'
docker compose -f docker-compose.local.yml up -d postgres
if ($LASTEXITCODE -ne 0) { Fail 'Could not start the database container (see the Docker message above).' }
Write-Host -NoNewline 'Waiting for the database'
$ok = $false
for ($i = 0; $i -lt 60; $i++) {
    $state = docker inspect -f '{{.State.Health.Status}}' leadgen_postgres 2>$null
    if ($state -eq 'healthy') { $ok = $true; break }
    Write-Host -NoNewline '.'; Start-Sleep -Seconds 2
}
Write-Host ''
if (-not $ok) { Fail 'The database did not become ready. Run "docker logs leadgen_postgres" to see why.' }

# Python packages
Write-Host 'Installing Python packages...'
& $py -m pip install --quiet psycopg2-binary dnspython
if ($LASTEXITCODE -ne 0) { Fail 'pip install failed (see above).' }

# Start the app
$env:LEADGEN_HOME = Join-Path $PSScriptRoot 'server'
$env:DB_PASS = $dbPass
if (-not $env:ADMIN_PASSWORD) { $env:ADMIN_PASSWORD = 'admin12345' }
Write-Host "`nStarting Controva. Open http://localhost:8080  (login: admin / $($env:ADMIN_PASSWORD) on first run)" -ForegroundColor Green
Write-Host "Keep this window open. Press Ctrl+C to stop.`n"
& $py server\leads_api.py
