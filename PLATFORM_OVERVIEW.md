# Controva Intelligence Platform — Complete Overview

> **What is this?**
> An AI-powered lead generation system. You search for businesses (e.g. "laundry shops in Dubai"),
> it finds businesses with no website, scores them with AI, finds owner contact details,
> writes personalised outreach emails, and lets you send them — all from one dashboard.

---

## 1. The Big Picture

```
Your Browser
     │
     ▼
dashboard.html  ←── single HTML file, the entire frontend UI
     │
     │  HTTP calls (same server)
     ▼
leads_api.py  ←── Python backend, port 8080, handles all logic
     │
     ├──► PostgreSQL  ←── stores all leads, contacts, emails, pipeline
     ├──► Redis       ←── caching / queue
     ├──► Crawl4AI    ←── scrapes websites to find emails
     │
     └──► External APIs:
           ├── Google Places (New + Classic) — primary business discovery
           ├── OpenStreetMap Overpass        — free secondary source
           ├── HERE Maps Discover            — free third source (optional)
           ├── Google Geocoding              — city → lat/lng
           ├── Gemini (Google AI)            — query parsing + scoring
           ├── Claude (Anthropic)            — email copy generation
           ├── Serper                        — email/LinkedIn enrichment + website verify
           ├── Oxylabs                       — deep scraping fallback
           ├── Replicate / imagine.art       — mockup image generation
           └── Resend                        — outreach email delivery
```

---

## 2. Server Details

| Item | Value |
|---|---|
| Server IP | `2.25.152.153` |
| Dashboard URL | `http://2.25.152.153:8080/` |
| Login | `admin` / `ChangeMe_2026!` |
| OS | Ubuntu 22.04/24.04 |
| All files live at | `/opt/leadgen/` on the server |

---

## 3. What Each File Does

### On the Server (`/opt/leadgen/`)

| File | What it does |
|---|---|
| `leads_api.py` | The entire backend. Python HTTP server on port 8080. Handles all API endpoints, talks to all external services, manages the database. |
| `dashboard.html` | The entire frontend. One HTML file with React inside. The UI you see in the browser. |
| `config.json` | Your API keys and settings. Edit this to change keys without touching code. |
| `docker-compose.yml` | Starts PostgreSQL, Redis, and Crawl4AI as Docker containers. |

### On Your PC (`LeadGen_Platform_Complete/`)

| File | What it does |
|---|---|
| `deploy.py` | Pushes your local files to the server via SSH. Run `python deploy.py ui` to update the dashboard, `python deploy.py api` to update the backend. |
| `deploy.env` | SSH connection details (server IP, password). **Keep this private.** |
| `server/setup.sh` | One-click installer. Run this on a fresh Ubuntu VPS to set everything up from scratch. |

---

## 4. The Three Docker Services

These run in the background on your server. You never touch them directly.

| Service | Port | What it does |
|---|---|---|
| **PostgreSQL 16** | 5432 | The database. Stores all your leads, contacts, emails, everything. |
| **Redis 7** | 6379 | Cache layer. Prevents re-processing the same searches. |
| **Crawl4AI** | 11235 | Scrapes business websites to extract owner email addresses. |

**Check if they're running:**
```bash
ssh root@2.25.152.153
docker compose -f /opt/leadgen/docker-compose.yml ps
```

---

## 5. The API Keys — What Each One Does

All keys are stored in `/opt/leadgen/config.json` on the server.

| Key | Service | Used For |
|---|---|---|
| `google_api_key` | Google Places API | **Core** — finds businesses by niche + city. Without this, search doesn't work. |
| `gemini_key` | Google Gemini AI | Parses your natural language search into structured queries. Also scores leads 1–10. |
| `serper_key` | Serper.dev | Finds owner email addresses + verifies websites (Serper search). |
| `claude_key` | Anthropic Claude | Writes personalised outreach email copy for each lead. |
| `oxylabs_key` | Oxylabs | Premium web scraper for finding emails (fallback if Serper fails). |
| `here_api_key` | HERE Maps | Third lead discovery source — 250k free transactions/month. Set in Settings. |
| `replicate_token` | Replicate | Generates website mockup images (optional, off by default). |
| `imagine_art_key` | Imagine.art | Alternative image generator for mockups (optional). |
| `resend_key` | Resend | Sends the outreach emails from your domain. |
| `from_email` | — | The email address outreach is sent from. |
| `from_name` | — | The sender name on outreach emails. |

**To update a key on the server:**
```bash
ssh root@2.25.152.153
nano /opt/leadgen/config.json
systemctl restart leadgen-api
```

---

## 6. The Dashboard — What Each Page Does

