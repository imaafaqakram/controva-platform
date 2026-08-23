# Controva Intelligence Platform
## Company & Product Dossier
### For Startup Support Programs, Cloud Credits & Partnership Applications
**Company:** Controva LLC  
**Contact:** Support@controvallc.com  
**Current Version:** v7.0 (July 2026)  
**Document Purpose:** Technical + Business overview for AWS Activate, Google for Startups, DigitalOcean Hatch, YC Startup School, and similar programs

---

## 1. Executive Summary

**What is Controva Intelligence Platform?**

Controva is a full-stack, AI-powered **B2B outreach intelligence platform** built for agencies, freelancers, and sales teams who sell services (web design, SEO, marketing, development) to small and medium businesses. It automates the entire lead lifecycle from first discovery to first email reply, in a single self-hosted dashboard.

**The core problem it solves:**

Agencies that sell services to businesses without websites spend enormous time manually:
1. Searching for businesses without online presence on Google Maps
2. Copy-pasting names into LinkedIn / email lookup tools (Apollo.io, Hunter.io — $50-$500/month)
3. Writing individualized cold emails one at a time

Controva eliminates all three bottlenecks with AI automation.

**Value proposition in one sentence:**
> *"Type 'pest control companies in New Jersey' — Controva finds 100+ businesses that have no website, identifies the owner's contact info, scores every lead 1-10 with AI reasoning, writes a personalized cold email for each one, and sends it on your behalf. All in under 10 minutes."*

---

## 2. Company Information

| Field | Value |
|---|---|
| **Company Name** | Controva LLC |
| **Email** | Support@controvallc.com |
| **Type** | Technology Startup (Software) |
| **Stage** | Product Live — Pre-Revenue / Early Traction |
| **Category** | B2B SaaS / AI-Powered Sales Intelligence |
| **Target Customers** | Digital agencies, freelancers, SDR teams, web dev/SEO service providers |
| **Business Model** | Self-hosted license (current) → transitioning to SaaS subscription |
| **Geography** | Built for global use: US, UK, UAE, Pakistan, India, Australia, Canada, EU and 50+ countries |

---

## 3. Platform Architecture — Technical Overview

The platform consists of **two core components** and **four infrastructure services**, all containerized and self-hosted:

```
┌──────────────────────────────────────────────────────────┐
│                  CONTROVA PLATFORM STACK                 │
│                                                          │
│  Frontend: dashboard.html (React, Tailwind, ~135 KB)     │
│  Backend:  leads_api.py   (Python, ~280 KB, 5,700 lines) │
│                                                          │
│  Infrastructure (Docker):                                │
│    ├── PostgreSQL 16  — primary database                 │
│    ├── Redis 7         — query result cache              │
│    └── Crawl4AI        — async web scraper               │
│                                                          │
│  Deployment: Ubuntu VPS, port 8080, systemd service      │
└──────────────────────────────────────────────────────────┘
```

### Technology Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 (CDN), Tailwind CSS, custom SVG icons |
| Backend | Python 3 (stdlib only — no Flask/Django) |
| Database | PostgreSQL 16 |
| Cache | Redis 7 |
| Web Scraper | Crawl4AI (Docker, self-hosted) |
| Deployment | Ubuntu 22.04/24.04 VPS, systemd |
| CI/CD | GitHub Actions (auto-deploy on push to main) |
| DNS / Proxy | Nginx (recommended) |

---

## 4. Platform Modules — Full Feature Breakdown

The platform has **12 distinct modules**, all accessible from a single dashboard:

---

### Module 1: Intelligent Lead Discovery

**What it does:** Finds small businesses in any city worldwide using natural language search.

**How it works:**
1. User types: *"roofing contractors in Houston, Texas"*
2. Gemini AI parses the query into structured fields: `{niche: "roofing contractor", city: "Houston", country: "US"}`
3. Regex fallback parser activates if Gemini is unavailable — understands all 50 US states, 60+ countries
4. Google Geocoder converts city → GPS coordinates
5. **Multi-source discovery runs in parallel:**
   - **Google Places API (New)** — primary, up to 60 results per query
   - **Google Places API (Classic)** — automatic fallback on auth errors
   - **OpenStreetMap Overpass API** — free, always active alongside Google
   - **HERE Maps Discover API** — free 250k/month, activates when key is set
