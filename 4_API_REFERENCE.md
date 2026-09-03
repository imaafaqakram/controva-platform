# API Reference — Controva Intelligence Platform

Complete documentation of all 45+ endpoints.

**Base URL:** `http://YOUR_SERVER_IP:8080`
**Authentication:** Most endpoints are open. For production, add a reverse proxy with HTTP basic auth, or use the `/auth/login` token.
**Content-Type:** `application/json` for all POST requests.
**Version:** 8.3

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

Response includes `id`, `business_name`, `niche`, `city`, `country`, `phone`, `address`, `website`, `ai_score`, `icp_score` *(M8)*, `status`, `owner_name`, `owner_email`, `linkedin_url`, `mockup_url`, `email_subject`, `email_body`, `date_found`, `lead_type`.

### GET /leads.csv
Download all leads as CSV.

```bash
curl -O http://localhost:8080/leads.csv
```

### GET /lead/{id}
Get full details of a specific lead — includes `icp_score`/`score_breakdown` *(M8)*,
`meeting_booked` *(M10)*, and a `research` object *(M7)*: `{status, pain_points,
needs_summary, recommended_angle, reviews_summary, tech_stack, sources, researched_at}`.

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

## AI Research & Pain Detection (M7)

### POST /lead/{id}/research
Build (or rebuild) the AI research dossier for one lead. Background job — poll `/job/{job_id}`.

```bash
curl -X POST http://localhost:8080/lead/UUID_HERE/research -d '{}'
```

### POST /research/queue
Bulk-research every lead at or above `min_score` that hasn't been researched yet (up to 500).

```json
{"min_score": 0}
```

Research results (pain_points, needs_summary, recommended_angle, tech_stack, sources) are
returned as a `research` object inside `GET /lead/{id}`.

---

## Pain-Aware Scoring v2 (M8)

No dedicated endpoint — `icp_score` and `score_breakdown` are computed automatically at the
end of `/lead/{id}/research` and appear in `GET /lead/{id}` and `GET /leads` alongside the
legacy `ai_score`.

---

## CRM Integration (M9)

### GET /crm/connections
List configured CRM connections (secrets masked).

### POST /crm/connections/save
Create or update a connection. Omit `id` to create.

```json
{"type": "pipedrive", "name": "Main Pipedrive",
 "config": {"api_token": "...", "pipeline_id": "1", "stage_id": "2"}, "is_active": true}
```

```json
{"type": "webhook", "name": "Zapier",
 "config": {"webhook_url": "https://hooks.zapier.com/...", "webhook_secret": "optional"}}
```

### POST /crm/connections/{id}/delete
Remove a connection.

### POST /crm/push
Push leads to a connection. Omit `lead_ids` to push everything at or above `min_score`.

```json
{"connection_id": 1, "lead_ids": ["uuid1", "uuid2"]}
```
```json
{"connection_id": 1, "min_score": 60}
```

Returns a `job_id` — poll `/job/{job_id}`.

---

## Phase-2 Suite (M10)

### POST /webhook/calendly
Point your Calendly webhook subscription here. Unauthenticated (same trust model as
`/webhook/resend`). Matches the invitee email against `outreach_log`/`contacts` and sets
`leads.meeting_booked`.

Reply classification has no dedicated endpoint — it runs automatically inside the existing
**Check for Replies** (IMAP) job and appears as `reply_classification`/`reply_digest` on
`GET /outreach`.

