# Controva Platform — How to Run It

A complete guide for spinning up the Controva Intelligence Platform locally or
on a fresh VPS, with the exact commands that were verified by the test pass in
`testing/TESTING_REPORT.md`.

---

## TL;DR — fastest path

```bash
# 1. Install runtime
sudo apt-get install -y postgresql postgresql-contrib redis-server python3-pip
pip install psycopg2-binary

# 2. Boot data services
sudo pg_ctlcluster 16 main start
redis-server --daemonize yes --port 6379 --requirepass "CHANGE_ME_REDIS_PASS"

# 3. Create DB + load schema + grant perms (one-shot)
sudo -u postgres psql <<'EOF'
CREATE USER leadgen WITH PASSWORD 'CHANGE_ME_DB_PASS';
CREATE DATABASE leadgen_db OWNER leadgen;
EOF
sudo -u postgres psql -d leadgen_db -c 'CREATE EXTENSION IF NOT EXISTS "uuid-ossp"; CREATE EXTENSION IF NOT EXISTS pg_trgm;'
sudo -u postgres psql -d leadgen_db -f server/init.sql
sudo -u postgres psql -d leadgen_db -f server/migrations/001_intent.sql
sudo -u postgres psql -d leadgen_db -c '
  GRANT ALL ON ALL TABLES IN SCHEMA public TO leadgen;
  GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO leadgen;
  ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO leadgen;'

# 4. Stage app + run
sudo mkdir -p /opt/leadgen/mockups && sudo chown -R $USER /opt/leadgen
cp server/leads_api.py server/dashboard.html /opt/leadgen/
python3 /opt/leadgen/leads_api.py
```

Open `http://localhost:8080/` — login `admin` / `CHANGE_ME_BEFORE_DEPLOY`.

---

## 1. System requirements

| Resource | Minimum | Recommended |
|---|---|---|
| OS | Ubuntu 22.04 / 24.04 LTS | Ubuntu 24.04 LTS |
| RAM | 4 GB | 16 GB |
| Disk | 50 GB | 100 GB |
| CPU | 2 vCPU | 4 vCPU |
| Python | 3.10+ | 3.11+ |
| Network | Outbound HTTPS to AI provider APIs | Same |

---

## 2. Install runtime dependencies

```bash
sudo apt-get update
sudo apt-get install -y \
    postgresql postgresql-contrib \
    redis-server \
    python3 python3-pip
pip install psycopg2-binary
```

> **Note on Oxylabs:** the codebase imports `oxylabs_ai_studio` but it's not on
> PyPI under that name. The server logs `Oxylabs init failed` and falls back to
> Serper automatically. If you need Oxylabs deep-scrape, install from the
> Oxylabs partner repo or skip it.

### Optional: Crawl4AI (used for some scraping fallbacks)

If you want JS-rendered scraping, run Crawl4AI as a Docker sidecar:

```bash
docker run -d --name crawl4ai \
    -p 11235:11235 \
    -e CRAWL4AI_API_TOKEN=CHANGE_ME_CRAWL4AI_TOKEN \
    unclecode/crawl4ai:latest
```

Not required for any of the tested features.

---

## 3. Start data services

```bash
sudo pg_ctlcluster 16 main start                  # PostgreSQL on 5432
redis-server --daemonize yes --port 6379 \
    --requirepass "CHANGE_ME_REDIS_PASS"            # Redis on 6379
```

Verify:
```bash
sudo pg_lsclusters                                 # status should be 'online'
redis-cli -a CHANGE_ME_REDIS_PASS ping              # PONG
```

---

## 4. Create database, schema, permissions

```bash
sudo -u postgres psql <<'EOF'
CREATE USER leadgen WITH PASSWORD 'CHANGE_ME_DB_PASS';
CREATE DATABASE leadgen_db OWNER leadgen;
EOF

sudo -u postgres psql -d leadgen_db <<'EOF'
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;
EOF

sudo -u postgres psql -d leadgen_db -f server/init.sql
sudo -u postgres psql -d leadgen_db -f server/migrations/001_intent.sql

# IMPORTANT — without these grants, the API returns 500 'permission denied for table leads'
sudo -u postgres psql -d leadgen_db <<'EOF'
GRANT ALL ON ALL TABLES IN SCHEMA public TO leadgen;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO leadgen;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO leadgen;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO leadgen;
EOF
```

> **DB-name gotcha:** `init.sql` and most docs say `leadgen`; `leads_api.py`
> connects to `leadgen_db`. Use `leadgen_db` (matches the running code).

---

## 5. Stage the app

```bash
sudo mkdir -p /opt/leadgen/mockups
sudo chown -R $USER /opt/leadgen
cp server/leads_api.py /opt/leadgen/
cp server/dashboard.html /opt/leadgen/
```

> The API hard-codes `/opt/leadgen/` for the config file, mockup images, and the
> dashboard HTML — stick to this path.

### Configure API keys

The repo currently has API keys **hardcoded in `server/leads_api.py:28-36`** — a
security issue (see Bugs section of `testing/TESTING_REPORT.md`). Until that's
moved to a `.env`, either:

a. Use the in-code defaults (working but exposed in git), **or**
b. Save your real keys to `/opt/leadgen/config.json` (the API loads it on
   startup and overrides the hard-coded constants):

```bash
cp server/config.json.template /opt/leadgen/config.json
nano /opt/leadgen/config.json
```

The keys you can fill in:
`google_api_key`, `serper_key`, `gemini_key`, `claude_key`, `replicate_token`,
`imagine_art_key`, `oxylabs_key`, `resend_key`, `from_email`, `from_name`.

---

## 6. Start the API

```bash
cd /opt/leadgen
python3 leads_api.py
# → "LeadGen v5 - Multi-Module Intelligence Platform"
# → "Listening on :8080"
```

For production, install the systemd unit:
```bash
sudo cp server/leadgen-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now leadgen-api
```

### Verify it's up
```bash
curl -s http://127.0.0.1:8080/health | python3 -m json.tool
# expect: {"status":"ok","version":"5.0","providers":{...}}
```

---

## 7. Open the dashboard

```
http://localhost:8080/
```
**Default login:** `admin` / `CHANGE_ME_BEFORE_DEPLOY` — **change this immediately**
(see `server/leads_api.py` for where the hash is checked).

> **CDN-blocked networks:** the dashboard fetches React/Tailwind/Babel from
> `unpkg.com` and `cdn.tailwindcss.com`. If your VPS or corporate network blocks
> those, vendor them locally (used during the test pass):
>
> ```bash
> cd /opt/leadgen && mkdir vendor && cd vendor
> npm init -y
> npm i react@18.3.1 react-dom@18.3.1 @babel/standalone@7.24.4 tailwindcss@3
> ./node_modules/.bin/tailwindcss -i <(echo "@tailwind base; @tailwind components; @tailwind utilities;") -o tailwind.css --minify
> ```
> Then swap the four CDN `<script>`/`<link>` tags in `dashboard.html` for local
> `/vendor/...` paths (the API ships a `/mockups/*` static handler you can
> mirror to also serve `/vendor/*`).

---

## 8. Test that everything works

Run the verified test pass — 26 checks, costs ~$0.20–0.40:

```bash
python3 testing/run_tests.py
```

Take dashboard screenshots:
```bash
pip install playwright
python3 -m playwright install chromium
python3 testing/take_screenshots.py
# → screenshots saved to /tmp/leadgen-test/screenshots/
```

Full report of what was tested, with real Cambridge-dentist data captured:
[`testing/TESTING_REPORT.md`](./testing/TESTING_REPORT.md).

---

## 9. First real run (your own search)

In the dashboard:

1. **Search → "barber shops in Manchester UK"** → density `Fast` (cheapest)
2. **Leads** tab — confirm 30+ businesses returned, with `phone`, `website`, etc.
3. **Pipeline** tab — run **Enrich** (Serper-only), then **Score**, then **Generate email copy** (keep image OFF for now)
4. **Outreach** tab — review the Claude-written email; **Approve** or **Reject**
5. Hit **Send** only after you've set `from_email` to a verified Resend sender.

---

## 10. Common issues

| Symptom | Fix |
|---|---|
| `permission denied for table leads` | Run the `GRANT` block in step 4 |
| `psycopg2.OperationalError: database "leadgen_db" does not exist` | DB name mismatch — create `leadgen_db`, not `leadgen` |
| Dashboard shows "Loading Controva Intelligence..." forever | CDNs blocked. Vendor JS/CSS locally (step 7 note) |
| `/search` returns 400 `query required` | Use field name `query` (not `q`) |
| `/find-people` returns 400 `company_name required` | Use field name `company_name` (not `company`) |
| `Oxylabs init failed: No module named 'oxylabs_ai_studio'` | Harmless — Serper covers the path |
| `/score` returns `total: 0` | No leads in `enriched` status — run `/enrich` first |

---

## 11. Cost expectations (per typical workflow)

| Action | Estimated cost |
|---|---|
| One discovery search, `low` density | ~$0.085 (Google Places) |
| One discovery search, `standard` density | ~$0.155 |
| One discovery search, `high` density | ~$0.43 |
| Enrich one lead (Serper) | ~$0.005 |
| AI-score 10 leads (Gemini) | ~$0.005 |
| Generate email copy for 1 lead (Claude) | ~$0.01–0.03 |
| Generate mockup image (Replicate FLUX) | $0.003 |
| Send email (Resend, first 3,000/mo) | FREE |

A full *find-50-leads → enrich → score → email-copy → send* run is typically
**under $1**.

---

## 12. Security hardening (before going public)

1. **Rotate every API key in `server/leads_api.py:28-36`** — they're in git history.
2. Move keys to `/opt/leadgen/config.json` (or env vars) and `.gitignore` the file.
3. Change `admin / CHANGE_ME_BEFORE_DEPLOY` password (and swap SHA256 for bcrypt — flagged in code).
4. Put the API behind Caddy or nginx with TLS + basic auth, not raw `:8080`.
5. Configure firewall to expose only `:443` publicly.
