# API Reference — Controva Intelligence Platform

Complete documentation of all 30+ endpoints.

**Base URL:** `http://YOUR_SERVER_IP:8080`
**Authentication:** Most endpoints are open. For production, add a reverse proxy with HTTP basic auth, or use the `/auth/login` token.
**Content-Type:** `application/json` for all POST requests.

---

## Authentication

### POST /auth/login
Login and get a session token.

```bash
curl -X POST http://localhost:8080/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"ChangeMe_2026!"}'
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
Natural-language search. Best entry point.

```bash
curl -X POST http://localhost:8080/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "barber shops in Manchester UK",
    "filter_mode": "no_website",
    "density": "standard"
  }'
```

**Parameters:**
- `query` (required) — Free-text search
- `filter_mode` — `no_website` (default) / `with_website` / `all`
- `density` — `low` (5 zones) / `standard` (9 zones) / `high` (25 zones)

Response:
```json
{
  "status": "success",
  "parsed": {"niche":"barber","city":"Manchester","country":"GB"},
  "filter_mode": "no_website",
  "density": "standard",
  "total_new_leads": 23,
  "leads": [...]
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
Get pipeline job status, progress, and log.

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
Update settings.

```json
{
  "enrichment_primary": "serper",
  "enrichment_fallback": "oxylabs",
  "image_provider": "imagine_art",
  "auto_score": true,
  "auto_email_copy": true,
  "auto_image": false
}
```

### GET /api-keys
Get API key status (masked, shows last 4 chars only).

### POST /api-keys/update
Update an API key (persists to disk).

```json
{"key": "imagine_art_key", "value": "vk-new-key-here"}
```

Valid keys: `google_api_key`, `serper_key`, `gemini_key`, `claude_key`, `replicate_token`, `imagine_art_key`, `oxylabs_key`, `resend_key`, `from_email`, `from_name`.

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
| Google Places | $300 credit | /search, /discover |
| Serper | 2,500 searches | /enrich, /keywords, /serp, /trends, /find-people, etc. |
| Gemini | High | /score, /search (parsing), /keywords (expansion) |
| Claude | Pay-per-token | /generate-assets, /regenerate-email |
| Replicate | $0.003/image | /generate-assets (when image_provider=replicate) |
| Resend | 3,000 emails/mo | /send-email, /lead/{id}/send |

When you hit a limit, the API returns an error in the response body explaining what failed.

---

## Versioning

Current API version: **5.0**

Check `/health` for the version your server is running.

Breaking changes will bump the major version. Backwards-compatible features bump the minor.