6. **Gemini expands the niche** — generates synonyms, subtypes, and OSM tags ("roofing contractor" → "roofer, roofing company, roofing services, tile roofer, commercial roofing")
7. **Expanding round system** — "Find More" clicks widen the radius and use more search terms, never re-discovering the same businesses

**Discovery coverage:**
| Density | Map Tiles | Best For |
|---|---|---|
| Fast | 5 tiles | Quick test, small cities |
| Standard | 9 tiles | Most searches |
| Thorough | 25 tiles | Large metros, deep coverage |

**Cross-source deduplication:** by Google Place ID, normalized phone (last 10 digits), and domain

---

### Module 2: Website Verification Engine

**What it does:** Confirms whether each discovered business actually has a live, working website.

**Two-path verification:**
- For leads **with** a stored URL: HTTP HEAD → GET request, checks response < 400
- For leads **without** a stored URL: Serper web search for `"[business name]" [city] official website`, filters out social/directory sites (Facebook, Yelp, Google Maps, Apple Maps, etc.)

**Output badges on leads:**
| Badge | Meaning |
|---|---|
| `NO SITE` (red) | Verified — confirmed no website → hot lead |
| `✓` (green) | Verified — has a live website |
| `?` (gray) | Not yet verified |
| `🌐` (green) | Has URL stored (unverified) |

---

### Module 3: Contact Enrichment Pipeline

**What it does:** Finds the decision-maker's email address and LinkedIn profile for each lead.

**4-tier enrichment strategy (configurable per run):**

| Strategy | What It Does | Cost |
|---|---|---|
| **Serper Only** | Web search for owner email + LinkedIn | Serper credits only |
| **Oxylabs Only** | Deep residential proxy scrape | Oxylabs credits |
| **Smart (Serper → Oxylabs)** | Serper first, Oxylabs fills gaps | Both (best results) |
| **100% Free** | Free web scrape + email permutator | Zero cost |

**Free enrichment pipeline (when no paid keys):**
1. Guesses the business domain from name
2. DuckDuckGo instant answer for official site
3. Jina Reader (free, unlimited) scrapes homepage, /contact, /about
4. Extracts emails with regex, social links with pattern matching
5. **Email Permutator** — generates likely addresses (`first.last@domain.com`, `info@`, `hello@`) + DNS MX verification

**Database tables populated:**
- `contacts` → full_name, email, linkedin_url, job_title, confidence score
- `assets` → email_subject, email_body, mockup_image (URL)

---

### Module 4: AI Lead Scoring

**What it does:** Gemini AI rates every lead from 1-10 with written justification.

**Scoring factors:**
- Google rating and review count (high rating = credible business)
- Niche demand signal (pest control vs. hobby shop)
- Business size indicators (address type, phone type)
- Location (city tier, market size)
- Presence signals (Instagram listed, other social)

**Score threshold:** Leads with AI score ≥ 7 become "hot leads" and appear in the `hot_leads` database view.

---

### Module 5: Personalized Email Copywriting

**What it does:** Claude (Anthropic) writes a fully personalized cold outreach email for each lead.

**Email generation includes:**
- Personalized subject line referencing the business name + niche
- Body that mentions the business's specific city, niche, and lack of web presence
- Call to action tailored to the service being offered
- Optional: website mockup image attached (generated by Replicate or imagine.art)

**Email variables:**
- Business name, niche, city
- Owner name (if enriched)
- Score reason from Gemini (used to personalize opening hook)

---

### Module 6: Multi-Channel Email Outreach & Tracking

**What it does:** Review, approve, edit, and send outreach emails with full tracking.

**Outreach workflow:**
1. **Approve** — review AI-written email + mockup before sending
2. **Reject** — mark lead as not suitable
3. **Edit** — manually modify subject/body before sending
4. **Regenerate** — re-run Claude for a fresh email
5. **Send** — delivers via Resend.com (authenticated, domain-verified)

