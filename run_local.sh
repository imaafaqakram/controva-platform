#!/usr/bin/env bash
# One-command local start for Mac / Linux. Needs only Docker Desktop (running).
#   Run from the repo folder:   bash run_local.sh
# Opens http://localhost:8080 — log in as admin / admin12345, or demo / demo12345! (sample client).
# Stop with:  docker compose down      Start over (wipes data):  docker compose down -v
set -euo pipefail
cd "$(dirname "$0")"

fail() { printf '\nERROR: %s\n' "$1" >&2; exit 1; }

command -v docker >/dev/null || fail 'Docker is not installed. Install Docker Desktop, start it, then run this again.'
docker info >/dev/null 2>&1 || fail 'Docker is installed but not running. Open Docker Desktop, wait until it says "running", then run this again.'

echo 'Building and starting Controva (first run downloads ~200 MB, takes a few minutes)...'
docker compose up -d --build || fail 'docker compose could not start the app (see above). If port 8080 is busy: APP_PORT=8090 bash run_local.sh'

PORT="${APP_PORT:-8080}"
printf 'Waiting for the app'
for _ in $(seq 1 60); do
  curl -s -m 2 "http://localhost:$PORT/health" >/dev/null && break
  printf '.'; sleep 2
done
echo
curl -s -m 2 "http://localhost:$PORT/health" >/dev/null || fail 'The app did not come up. Run "docker compose logs app" to see why.'

printf '\nControva is running at http://localhost:%s\n' "$PORT"
echo '  admin / admin12345   (you — sees every company)'
echo '  demo  / demo12345!   (sample client company)'
(command -v open >/dev/null && open "http://localhost:$PORT") || (command -v xdg-open >/dev/null && xdg-open "http://localhost:$PORT") || true
