# API Reference — Controva Intelligence Platform

Complete documentation of all 35+ endpoints.

**Base URL:** `http://YOUR_SERVER_IP:8080`
**Authentication:** Most endpoints are open. For production, add a reverse proxy with HTTP basic auth, or use the `/auth/login` token.
**Content-Type:** `application/json` for all POST requests.
**Version:** 7.0

---

## Authentication

### POST /auth/login
Login and get a session token.

```bash
curl -X POST http://localhost:8080/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"CHANGE_ME_BEFORE_DEPLOY"}'
```

Response:
```json
{"success": true, "token": "RXCx4Mn0EXBoQe7QhqEQfYlYLCbn0x9S..."}
```

### POST /auth/check
Validate a token.

```bash
curl -X POST http://localhost:8080/auth/check \
  -H "Content-Type: application/json" \
  -d '{"token":"YOUR_TOKEN"}'
```

---

## Lead Discovery

### POST /search
Natural-language search. Best entry point. Starts a background job and returns a `job_id` — poll `/job/{job_id}` for progress.

```bash
curl -X POST http://localhost:8080/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "pest control and exterminators in new jersey USA",
    "filter_mode": "all",
    "density": "standard",
    "find_more": false
  }'
```

**Parameters:**
- `query` (required) — Free-text search. The AI parser understands any business type and any city worldwide. US state names ("new jersey", "texas") are automatically mapped to the state's largest city.
- `filter_mode` — `all` (recommended) / `no_website` / `with_website`
- `density` — `low` (5 tiles) / `standard` (9 tiles) / `high` (25 tiles)
- `find_more` — `true` to advance to the next round (wider radius, more synonyms)

Response:
```json
{
  "job_id": "job_1719700000000",
  "status": "started",
  "parsed": {"niche":"pest control and exterminators","city":"Newark","country":"US"}
}
```

Poll `/job/{job_id}` until `status === "completed"`, then read `results`:
```json
{
  "total_new_leads": 47,
  "leads": [...],
  "discover_status": "success",
  "niche": "pest control and exterminators",
  "city": "Newark",
  "country": "US",
  "filter_mode": "all",
  "message": "Found 47 new businesses"
}
```

### POST /discover
Same as `/search` but takes structured input.

```json
{
  "niche": "restaurant",
  "city": "Dubai",
  "country": "AE",
  "filter_mode": "no_website",
  "density": "standard"
}
```

---

## Lead Management

### GET /leads
List all leads in database.

```bash
curl http://localhost:8080/leads
```

Response includes `id`, `business_name`, `niche`, `city`, `country`, `phone`, `address`, `website`, `ai_score`, `status`, `owner_name`, `owner_email`, `linkedin_url`, `mockup_url`, `email_subject`, `email_body`, `date_found`, `lead_type`.

### GET /leads.csv
Download all leads as CSV.

```bash
curl -O http://localhost:8080/leads.csv
```

### GET /lead/{id}
Get full details of a specific lead.

```bash
curl http://localhost:8080/lead/61ad7541-684f-47cd-a8da-e1fd2bdbc7c2
```

### POST /lead/{id}/approve
Mark lead as approved for sending.

### POST /lead/{id}/reject
Mark lead as rejected.

### POST /lead/{id}/send
Send the prepared email via Resend.com.

### POST /lead/{id}/regenerate-email
Regenerate email copy with Claude.

```json
{"instructions": "Make it shorter and friendlier"}
```

---

## Enrichment

### POST /enrich
Enrich all discovered leads (find emails + LinkedIn).

```bash
curl -X POST http://localhost:8080/enrich \
  -H "Content-Type: application/json" \
  -d '{"provider":"serper_then_oxylabs"}'
```

**provider options:**
- `serper_only` — Fast, uses Serper only
- `oxylabs_only` — Deep scrape with Oxylabs
- `serper_then_oxylabs` — Recommended (Serper first, Oxylabs fallback)
- `free_only` — Serper + email permutator only

### POST /reenrich-missing-emails
Re-run enrichment ONLY on leads that have no email yet.

```json
{"use_oxylabs": true}
```

### POST /score
AI-score all enriched leads with Gemini (1-10 rating).

### POST /generate-assets
Generate mockup images + email copy for top-scored leads.

```json
{"image_provider": "imagine_art", "min_score": 5}
```

### POST /run-pipeline
Run enrich + score + generate in sequence (async background job).