**Tracking metrics:**
- Sent at timestamp
- Opened at (requires email tracking pixel, via Resend webhook)
- Replied at
- Follow-up due date

---

### Module 7: SEO & Keyword Research

**What it does:** Full keyword research, SERP analysis, and Google Trends data.

**Features:**
- Keyword volume + competition lookup via Serper
- SERP position analysis for any domain
- Google Trends integration (trending queries, related topics)
- Backlink checker via Serper news + organic search
- Tech stack detection via page source analysis

---

### Module 8: Competitor Intelligence

**What it does:** Deep analysis of any competitor domain.

**Features:**
- Technology stack detection (CMS, frameworks, analytics tools)
- Social media profile links (Facebook, Instagram, LinkedIn, TikTok)
- Backlink discovery via Serper
- Wayback Machine historical snapshots
- SERP ranking analysis

---

### Module 9: People & Decision-Maker Finder

**What it does:** Free alternative to Apollo.io — finds decision-makers at any company.

**Features:**
- Company name → finds LinkedIn profiles of owners, founders, C-suite
- Email discovery and confidence scoring
- Job title extraction
- Social profile URLs

---

### Module 10: Social Media Intelligence

**What it does:** Scouts and analyzes social media presence across platforms.

**Platforms covered:**
- Instagram
- TikTok
- YouTube

**Data extracted:**
- Account name, followers, post count
- Engagement patterns
- Contact info from bios

---

### Module 11: E-commerce Product Research

**What it does:** A full product hunting and market validation engine for e-commerce sellers.

**Two research modes:**

**a) Product Hunt** — AI-driven product discovery:
1. Serper searches Google Shopping, Amazon bestsellers, article mentions
2. Google Trends analysis
3. eBay Browse API (live listing counts + price ranges)
4. Gemini identifies 10+ candidate products
5. Every candidate is **cross-validated** against live eBay/Amazon/Google data — unverified products are dropped, never shown as opportunities
6. Gemini scores each verified product: demand (30), competition (25), margin (25), trend (20)
7. Returns: Hunter Score, entry price, estimated monthly sales, strategy, verdict (BUY/TEST/AVOID)

**b) Deep Ecommerce Research** — detailed market analysis for a specific product:
- Google Shopping listings with prices and ratings
- eBay live listings (via Browse API) with price min/median/max
- Amazon data via Serper
- AI verdict: "is this a good product to sell right now?"

**Market coverage:**
US, UK, Canada, Australia, Germany, France, Italy, Spain (full currency + marketplace support)

---

### Module 12: Platform Settings & API Management

**What it does:** Central control panel for all API keys, enrichment strategy, automation toggles.

**API keys managed:**

| Key | Service | Purpose |
|---|---|---|
| `google_api_key` | Google Places + Geocoding | Core business discovery |
| `gemini_key` | Google Gemini AI | Query parsing, lead scoring, niche expansion |
| `serper_key` | Serper.dev | Email enrichment, website verification, SEO, e-commerce |
| `claude_key` | Anthropic Claude | Personalized email copywriting |
| `oxylabs_key` | Oxylabs AI Studio | Deep enrichment scraping |
| `here_api_key` | HERE Maps | Third discovery source (free 250k/month) |
| `replicate_token` | Replicate FLUX | Website mockup image generation |
| `imagine_art_key` | imagine.art | Alternative image generator |
| `resend_key` | Resend.com | Email delivery |
| `scrapingbee_key` | ScrapingBee | Anti-bot scraping fallback (1k free/month) |
| `zenrows_key` | ZenRows | Anti-bot scraping fallback (1k free/month) |
| `scrapingdog_key` | Scrapingdog | Anti-bot scraping fallback (1k free/month) |
| `firecrawl_key` | Firecrawl.dev | Structured scraping fallback (500 free/month) |
| `ebay_client_id` | eBay Browse API | Live product listing data (5,000 free calls/day) |

