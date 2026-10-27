#!/bin/sh
# Container start: stage the dashboard into the writable data folder (keys,
# config.json and mockups persist there), optionally load demo data, run.
set -e
mkdir -p "$LEADGEN_HOME/mockups"
cp /app/server/dashboard.html "$LEADGEN_HOME/dashboard.html"
if [ "${DEMO_DATA:-0}" = "1" ]; then
  python /app/server/demo_seed.py || echo "[demo] seeding skipped (see error above)"
fi
exec python /app/server/leads_api.py