White-label and daily-digest settings (`client_brand_name`, `client_brand_color`,
`client_footer_text`, `calendly_url`, `daily_digest_enabled`, `digest_recipient_email`,
`multi_decision_maker_capture`) are read/written via the existing `GET`/`POST /config` —
see [Configuration](#configuration) below.

---

## Multi-Domain Sending + Outreach Automation (M11)

### GET /sending-domains
List configured sending domains with today's/7-day send stats. Admin only.

### POST /sending-domains/save
Create or update a sending domain. Omit `id` to create. `from_email`'s domain must match
`domain`. The domain must already be verified in your Resend account (Resend supplies the
SPF/DKIM records to add at that domain's DNS host — this endpoint doesn't do that part).

```json
{"domain": "mail-two.com", "from_email": "hello@mail-two.com", "from_name": "Controva",
 "daily_cap": 20, "is_active": true}
```

### POST /sending-domains/{id}/delete
Remove a sending domain. Admin only.

Outreach sends (initial send and sequence follow-ups) automatically rotate across every
active, under-cap domain configured here — no domain configured means everything still
goes out via the single global `from_email`/`from_name` (Configuration). Any domain with
≥10 sends and a ≥5% bounce+complaint rate in the trailing 7 days is paused automatically.

Automation mode (`outreach_automation_mode`: `off` | `daily_approval` | `full_auto`) is
read/written via the existing `GET`/`POST /config` — see [Configuration](#configuration).
`full_auto` runs a background loop that sends `ready` leads through the same function
(and every gate — verification, suppression, throttle, domain caps) a manual "Send Email"
click uses.

---

## Activity Log (M12)

### GET /admin/activity
Paginated, filterable view over `api_usage` — who called which API, when, and at what cost.
Admin only.

Query params (all optional): `days` (`1`/`7`/`30`/`all`, default `30`), `username` (exact
match), `provider` (exact match, e.g. `claude`), `limit` (default 100, max 500), `offset`.

```
GET /admin/activity?days=7&provider=claude&limit=50
```

Response:
```json
{
  "rows": [{"time": "2026-09-03T03:16:10Z", "username": "admin", "provider": "serper",
            "endpoint": "search", "cost": 0.001, "meta": "signs Dubai"}],
  "total_count": 42, "total_cost": 1.23,
  "by_provider": [{"provider": "claude", "count": 10, "cost": 0.9}],
  "by_user": [{"username": "admin", "count": 30, "cost": 1.0}],
  "limit": 100, "offset": 0
}
```

`username` is `"(system)"` for calls made by a background scheduler (ICP/digest/sequence
loops) rather than a logged-in user's click. Attribution is automatic — every existing
`log_api_usage()` call site picks it up with no changes needed at the call site itself.

---

## Workflow Builder + N8N (M13)

### GET /workflows
List saved workflows: `id`, `name`, `graph` ({nodes, edges}), `is_active`, `created_by`,
`updated_at`, and the most recent run's `last_run_status`/`last_run_at`.

### POST /workflows/save
Create or update a workflow. Omit `id` to create.

```json
{"id": null, "name": "Signage prospecting", "graph": {
  "nodes": [{"id": "n1", "type": "search", "x": 40, "y": 40, "config": {"niche": "signage", "city": "Chicago"}},
            {"id": "n2", "type": "send_email", "x": 300, "y": 40, "config": {"domain_id": ""}}],
  "edges": [{"id": "e1", "source": "n1", "target": "n2"}]
}}
```

Node `type` is one of `search`, `enrich`, `score`, `filter_score`, `generate_assets`,
`send_email` — each takes the config shape shown in the dashboard's node config panel.
`send_email`'s `domain_id` is optional; blank/omitted means auto-rotate across active sending
domains (same as a manual send), same as M11.

### POST /workflows/{id}/delete
Remove a workflow (cascades to its run history).

### POST /workflows/run
Executes the saved graph as a DAG (topological order, so branches and fan-in both work) —
each node acts only on the lead ids that flowed to it from its predecessor node(s), not on
every matching lead platform-wide. Returns a `job_id` — poll `/job-status?job_id=...` same as
any other background job (ICP runs, discovery, etc.).

```json
{"id": 1}
```

### GET /n8n/workflows
Read-only proxy to your n8n instance's `GET /api/v1/workflows` (requires `n8n_url` +
`n8n_api_key` set in Settings → API Keys). Admin only. Returns `{workflows: [...], configured,
n8n_url}` — each workflow has `id`, `name`, `active`, `updated_at`. n8n itself is never
modified by this endpoint.

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
Update one API key (persists to disk and memory).

```json
{"key": "here_api_key", "value": "your-here-key-here"}
```

**Valid keys:** `google_api_key`, `serper_key`, `gemini_key`, `claude_key`, `replicate_token`, `imagine_art_key`, `oxylabs_key`, `resend_key`, `from_email`, `from_name`, `here_api_key`, `scrapingbee_key`, `zenrows_key`, `scrapingdog_key`, `firecrawl_key`, `ebay_client_id`, `ebay_client_secret`, `reddit_client_id`, `reddit_client_secret`, `freelancer_api_key`, `millionverifier_key`, `public_base_url`, `company_name`, `company_address`, `resend_webhook_secret`, `imap_host`, `imap_user`, `imap_pass`.

### POST /api-keys/bulk-update
Update many keys in one call — powers the Settings "Bulk import" (upload/paste a `.env` or
JSON file instead of setting 25+ fields one at a time). Blank values in `pairs` are ignored
(never wipes a key it doesn't mention); names not in the valid-keys list above are reported
back in `skipped` rather than silently dropped. Persists once, admin only.

```json
{"pairs": {"GOOGLE_API_KEY": "AIza...", "serper_key": "abc123"}}
```

Response: `{"success": true, "updated": ["google_api_key", "serper_key"], "skipped": []}`

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

Current API version: **8.3** — adds AI research (M7), pain-aware scoring (M8), CRM push
(M9), the phase-2 suite (M10), multi-domain sending + outreach automation (M11), the
admin activity log (M12), and the visual workflow builder + n8n panel (M13). Fully
backwards-compatible with 7.0 clients — all new fields are additive.

Check `/health` for the version your server is running.

Breaking changes will bump the major version. Backwards-compatible features bump the minor.