**Automation toggles:**
- `auto_score` — automatically run Gemini scoring after discovery (default: ON)
- `auto_email_copy` — automatically write email with Claude (default: OFF)
- `auto_image` — automatically generate mockup images (default: OFF)

---

## 5. Database Schema

| Table | Records | Purpose |
|---|---|---|
| `leads` | Businesses | Core table — name, location, phone, website, AI score, status |
| `contacts` | Decision makers | Email, LinkedIn, job title per lead |
| `assets` | Generated content | Mockup images, email subject, email body |
| `outreach_log` | Sent emails | Recipient, timestamps, open/reply tracking |
| `processed_cache` | Dedup hashes | Prevents re-processing same searches |
| `discovery_state` | Round counters | Tracks which search depth each (niche, city) is at |
| `research_cache` | Full results | Caches e-commerce/SEO research results (24h TTL) |
| `research_history` | Run history | Permanent log of all research runs |
| `workflow_runs` | Job logs | Background pipeline execution history |
| `intent_signals` | Intent data | Buying intent detection from web signals |

**Key computed field:** `has_website BOOLEAN GENERATED ALWAYS AS (website IS NOT NULL AND website != '') STORED` — automatically maintained, indexed for fast filtering.

---

## 6. API Endpoints (Backend)

The Python backend exposes **35+ REST endpoints** on port 8080:

| Endpoint | Method | Purpose |
|---|---|---|
| `/` | GET | Serve dashboard.html |
| `/health` | GET | Health check (returns DB + service status) |
| `/login` | POST | JWT session authentication |
| `/search` | POST | Start a new lead discovery job |
| `/jobs/{id}` | GET | Poll live progress of a background job |
| `/jobs/{id}/cancel` | POST | Cancel a running search |
| `/leads` | GET | Paginated leads list with sort/filter |
| `/leads/{id}` | GET/PUT/DELETE | Individual lead CRUD |
| `/leads/export` | GET | CSV export |
| `/leads/verify` | POST | Start website verification job |
| `/leads/verify/{id}` | POST | Verify a single lead's website |
| `/pipeline/enrich` | POST | Start contact enrichment job |
| `/pipeline/score` | POST | Run Gemini AI scoring on all leads |
| `/pipeline/generate-copy` | POST | Run Claude email writing on all leads |
| `/pipeline/generate-image/{id}` | POST | Generate mockup image for one lead |
| `/outreach` | GET | List email drafts pending approval |
| `/outreach/{id}/approve` | POST | Approve and queue email |
| `/outreach/{id}/send` | POST | Send email via Resend |
| `/outreach/{id}/reject` | POST | Reject email draft |
| `/outreach/{id}/regenerate` | POST | Re-run Claude for fresh copy |
| `/analytics` | GET | Dashboard stats and chart data |
| `/seo` | POST | SEO keyword research |
| `/competitors` | POST | Competitor intelligence |
| `/people` | POST | Decision-maker finder |
| `/social` | POST | Social media scout |
| `/ecommerce` | POST | Deep product research |
| `/product-hunt` | POST | AI product discovery |
| `/config` | GET/POST | Read/update API keys and toggles |
| `/intent` | POST | Intent signal search |

---

## 7. Intelligence Pipeline — Full Lead Journey

```
1. DISCOVER     User types natural language → AI parses → 4 sources searched in parallel
                Dedup by place_id, phone, domain → new leads saved as "discovered"

2. VERIFY       HTTP ping or Serper web search → confirms website presence
                Badges: NO SITE (hot) | ✓ (has site) | ? (unverified)

3. FILTER       "Hot (no website)" tab → confirmed targets for web/SEO outreach

4. ENRICH       Crawl4AI + Serper/Oxylabs finds owner email + LinkedIn
                Email permutator generates + DNS-validates guessed addresses
                Status: "enriched"

5. SCORE        Gemini AI scores 1-10 with written reason
                Status: "scored" (< 7) or "ready" (≥ 7, promoted to hot queue)

6. WRITE        Claude writes personalized subject + body
                FLUX / imagine.art generates website mockup image
                Status: "ready"

7. APPROVE      Human reviews email + mockup → Approve / Reject / Edit / Regenerate

8. SEND         Resend.com delivers authenticated email
                Status: "sent"

9. TRACK        Open pixel fires → "opened"
                Reply webhook → "replied" → pipeline stage "closed" or "rejected"
```

