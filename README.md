# Controva Intelligence Platform

> AI-powered B2B lead generation platform — find businesses, verify their digital presence, enrich contacts, and send personalized outreach. All from one self-hosted dashboard.

---

## Table of Contents

1. [What It Does](#what-it-does)
2. [Quick Start](#quick-start)
3. [How a Lead Moves Through the System](#how-a-lead-moves-through-the-system)
4. [Dashboard Pages](#dashboard-pages)
5. [Lead Discovery](#lead-discovery)
6. [Website Verification](#website-verification)
7. [Enrichment Strategies](#enrichment-strategies)
8. [Deployment & CI/CD](#deployment--cicd)
9. [Configuration & API Keys](#configuration--api-keys)
10. [Architecture](#architecture)
11. [Database Schema](#database-schema)
12. [Troubleshooting](#troubleshooting)
13. [Security Checklist](#security-checklist)
14. [Changelog](#changelog)

---

## What It Does

Controva is a full B2B lead generation pipeline, self-hosted on your own VPS:

| Step | What happens |
|---|---|
| **Search** | Type "pest control companies in New Jersey" — AI parses it, searches 4 sources simultaneously |
| **Discover** | Finds businesses via Google Places, OpenStreetMap, and HERE Maps |
| **Verify** | Checks whether each business actually has a live website |
| **Filter** | Show only "hot" leads (confirmed no website) — your best pitch targets |
| **Enrich** | Finds owner email via Serper / Oxylabs / Crawl4AI |
| **Score** | Gemini AI rates each lead 1–10 with reasoning |
| **Write** | Claude writes a personalized outreach email per lead |
| **Send** | Review, approve, send via Resend.com |
| **Track** | Dashboard charts sent / opened / replied |

---

## Quick Start

### Requirements
- Ubuntu 22.04 / 24.04 / 26.04 VPS
- Minimum 4 GB RAM, 50 GB disk (16 GB RAM recommended)
- Root SSH access

### Install in 3 commands

```bash
scp -r controva-platform root@YOUR_SERVER_IP:/root/
ssh root@YOUR_SERVER_IP
cd /root/controva-platform/server && chmod +x setup.sh && sudo ./setup.sh
```

### Add your API keys

```bash
nano /opt/leadgen/config.json
```

Minimum keys needed to start:

```json
{
  "google_api_key": "AIzaSy_YOUR_GOOGLE_KEY",
  "serper_key":     "YOUR_SERPER_KEY",
  "gemini_key":     "AIzaSy_YOUR_GEMINI_KEY"
}
```

Full key list → see [Configuration & API Keys](#configuration--api-keys).

```bash
systemctl restart leadgen-api
```

Open `http://YOUR_SERVER_IP:8080/`  
Login: `admin` / `ChangeMe_2026!` ← **change this immediately**

---

## How a Lead Moves Through the System

```
1.  SEARCH      — "pest control in New Jersey USA"
                  AI parses → niche: pest control, city: Newark, country: US

2.  DISCOVER    — Google Places (New API + Classic fallback) + OSM + HERE Maps
                  Searches in expanding radius tiles, deduplicates across sources
                  Saved to DB as status: "discovered"

3.  VERIFY      — Click "Verify Websites" on Leads page
                  HTTP ping existing URLs; Serper search for leads without one
                  Adds NO SITE / ✓ badge to each lead

4.  FILTER      — "✓ No Website (verified)" tab → confirmed hot leads only

5.  ENRICH      — Pipeline → Enrich All
                  Crawl4AI scrapes; Serper/Oxylabs finds owner email + LinkedIn
                  Status → "enriched"

6.  SCORE       — Pipeline → AI Score
                  Gemini 1–10 rating with reason
                  Status → "ready"

7.  WRITE       — Pipeline → Generate Copy
                  Claude writes personalized subject + body
                  Optional: Replicate/imagine.art generates website mockup image

8.  APPROVE     — Outreach page: review → Approve / Reject / Edit / Regenerate

9.  SEND        — Sends via Resend.com
                  Status → "sent"

10. TRACK       — Dashboard: open rates, reply rates, conversion
```

---

## Dashboard Pages

| Page | What it does |
|---|---|
| **Dashboard** | Overview — total leads, pipeline stage counts, recent leads, reply rates |
| **Search** | Natural-language search with live progress, coverage density, website filter |
| **Leads** | Full table with sort / filter / multi-select / CSV download / Verify Websites |
| **Pipeline** | Enrich → Score → Generate; choose enrichment strategy per run |
| **Outreach** | Review email + mockup before sending; approve/reject/regenerate |
| **Analytics** | Charts: leads per day, status breakdown, niche & city breakdown, score distribution |
| **SEO** | Keyword research, SERP analysis, Google Trends |
| **Competitors** | Tech stack, social profiles, backlinks, Wayback snapshots |
| **People** | Decision-maker finder (free Apollo.io alternative) |
| **Social** | Social media scout across Instagram, TikTok, YouTube |
| **E-commerce** | Amazon/eBay product/niche research |
| **Settings** | API keys, enrichment strategy, image provider, automation toggles |

---

## Lead Discovery

### How search works

1. You type a query: `"roofing contractors in Texas"`
2. The AI parser (Gemini) extracts the niche and location. If Gemini fails, a regex fallback runs — it understands **any** business type and all 50 US states.
3. If you typed a **US state** ("Texas", "New Jersey", "Florida"), it automatically uses the state's largest city as the search center.
4. The geocoder converts the city to lat/lng coordinates.
5. The discovery engine searches in a grid of tiles at increasing radius each round.

### Discovery sources (all run in parallel)

| Source | API | Cost | Notes |
|---|---|---|---|
| Google Places (New) | `places.googleapis.com/v1/places:searchText` | Paid | Primary; 60 results per query |
| Google Places (Classic) | `maps.googleapis.com/maps/api/place/textsearch` | Paid | Auto-fallback if New API fails |
| OpenStreetMap Overpass | `overpass-api.de` | Free | Always runs alongside Google |
| HERE Maps Discover | `discover.search.hereapi.com/v1/discover` | Free 250k/mo | Runs when `HERE_API_KEY` is set |

Cross-source deduplication uses: phone number (last 10 digits) + domain + Google place ID.

### Expanding rounds

Each niche+city combination tracks a **round counter**. Every "Find More Leads" click advances to the next round — wider radius, more synonyms, more sources. You will never accidentally re-import businesses you already have.

### Coverage density

| Density | Tiles | Best for |
|---|---|---|
| Fast | 5 | Quick test, small city |
| Standard | 9 | Most searches |
| Thorough | 25 | Large metro, deep coverage |

### Website filter (at search time)

| Filter | What enters the DB |
|---|---|
| No Website | Only businesses without a listed website |
| All | All businesses (default — recommended) |
| Has Website | Only businesses with a listed website |

> **Tip:** Use "All" when searching — then use the Verify Websites feature afterwards to get confirmed data. "No Website" at search time uses the Places API field which is often wrong.

---

## Website Verification

After leads are imported, you can verify whether each business actually has a live website.

### How it works

For leads **with** a stored URL → HTTP HEAD then GET to check the site responds (< 400 status).

For leads **without** a stored URL → Serper searches `"[business name]" [city] official website` and picks the first link that isn't a social/directory site (Facebook, Instagram, Yelp, TripAdvisor, LinkedIn, Google Maps, Apple Maps, TripAdvisor, Foursquare, BBB, Trustpilot, YellowPages).

Results written back to DB:
- `website_verified = TRUE`
- `has_website = TRUE / FALSE`
- `website = <url>` (if found)

### Status badges in the Leads table

| Badge | Meaning |
|---|---|
| `NO SITE` (red) | Verified — no website found → **hot lead** |
| `✓` (green) | Verified — has a live website |
| `?` (gray) | Not yet verified |
| `🌐` (green) | Has a website URL (may not be verified yet) |

### Filters

- **Hot (no website)** — leads where `has_website = FALSE` (from discovery, unverified)
- **✓ No Website (verified)** — leads where `website_verified = TRUE` AND `has_website = FALSE` — your most reliable hot leads

### Running verification

1. Go to **Leads** page
2. To verify all unverified leads: click **Verify Websites**
3. To verify specific leads: select them (checkboxes) → click **Verify Selected**
4. Watch progress in the amber panel; click **Stop** to cancel

Processes up to 500 leads per run. Re-run anytime.

---

## Enrichment Strategies

Set your strategy in **Settings → Enrichment Strategy** or select per-run on the **Pipeline** page.

| Strategy | What it does | Cost |
|---|---|---|
| **Serper Only** | Web search for owner email/LinkedIn. Fast. | Serper credits only |
| **Oxylabs Only** | Deep scrape via Oxylabs AI Studio. Most thorough. | Oxylabs credits only |
| **Smart: Serper → Oxylabs** | Serper first; Oxylabs fills gaps. Best results. | Both (recommended) |
| **100% Free** | Serper + email permutator (first.last@domain). No extra cost. | Serper credits only |

The strategy saved in Settings is the default for all automatic enrichment. You can override it per run on the Pipeline page.

---

## Deployment & CI/CD

### Auto-deploy (GitHub Actions)

The repository includes `.github/workflows/deploy.yml`. Every push to `main` that changes `server/leads_api.py` or `server/dashboard.html` automatically:

1. SSHes into your server
2. Copies the changed files to `/opt/leadgen/`
3. Restarts `leadgen-api` service (if `leads_api.py` changed)

Required GitHub repository secrets:

| Secret | Value |
|---|---|
| `SERVER_HOST` | Your server IP (e.g. `2.25.152.153`) |
| `SERVER_USER` | `root` |
| `SERVER_PASS` | Your server SSH password |

### Manual deploy

```bash
# From your local machine
python deploy.py ui      # Update dashboard only (instant, no restart)
python deploy.py api     # Update backend + restart service
python deploy.py         # Update both
python deploy.py status  # Check server health
python deploy.py logs    # Tail live logs
python deploy.py pull    # Download live files from server to local
```

### Manual file copy

```bash
scp server/leads_api.py root@YOUR_IP:/opt/leadgen/
scp server/dashboard.html root@YOUR_IP:/opt/leadgen/
ssh root@YOUR_IP "systemctl restart leadgen-api"
```

---

## Configuration & API Keys

All keys live in `/opt/leadgen/config.json` on the server (persisted across restarts). Update them from the **Settings** page in the dashboard, or edit the file directly.

### Required keys

| Key | Service | Get it at | Free tier |
|---|---|---|---|
| `google_api_key` | Google Places + Geocoding | console.cloud.google.com | $300 credits |
| `serper_key` | Serper.dev web search | serper.dev | 2,500 free searches |
| `gemini_key` | Google Gemini AI | aistudio.google.com | Generous free tier |

### Recommended keys

| Key | Service | Get it at | Free tier |
|---|---|---|---|
| `claude_key` | Anthropic Claude | console.anthropic.com | Pay-as-you-go |
| `resend_key` | Resend email | resend.com | 3,000 emails/month |
| `from_email` | Your sender address | — | — |
| `from_name` | Sender name | — | — |

### Optional keys

| Key | Service | Get it at | Free tier |
|---|---|---|---|
| `here_api_key` | HERE Maps discovery | developer.here.com | 250k transactions/month |
| `oxylabs_key` | Oxylabs AI Studio | aistudio.oxylabs.io | Pay per scrape |
| `replicate_token` | Replicate FLUX images | replicate.com | Pay per image |
| `imagine_art_key` | imagine.art images | imagine.art/dev | Pay per image |

### Enrichment strategy (in Settings UI)

```
enrichment_strategy: serper_only | oxylabs_only | serper_then_oxylabs | free_only
```

### Automation toggles (in Settings UI)

```
auto_score      — run Gemini scoring automatically after discovery (default: ON)
auto_email_copy — run Claude email writing automatically (default: OFF — saves credits)
auto_image      — generate mockup images automatically (default: OFF)
```

---

## Architecture

```
Browser
   │
   ▼
dashboard.html  (React + Tailwind, single file, ~135 KB)
   │
   │ REST/JSON over HTTP port 8080
   ▼
leads_api.py  (Python stdlib only, threaded HTTP server)
   │
   ├── PostgreSQL 16  ── leads, contacts, assets, outreach_log, discovery_state
   ├── Redis 7        ── response cache
   ├── Crawl4AI       ── async web scraper for email extraction
   │
   └── External APIs
         ├── Google Places (New)      — primary business discovery
         ├── Google Places (Classic)  — auto-fallback
         ├── OpenStreetMap Overpass   — free secondary source
         ├── HERE Maps Discover       — free third source (optional)
         ├── Google Geocoding         — city → lat/lng
         ├── Gemini AI                — query parsing, lead scoring
         ├── Claude                   — email copy generation
         ├── Serper.dev               — email/LinkedIn enrichment
         ├── Oxylabs AI Studio        — deep enrichment fallback
         ├── Replicate / imagine.art  — mockup image generation
         └── Resend.com               — outreach email delivery
```

### File structure

```
controva-platform/
├── README.md                    ← You are here
├── 1_INSTALLATION_GUIDE.md      ← Full VPS setup walkthrough
├── 4_API_REFERENCE.md           ← All 35+ endpoint docs
├── PLATFORM_OVERVIEW.md         ← Architecture deep-dive
├── HOW_TO_RUN.md                ← How to start/stop/update
├── deploy.py                    ← Manual deploy script
├── deploy.env                   ← SSH credentials (keep private)
├── .github/workflows/
│   └── deploy.yml               ← Auto-deploy on push to main
└── server/
    ├── leads_api.py             ← Entire backend (~150 KB)
    ├── dashboard.html           ← Entire frontend (~135 KB)
    ├── docker-compose.yml       ← PostgreSQL + Redis + Crawl4AI
    ├── init.sql                 ← DB schema
    ├── migrations/              ← DB migrations (applied on startup)
    ├── leadgen-api.service      ← Systemd unit
    └── setup.sh                 ← One-click installer
```

---

## Database Schema

| Table | Purpose |
|---|---|
| `leads` | Every discovered business — name, city, niche, phone, address, website, has_website, website_verified, ai_score, status |
| `contacts` | Owner per lead — full_name, email, linkedin_url, job_title |
| `assets` | Generated content — mockup images, email subject, email body |
| `outreach_log` | Every email sent — recipient, timestamps, open/reply |
| `processed_cache` | SHA hashes of past searches — prevents duplicate processing |
| `discovery_state` | Round counter per (niche, city) — tracks which round each search is on |
| `workflow_runs` | Background job log |

### Key columns on `leads`

| Column | Type | Description |
|---|---|---|
| `has_website` | boolean | Whether a website was found (Google Places field) |
| `website_verified` | boolean / null | `TRUE` = verified by HTTP ping, `NULL` = not yet checked |
| `phone_norm` | varchar | Last 10 digits of phone for dedup |
| `domain` | varchar | Stripped domain for dedup |
| `ai_score` | integer | Gemini score 1–10 |
| `status` | varchar | discovered → enriched → scored → ready → approved → sent → replied |

---

## Troubleshooting

### "0 new leads" after search

1. **Wrong location**: If you searched a US state ("Texas"), the parser maps it to the largest city (Houston). Check the parsed result shown on screen — it should say the city, not the state.
2. **All filtered out**: If you used "No Website" filter at search time, every business with a website is silently dropped. Switch to "All" filter and use Verify Websites instead.
3. **Places API error**: The platform auto-falls back to Classic API. If you see "0 candidates" in the live log, check your Google API key has Places API enabled and billing is set up.

### Search returns wrong niche or city

The regex fallback runs when Gemini is unavailable. If results look wrong:
- Use format `"<business type> in <city>, <country>"` — explicit and unambiguous.
- If Gemini key is missing or rate-limited, set a valid key in Settings.

### Server logs

```bash
journalctl -u leadgen-api -f         # Live API log
docker compose -f /opt/leadgen/docker-compose.yml ps   # Docker services status
curl http://localhost:8080/health     # API health check
```

### Restart everything

```bash
systemctl restart leadgen-api
cd /opt/leadgen && docker compose restart
```

### Database backup

```bash
docker exec leadgen_postgres pg_dump -U leadgen leadgen_db > backup_$(date +%Y%m%d).sql
```

---

## Security Checklist

Before going to production:

- [ ] Change dashboard login: edit `AUTH_USERS` dict in `leads_api.py`
- [ ] Change PostgreSQL password: update `docker-compose.yml` and `leads_api.py`
- [ ] Change Redis password: same files
- [ ] Rotate all API keys hardcoded in `leads_api.py` — move them to `/opt/leadgen/config.json` only
- [ ] Add a reverse proxy (nginx) with HTTPS + basic auth in front of port 8080
- [ ] Remove or rotate `deploy.env` after setup — it contains your SSH password
- [ ] Set up daily database backups

---

## Changelog

### v7.0 — June 2026 (current)

**New features**
- **Website Verification** — HTTP ping + Serper search confirms which leads truly have no website. Shows `NO SITE` / `✓` / `?` badges. New "✓ No Website (verified)" filter shows only confirmed hot leads.
- **Enrichment Strategy Selector** — Choose Serper Only / Oxylabs Only / Smart / 100% Free in Settings. Per-run override on Pipeline page. "Enrich All" step now respects the selected strategy.
- **HERE Maps** — Third lead discovery source (free 250k transactions/month). Set `here_api_key` in Settings to activate.
- **Stop Search** — Cancel an in-progress search/discovery job instantly.
- **Sort by** — Sort leads by newest, oldest, highest score, name A→Z/Z→A, city, niche.

**Bug fixes**
- Query parser completely rewritten: extracts the real niche from your query (any business type, not a fixed 25-word list); understands all 50 US states (→ redirected to largest city); no more silent "Dubai" or "restaurant" defaults when Gemini fails.
- Google Places API returns errors as 200 OK with JSON body — platform now detects and auto-falls back to Classic API.
- Default website filter changed from "No Website" to "All" — previously silently dropped all leads in established cities (Toronto, Beverly Hills) which almost all have websites.
- Gemini model fallback: tries 3 model names in sequence so a deprecated model doesn't break query parsing.

### v6.1 — May 2026

- Multi-source expanding discovery engine (Google Places + OSM, round-based)
- Live search progress panel with log
- Sort dropdown on Leads page
- HERE Maps groundwork

### v5.0 — April 2026

- Initial public release
- Single-source Google Places discovery
- Enrichment pipeline (Serper + Oxylabs + Crawl4AI)
- AI scoring (Gemini), email copy (Claude), mockup images (Replicate)
- Resend email sending + outreach approval flow

---

## Support

| Resource | When to use |
|---|---|
| `1_INSTALLATION_GUIDE.md` | Fresh VPS setup |
| `4_API_REFERENCE.md` | All endpoints with curl examples |
| `PLATFORM_OVERVIEW.md` | Architecture and code internals |
| `HOW_TO_RUN.md` | Day-to-day operations |
| `journalctl -u leadgen-api -f` | Live error logs |
| `curl http://localhost:8080/health` | API health check |

---

**Platform:** Controva Intelligence Platform v7.0  
**Built for:** Controva LLC (Support@controvallc.com)  
**License:** Proprietary — Controva LLC  
**Last updated:** June 2026


TO run this platform on local : 
1. Make sure the docker is running and postgres is running on docker-compose.yml file or use this command to start it: 
docker compose -f docker-compose.local.yml up -d

2. and use this command to start application server: 
python server/leads_api.py

3. Run the "1_INSTALLATION_GUIDE.md" guide 
4. Start the platform using " HOW_TO_RUN.md" guide