```json
{"provider":"serper_then_oxylabs", "generate_images": false}
```

Returns `job_id`. Poll `/job/{job_id}` for progress.

### GET /job/{job_id}
Get background job status, progress, log, and results.

```bash
curl http://localhost:8080/job/job_1719700000000
```

Response:
```json
{
  "status": "running",       // running | completed | failed | cancelled
  "progress": 42,            // 0–100
  "log": ["Searching...", "Found 23 businesses..."],
  "step": "Discover",
  "results": { ... }         // only when status = completed
}
```

### POST /job/{job_id}/cancel
Cancel a running background job (discovery, verification, enrichment).

```bash
curl -X POST http://localhost:8080/job/job_1719700000000/cancel \
  -H "Content-Type: application/json" -d '{}'
```

Response:
```json
{"status": "cancelled"}
```

---

## Website Verification

### POST /verify-websites
Verify whether leads have live websites. Runs as a background job — poll `/job/{job_id}` for progress.

For leads **with** a stored URL: HTTP HEAD then GET to confirm site is alive.  
For leads **without** a URL: Serper search `"[name]" [city] official website` — picks first non-social link.

```bash
curl -X POST http://localhost:8080/verify-websites \
  -H "Content-Type: application/json" \
  -d '{"lead_ids": []}'
```

**Parameters:**
- `lead_ids` — array of lead IDs to verify. Empty array = verify all unverified leads (up to 500).

Response:
```json
{"job_id": "job_1719700001000", "status": "started"}
```

Completed job results:
```json
{
  "has_website": 120,
  "no_website": 52,
  "total": 172,
  "errors": 3
}
```

After verification, each lead has:
- `website_verified: true`
- `has_website: true / false`
- `website: "https://..."` (if found)

---

## People & Email Finder (Free Apollo/Hunter)

### POST /find-people
Free Apollo.io alternative.

```json
{
  "company_name": "Stripe",
  "titles": ["CEO", "Founder", "CTO"],
  "location": "San Francisco"
}
```

### POST /find-emails
Free Hunter.io alternative.

```json
{
  "business_name": "Acme Corp",
  "domain": "acme.com",
  "first_name": "John",
  "last_name": "Doe"
}
```

### POST /find-domain
Guess domain from business name.

```json
{"business_name": "Najmat Lahore Restaurant"}
```

### POST /verify-email
Verify email deliverability (SMTP RCPT TO).

```json
{"email": "info@example.com"}
```

Response includes `syntax_valid`, `domain_resolves`, `has_mx`, `mailbox_exists`, `risk_level`, `details[]`.

---

## SEO Intelligence

### POST /keywords
Keyword research (related, autocomplete, PAA, competitors).

```json
{
  "keyword": "web design services",
  "location": "Dubai"
}
```

### POST /serp
SERP analysis (rankings, local pack, snippets).

```json
{
  "keyword": "best laundry",
  "location": "Dubai"
}
```

### POST /trends
Google Trends data (free implementation).

```json
{"keyword": "AI tools", "geo": "US"}
```

---

## Competitor Intelligence

### POST /competitor
Full competitor analysis (social, rankings, mentions).

```json
{"target": "shopify.com"}
```

### POST /tech-stack
Detect website tech stack (CMS, frameworks, analytics).

```json
{"domain": "shopify.com"}
```

### POST /domain-intel
Full domain analysis (DNS, title, description, tech).

```json
{"domain": "apple.com"}
```

### POST /wayback
Wayback Machine historical snapshots.

```json
{"url": "https://google.com", "limit": 5}
```

### POST /backlinks
Discover backlinks via SERP.

```json
{"url": "https://yourdomain.com"}
```

---

## Other Modules

### POST /social-scout
Find Instagram/TikTok/YouTube profiles in any niche.

```json
{
  "niche": "barber",
  "location": "Dubai",
  "platforms": ["instagram", "tiktok"]
}
```

### POST /ecommerce
Product/niche research.

```json
{
  "query": "wireless earbuds",
  "platform": "amazon"
}
```

---

## Configuration

### GET /config
Get current settings (enrichment provider, image provider, automation toggles).

### POST /config
Update settings. All values are persisted to disk at `/opt/leadgen/config.json`.

```json
{
  "enrichment_strategy": "serper_then_oxylabs",
  "image_provider": "none",
  "auto_score": true,
  "auto_email_copy": false,
  "auto_image": false
}
```

