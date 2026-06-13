# Controva Intelligence Platform — Complete Kit

> Multi-module B2B intelligence platform with 30+ API endpoints, modern React dashboard, AI-powered enrichment, and outreach automation.

---

## What's In This Kit

```
LeadGen_Platform_Complete/
├── README.md                       <- You are here
├── 1_INSTALLATION_GUIDE.md         <- How to install from scratch
├── 2_USER_GUIDE.docx               <- How to use the platform (for end users)
├── 3_DEVELOPER_GUIDE.docx          <- How the code works (for developers)
├── 4_API_REFERENCE.md              <- All 30+ endpoints documented
└── server/
    ├── docker-compose.yml          <- PostgreSQL + Redis + Crawl4AI Docker setup
    ├── init.sql                    <- Database schema (auto-runs on first start)
    ├── leads_api.py                <- Main API server (Python, ~118KB)
    ├── dashboard.html              <- React/Tailwind dashboard (~117KB)
    ├── config.json.template        <- API keys + settings (replace with yours)
    ├── leadgen-api.service         <- Systemd service file
    └── setup.sh                    <- One-click installer
```

---

## Quick Start (15 minutes)

### 1. Get a VPS
- Ubuntu 22.04+ (24.04 or 26.04 recommended)
- Minimum: 4GB RAM, 50GB disk
- Recommended: 16GB RAM (Hostinger KVM 4)

### 2. Upload This Kit to Your Server

```bash
scp -r LeadGen_Platform_Complete root@YOUR_SERVER_IP:/root/
```

### 3. Run the Installer

```bash
ssh root@YOUR_SERVER_IP
cd /root/LeadGen_Platform_Complete/server
chmod +x setup.sh
sudo ./setup.sh
```

The installer will:
- Install Docker, Python, dependencies
- Start PostgreSQL, Redis, Crawl4AI containers
- Open firewall ports (8080, 5432, 6379, 11235)
- Create + start the API service

### 4. Add Your API Keys

```bash
nano /opt/leadgen/config.json
```

Replace these with your real keys:
```json
{
  "google_api_key":  "AIzaSy_YOUR_GOOGLE_KEY",
  "serper_key":      "YOUR_SERPER_KEY",
  "gemini_key":      "AIzaSy_YOUR_GEMINI_KEY",
  "claude_key":      "sk-ant-api03-YOUR_CLAUDE_KEY",
  "replicate_token": "r8_YOUR_REPLICATE_TOKEN",
  "imagine_art_key": "vk-YOUR_IMAGINE_ART_KEY",
  "oxylabs_key":     "YOUR_OXYLABS_KEY",
  "resend_key":      "re_YOUR_RESEND_KEY",
  "from_email":      "you@yourdomain.com",
  "from_name":       "Your Name"
}
```

### 5. Restart & Open

```bash
systemctl restart leadgen-api
```

Open: `http://YOUR_SERVER_IP:8080/`

**Default login:** `admin` / `ChangeMe_2026!` (change immediately)

---

## What This Platform Does

### Lead Generation
- Find businesses worldwide by natural-language search ("barber shops in Manchester UK")
- Filter by website status (no website / has website / all)
- Choose coverage density (5 / 9 / 25 zones)
- Auto-deduplicates against existing leads

### Multi-Provider Enrichment
- Find owner LinkedIn URLs (via Serper)
- Find business emails (via Serper + Oxylabs fallback)
- Verify emails via SMTP RCPT TO check
- Build email patterns (free Hunter.io alternative)
- Discover decision-makers (free Apollo.io alternative)

### AI-Powered Asset Generation
- AI scoring with Gemini (1-10 rating each lead)
- Personalized email copy with Claude
- Website mockup images (Replicate FLUX or imagine.art)

### Intelligence Modules
- SEO keyword research (related, autocomplete, PAA)
- SERP analysis (rankings, features, snippets)
- Competitor intelligence (tech stack, social, keywords)
- Wayback Machine snapshots
- Backlink discovery
- Social media profile scout (Instagram, TikTok, YouTube, etc.)
- E-commerce research (Amazon, eBay)
- Google Trends data

### Outreach Pipeline
- Review email + mockup + LinkedIn before sending
- Approve / Reject / Edit / Regenerate
- Send via Resend.com
- Track sent / opened / replied

### Modern Dashboard
- Light + Dark themes
- Sortable + filterable leads table
- Multi-select + CSV download
- Real-time charts
- Mobile responsive
- Password-protected login

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│   USER BROWSER  →  React Dashboard (port 8080)          │
└───────────────────────┬─────────────────────────────────┘
                        │ REST API
┌───────────────────────▼─────────────────────────────────┐
│   Python API Server  (single-file, threading HTTP)      │
│   30+ endpoints across 6 modules                        │
└──┬─────────────┬─────────────┬──────────────────────────┘
   │             │             │
   ▼             ▼             ▼
EXTERNAL    LOCAL DOCKER   PERSISTENT DATA
APIs        SERVICES       LAYER
- Google    - PostgreSQL   - /opt/leadgen/mockups/
  Places    - Redis        - /opt/leadgen/postgres/data
- Serper    - Crawl4AI     - /opt/leadgen/config.json
- Gemini
- Claude
- Replicate
- imagine.art
- Oxylabs
- Resend
```

---

## File Reference

| File | Size | Purpose |
|---|---|---|
| `leads_api.py` | 118 KB | Single-file Python API + business logic |
| `dashboard.html` | 117 KB | React + Tailwind + inline SVG icons dashboard |
| `init.sql` | 8 KB | PostgreSQL schema (8 tables + 2 views) |
| `docker-compose.yml` | 2 KB | PostgreSQL + Redis + Crawl4AI services |
| `config.json.template` | <1 KB | API keys + provider toggles |
| `leadgen-api.service` | <1 KB | Systemd unit for 24/7 uptime |
| `setup.sh` | 4 KB | One-click installer |

---

## Need Help?

| Document | When to Read |
|---|---|
| **1_INSTALLATION_GUIDE.md** | Setting up from scratch — detailed walkthrough |
| **2_USER_GUIDE.docx** | Daily use — how to find/enrich/send leads |
| **3_DEVELOPER_GUIDE.docx** | Modifying code, adding new modules |
| **4_API_REFERENCE.md** | Integrating other tools, automation |

---

## Default Credentials (CHANGE IMMEDIATELY)

```
Dashboard login: admin / ChangeMe_2026!
PostgreSQL:      leadgen / LeadGen_Secure_2024!
Redis:           (password) Redis_Secure_2024!
Crawl4AI token:  crawl4ai_secret_token_2024
```

Edit these in:
- Dashboard login → inside `leads_api.py` (AUTH_USERS dict)
- PostgreSQL/Redis/Crawl4AI → inside `docker-compose.yml`

---

## Support

If something breaks:
1. Check API logs: `journalctl -u leadgen-api -f`
2. Check Docker: `docker compose ps`
3. Test endpoints: `curl http://localhost:8080/health`
4. Read the Developer Guide for architecture details

---

**License:** Proprietary — Controva LLC
**Built for:** Controva LLC (Support@controvallc.com)
**Version:** 6.1 (Production)
**Last updated:** June 2026