| Page | What it does |
|---|---|
| **Dashboard** | Overview stats — total leads, pipeline stages, reply rates. |
| **Search** | Natural-language search with live progress, density selector, website filter, Stop button. |
| **Leads** | Table of all discovered businesses. Sort by date/score/name/city/niche. Filter tabs including "✓ No Website (verified)". Verify Websites button with live progress. Multi-select + CSV download. |
| **Pipeline** | Enrichment workflow — choose Serper / Oxylabs / Smart / Free strategy. Runs Crawl4AI + Serper to find emails, scores with Gemini, writes email with Claude. |
| **Outreach** | Review and approve emails before sending. Edit / Regenerate / Reject. Send via Resend. |
| **Analytics** | Charts: leads per day, status breakdown, niche/city breakdown, score distribution. |
| **SEO** | Keyword research, SERP analysis, Google Trends. |
| **Competitors** | Tech stack, social profiles, backlinks, Wayback Machine snapshots. |
| **People** | Decision-maker finder (free Apollo.io alternative). |
| **Social** | Social media scout across Instagram, TikTok, YouTube. |
| **E-commerce** | Amazon/eBay product and niche research. |
| **Settings** | API keys (including HERE Maps), enrichment strategy selector, image provider, automation toggles. |

---

## 7. How a Lead Goes Through the System

```
1. SEARCH
   You type "laundry shops in Dubai"
   → Gemini parses it → Google Places finds ~20 businesses
   → Saved to database as status: "discovered"

2. FILTER
   On Leads page: filter "Hot (no website)" = businesses with no website
   → These are your best prospects (they need web services)

3. ENRICH  (Pipeline page)
   Click "Run Enrichment" on a lead
   → Crawl4AI scrapes their social pages
   → Serper searches "[business name] owner email"
   → Email found → saved to Contacts table
   → Status becomes: "enriched"

4. SCORE  (Pipeline page)
   Click "Run AI Score"
   → Gemini reviews the business (rating, review count, location)
   → Gives score 1-10 with reason
   → Status becomes: "scored" or "ready" (if score ≥ 7)

5. EMAIL WRITE  (Pipeline page)
   Click "Write Email"
   → Claude generates personalised subject + body
   → Optionally generates a website mockup image (if Replicate enabled)
   → Status becomes: "ready"

6. APPROVE + SEND  (Outreach page)
   Review the email, approve it
   → Resend delivers it to the owner's email
   → Status becomes: "sent"

7. TRACK
   Dashboard shows open rates, replies
   → Replied leads become "replied" → "closed"
```

---

## 8. The Lead Status Flow

```
discovered → enriched → scored → ready → approved → sent → replied → closed
                                                              ↓
                                                           rejected
```

---

## 9. Database Tables

| Table | Stores |
|---|---|
| `leads` | Every business found — name, location, phone, website, has_website, website_verified, ai_score, status |
| `contacts` | Owner details per lead — name, email, LinkedIn, job title |
| `assets` | Generated content — mockup images, email subject, email body |
| `outreach_log` | Every email sent — to whom, when, opened/replied timestamps |
| `processed_cache` | Hashes of past searches — prevents running the same search twice |
| `discovery_state` | Round counter per (niche, city, country) — tracks search depth for "Find More" |
| `workflow_runs` | Log of background jobs |

**Key columns on `leads`:**
- `has_website` (boolean) — whether a website was listed in the Places API response
- `website_verified` (boolean/null) — `TRUE` after HTTP verification, `NULL` if not yet checked
- `phone_norm` (varchar) — last 10 digits of phone number used for deduplication
- `domain` (varchar) — stripped domain used for deduplication across sources

---

## 10. How to Manage the Server

```bash
# SSH in
ssh root@2.25.152.153

# Check everything is running
systemctl status leadgen-api          # Is the Python API running?
docker compose -f /opt/leadgen/docker-compose.yml ps  # Are DB/Redis/Crawl4AI up?

# Restart the API (after config changes)
systemctl restart leadgen-api

# Watch live logs
journalctl -u leadgen-api -f

# Restart all Docker services
cd /opt/leadgen && docker compose restart

# Backup the database
docker exec leadgen_postgres pg_dump -U leadgen leadgen_db > backup.sql
```

---

## 11. How to Deploy Updates from Your PC

```powershell
cd C:\Users\ANC\Downloads\LeadGen_Platform_Complete

python deploy.py ui       # Update the dashboard UI only (instant, no restart)
python deploy.py api      # Update the backend + restart the service
python deploy.py          # Update both
python deploy.py status   # Check server health
python deploy.py logs     # Tail live server logs
python deploy.py pull     # Download live files FROM server to your PC
```

---

## 12. Deploy to a New Server

1. Get a new Ubuntu 22.04/24.04 VPS
2. Upload the `server/` folder to `/root/LeadGen/server/` on the new VPS
3. SSH in and run:
   ```bash
   cd /root/LeadGen/server
   chmod +x setup.sh
   sudo ./setup.sh
   ```
4. Edit `/opt/leadgen/config.json` with your API keys
5. Run `systemctl restart leadgen-api`
6. Update `deploy.env` on your PC with the new server IP/password

---

## 13. Important Security Notes

- The `deploy.env` file contains your server SSH password — never share or commit it to GitHub
- `leads_api.py` has API keys hardcoded as fallbacks — the real keys should be in `/opt/leadgen/config.json` on the server
- The dashboard login (`admin` / `ChangeMe_2026!`) should be changed if this is a production server
- Port 8080 is open to the internet — anyone who knows the IP can reach the login page

---

*Generated: June 2026 | Platform: Controva Intelligence Platform v5*
