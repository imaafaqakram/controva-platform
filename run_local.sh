#!/usr/bin/env bash
# One-command local start for Mac / Linux.
#   Needs: Docker Desktop (running) and Python 3.10+.
#   Run from the repo folder:   bash run_local.sh
# Then open http://localhost:8080 and log in as admin / admin12345 (first run).
set -euo pipefail
cd "$(dirname "$0")"

fail() { printf '\nERROR: %s\n' "$1" >&2; exit 1; }

command -v docker >/dev/null || fail 'Docker is not installed. Install Docker Desktop, start it, then run this again.'
docker info >/dev/null 2>&1 || fail 'Docker is installed but not running. Open Docker Desktop, wait until it says "running", then run this again.'

PY=''
for c in python3 python; do
  if command -v "$c" >/dev/null && [ "$("$c" -c 'import sys; print(sys.version_info >= (3, 10))' 2>/dev/null)" = True ]; then
    PY=$c; break
  fi
done
[ -n "$PY" ] || fail 'Python 3.10 or newer was not found. Install it from python.org, then run this again.'

if [ ! -f .env ]; then cp .env.example .env; echo 'Created .env from .env.example'; fi
DB_PASS_VALUE=$(grep '^LEADGEN_DB_PASS=' .env | head -1 | cut -d= -f2-)
[ -n "$DB_PASS_VALUE" ] || fail 'LEADGEN_DB_PASS is missing from .env'

echo 'Starting the database (Docker)...'
docker compose -f docker-compose.local.yml up -d postgres || fail 'Could not start the database container (see the Docker message above).'
printf 'Waiting for the database'
ok=''
for _ in $(seq 1 60); do
  if [ "$(docker inspect -f '{{.State.Health.Status}}' leadgen_postgres 2>/dev/null)" = healthy ]; then ok=1; break; fi
  printf '.'; sleep 2
done
echo
[ -n "$ok" ] || fail 'The database did not become ready. Run "docker logs leadgen_postgres" to see why.'

echo 'Installing Python packages...'
"$PY" -m pip install --quiet psycopg2-binary dnspython || fail 'pip install failed (see above).'

export LEADGEN_HOME="$PWD/server" DB_PASS="$DB_PASS_VALUE"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin12345}"
printf '\nStarting Controva. Open http://localhost:8080  (login: admin / %s on first run)\n' "$ADMIN_PASSWORD"
printf 'Keep this window open. Press Ctrl+C to stop.\n\n'
exec "$PY" server/leads_api.py