---

## 8. Competitive Analysis

| Feature | Controva | Apollo.io | Hunter.io | Instantly.ai |
|---|---|---|---|---|
| Lead discovery (no website filter) | ✅ Full | ❌ None | ❌ None | ❌ None |
| Worldwide business search | ✅ 60+ countries | ✅ Limited | ❌ US/EU | ❌ Limited |
| AI lead scoring (1-10 with reason) | ✅ Gemini | ❌ None | ❌ None | ❌ None |
| Personalized email copywriting | ✅ Claude AI | ❌ None | ❌ None | ✅ Templates |
| Website mockup generation | ✅ FLUX AI | ❌ None | ❌ None | ❌ None |
| E-commerce product research | ✅ Full module | ❌ None | ❌ None | ❌ None |
| SEO + competitor intelligence | ✅ Full module | ❌ None | ❌ None | ❌ None |
| Self-hosted (no data leakage) | ✅ Full control | ❌ SaaS only | ❌ SaaS only | ❌ SaaS only |
| Enrichment cost | ~$0-20/mo | $49-$399/mo | $49-$499/mo | $37-$277/mo |
| Requires no coding to use | ✅ Dashboard UI | ✅ | ✅ | ✅ |

**Key differentiator:** Controva is the **only** tool that finds businesses that do NOT have a website — specifically targeting the niche of agencies that sell web design / digital marketing services to offline businesses.

---

## 9. Planned Features (Product Roadmap)

### Q3 2026 — Cloudscape UI Migration
- **Complete redesign** to Cloudscape Design System (AWS open-source)
- New architecture: Vite + React + TypeScript frontend
- AWS AppLayout, SideNavigation, TopNavigation
- Cloudscape Table, Form, Modal, Alert components throughout

### Q4 2026 — Multi-Tenancy & SaaS Launch
- User accounts with role-based access (Admin, Operator, Viewer)
- Per-workspace lead isolation
- Usage quotas per user
- Stripe billing integration

### Q1 2027 — AI Intent Engine
- Monitors Craigslist, Reddit, Facebook Groups for buying signals
- "Businesses posting in 'looking for website' forums" → instant alert
- Intent score layered on top of AI lead score

### Q2 2027 — CRM Integrations
- Zapier webhooks
- HubSpot native integration
- Pipedrive native integration
- GoHighLevel connector (agency CRM)

### Q3 2027 — WhatsApp Outreach Channel
- Send personalized WhatsApp messages via WhatsApp Business API
- Template message management
- Reply tracking integrated into pipeline

### Q4 2027 — Enterprise Features
- Custom AI model fine-tuning per agency niche
- White-label dashboard with custom branding
- Multi-server distributed discovery
- Team collaboration + lead assignment

---

## 10. Current Infrastructure (as of July 2026)

| Component | Spec | Provider |
|---|---|---|
| VPS Server | Ubuntu 24.04, 8 vCPU, 16 GB RAM, 100 GB SSD | Hostinger / DigitalOcean |
| Database | PostgreSQL 16 (Docker container) | Self-hosted on VPS |
| Cache | Redis 7 (Docker container) | Self-hosted on VPS |
| Web Scraper | Crawl4AI 0.7.x (Docker container) | Self-hosted on VPS |
| CI/CD | GitHub Actions (auto-deploy) | GitHub |
| Email delivery | Resend.com | Third-party |
| Domain | controvallc.com | — |

---

## 11. Security Posture

| Area | Current Status |
|---|---|
| Authentication | Session-based auth with hashed passwords |
| API key storage | Disk-based `config.json` (not in source code) |
| Database | Private Docker network, no external port exposure |
| Transport | Nginx reverse proxy + HTTPS (recommended) |
| API keys in code | Documented — should be moved to `config.json` |
| Port exposure | Port 8080 open — recommended to put behind Nginx |
| **Planned:** | JWT + OAuth2, secrets manager, SOC 2 prep |