**`enrichment_strategy` values:**
- `serper_only` — fast, Serper only
- `oxylabs_only` — deep scrape, Oxylabs only
- `serper_then_oxylabs` — Serper first, Oxylabs fills missing (recommended)
- `free_only` — Serper + email permutator, no paid scraping

**`image_provider` values:**
- `none` — no image generation (default)
- `replicate` — Replicate FLUX
- `imagine_art` — imagine.art

### GET /api-keys
Get API key status (masked, shows last 4 chars only).

### POST /api-keys/update
Update an API key (persists to disk and memory).

```json
{"key": "here_api_key", "value": "your-here-key-here"}
```

**Valid keys:** `google_api_key`, `serper_key`, `gemini_key`, `claude_key`, `replicate_token`, `imagine_art_key`, `oxylabs_key`, `resend_key`, `from_email`, `from_name`, `here_api_key`.

---

## Outreach

### GET /outreach
List all sent emails with status.

### POST /send-email
Send a custom email via Resend.

```json
{
  "to": "test@example.com",
  "subject": "Hello",
  "body": "Plain text body",
  "html": "<p>HTML body (optional)</p>"
}
```

---

## Stats & Analytics

### GET /stats
Pipeline counters (hot_leads, total, enriched, ready, with_email, cities, etc.).

### GET /stats-chart
Time-series data for charts (leads_per_day, status_breakdown, niche_breakdown, city_breakdown, score_distribution).

---

## Static Files

### GET /
Returns the React dashboard HTML.

### GET /mockups/{filename}
Serves generated mockup images (PNG/JPG/WEBP).

### GET /health
Health check + capability list.

---

## Common Patterns

### Find + Enrich + Score + Send (full pipeline)

```bash
# 1. Discover
curl -X POST http://localhost:8080/search -d '{"query":"barber shops in Manchester UK"}'

# 2. Run full pipeline async
curl -X POST http://localhost:8080/run-pipeline -d '{"provider":"serper_then_oxylabs"}'
# Returns: {"job_id":"job_1234567890"}

# 3. Poll progress
curl http://localhost:8080/job/job_1234567890

# 4. Once complete, list ready leads
curl http://localhost:8080/leads | jq '.leads[] | select(.status == "ready")'

# 5. Send email for a specific lead
curl -X POST http://localhost:8080/lead/UUID_HERE/send
```

### Build Your Own Cron-Job Pipeline

```bash
# Every morning at 6am, search a different niche
0 6 * * 1 curl -X POST http://localhost:8080/search -d '{"query":"restaurants in Dubai"}'
0 6 * * 2 curl -X POST http://localhost:8080/search -d '{"query":"salons in Sharjah"}'

# Every hour, enrich whatever's queued
0 * * * * curl -X POST http://localhost:8080/enrich -d '{}'
```

### Integrate with Zapier / Make.com

Webhook trigger:
- URL: `http://YOUR_SERVER:8080/search`
- Method: POST
- Body: `{"query": "{{trigger_text}}"}`

Then use the response in your Zap.

---

## Error Codes

- `200` — OK
- `400` — Bad request (missing/invalid parameters)
- `401` — Unauthorized (auth endpoints)
- `404` — Not found
- `500` — Server error (check `journalctl -u leadgen-api`)

All errors return JSON:
```json
{"error": "description of what went wrong"}
```

---

## Rate Limits (External APIs Used)

Be mindful of these — they affect what the platform can do:

| API | Free Limit | Used By |
|---|---|---|
| Google Places (New + Classic) | $300 credit | /search, /discover |
| OpenStreetMap Overpass | Unlimited (fair use) | /search (always runs alongside Google) |
| HERE Maps Discover | 250,000 tx/month | /search (when here_api_key set) |
| Serper | 2,500 searches/month | /enrich, /verify-websites, /keywords, /serp, /trends, /find-people |
| Gemini | High free tier | /score, /search (query parsing), /keywords |
| Claude | Pay-per-token | /generate-assets, /regenerate-email |
| Replicate | $0.003/image | /generate-assets (image_provider=replicate) |
| Resend | 3,000 emails/month | /send-email, /lead/{id}/send |

When you hit a limit, the API returns an error in the response body explaining what failed.

---

## Versioning

Current API version: **7.0**

Check `/health` for the version your server is running.

Breaking changes will bump the major version. Backwards-compatible features bump the minor.