---

## 12. Questions Commonly Asked by AWS / Startup Programs

### Q: What problem does Controva solve?
**A:** Controva solves the "cold outreach cold start" problem for digital agencies. Agencies that sell web design, SEO, and marketing services to businesses **without** websites have no good tool to find, qualify, and contact those businesses at scale. Existing tools (Apollo.io, Hunter.io) focus on finding people at companies that already exist online — not the opposite (businesses with no digital presence at all).

### Q: Who is your target customer?
**A:** Digital marketing agencies, freelance web designers/developers, SEO consultants, and SDR teams at marketing software companies. Any team that sells digital services to offline businesses.

### Q: What is your business model?
**A:** Currently self-hosted license. Transitioning to a SaaS model in Q4 2026 with tiered pricing: Starter ($49/month), Growth ($149/month), Agency ($399/month).

### Q: What stage are you at?
**A:** The product is live, deployed on a production VPS, and being used. We are at pre-revenue, validating product-market fit and building the SaaS infrastructure.

### Q: Why do you need cloud credits?
**A:** To build the multi-tenant SaaS infrastructure: managed PostgreSQL (RDS), serverless backend (Lambda/App Runner), file storage (S3 for generated mockup images), CDN distribution (CloudFront), and CI/CD pipelines (CodePipeline).

### Q: What AI services do you use?
**A:** Google Gemini (query parsing, lead scoring, niche expansion, product scoring), Anthropic Claude (email copywriting), FLUX / imagine.art (image generation). We want to evaluate Amazon Bedrock as a potential alternative/supplement.

### Q: How many leads can the system handle?
**A:** The current architecture handles ~50,000+ leads in PostgreSQL with indexed queries returning in <100ms. The discovery engine is rate-limited by external APIs, but the platform itself has no lead count limit.

### Q: Is this open source?
**A:** No. Proprietary, owned by Controva LLC. The Cloudscape Design System (UI framework) we plan to migrate to is open source (Apache 2.0, by AWS).

### Q: What is your unfair advantage?
**A:** 
1. **No-website-filter** — unique in the market, zero direct competitors
2. **Self-hosted** — agencies don't trust SaaS tools with their client prospecting data
3. **Multi-source discovery** — Google Places + OpenStreetMap + HERE Maps simultaneously
4. **Free tier capable** — can run on zero paid APIs using free tiers (Gemini free, Serper 2500 free, Jina Reader free, Nominatim free)
5. **One-file deployment** — the entire frontend is one HTML file; extremely easy to update, version, and deploy via SSH/SCP

---

## 13. Infrastructure Wishlist (for AWS Activate)

| Service | Use Case | Estimated Cost/Month |
|---|---|---|
| **Amazon RDS (PostgreSQL)** | Managed multi-tenant database with automated backups | ~$50-200 |
| **Amazon S3** | Store generated mockup images (replacing local `/opt/leadgen/mockups/`) | ~$5-20 |
| **Amazon CloudFront** | CDN for the dashboard static assets + mockup image delivery | ~$5-20 |
| **AWS App Runner / ECS** | Containerized Python backend, auto-scaling | ~$50-200 |
| **Amazon Bedrock** | Evaluate Claude + Titan models as alternatives/supplements | ~$50-500 |
| **AWS Lambda** | Serverless background jobs (enrichment, scoring) | ~$10-50 |
| **Amazon ElastiCache** | Managed Redis for distributed caching across tenants | ~$25-100 |
| **AWS Secrets Manager** | Secure API key storage per tenant (replacing `config.json`) | ~$10-20 |
| **Amazon SES** | Alternative email delivery for outreach (lower cost than Resend) | ~$5-30 |
| **Amazon Cognito** | User auth + MFA for the SaaS multi-tenant version | ~$5-20 |

**Total estimated AWS infrastructure for SaaS v1:** ~$200-$1,200/month depending on usage

---

*Prepared by: Controva LLC | Support@controvallc.com | Version 7.0 | August 2026*
