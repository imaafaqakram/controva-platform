# Controva — Client MVP Program (v8)

> Program goal: deliver the client's AI prospecting & qualification brief **and exceed it**,
> without removing anything from the current system. Every existing capability stays;
> each milestone adds a new subsystem on top.
>
> Created: 2026-08-27 · Status: in progress · Owner: Controva LLC

---

## 0. Positioning (what this product now is)

Controva is an **AI lead prospecting and qualification platform**:

1. Client defines their **Ideal Customer Profile (ICP)**
2. System **discovers companies** matching it (multi-source, scheduled, autonomous)
3. Identifies **decision makers**, **enriches** and **verifies** their data
4. **AI-researches each company** — web presence, reviews, tech, hiring signals — and
   detects **pain points and buying signals**
5. **Scores** leads on ICP fit × detected need × intent
6. **Writes personalised messages** that reference the actual discovered pains
7. **Pushes qualified opportunities into the client's CRM**
8. (Phase 2) Runs compliant outreach, follow-ups, reply classification, meeting booking

Everything below M1–M5 (discovery engine, verification, compliance, sequences,
cost tracking) is retained as the foundation these milestones build on.

---

## Milestone map

| # | Milestone | Client requirement it closes | Depends on |
|---|-----------|------------------------------|------------|
| M6 | ICP Engine + Autonomous Discovery | "client defines ICP, system finds companies automatically" | existing discovery |
| M7 | AI Research & Pain Detection | "researches the company, detects needs/pain points" | M6 |
| M8 | Pain-Aware Scoring & Messaging | "scores the leads", "personalised message generation" | M7 |
| M9 | CRM Integration | "sends best opportunities into a CRM" | M8 |
| M10 | Phase-2 Suite + White-Label Polish | outreach / follow-ups / reply classification / booking (client's "later" list) | M8, M9 |

Each milestone ships: DB migration (idempotent, auto-applied at startup) → backend
functions + endpoints → dashboard UI → local regression test → deploy + smoke test →
docs updated (README + API reference). No milestone removes or breaks existing features.

---

## M6 — ICP Engine + Autonomous Discovery

**Goal:** prospecting runs itself. Define once, runs forever.

### Data model (migration 006_icp.sql)
- `icp_profiles`: id, name, industries (text[]), geos (text[]), keywords (text[]),
  exclusions (text[]), source_mix (places|osm|here|intent|all), min_lead_score (int),
  push_to_crm (bool), is_active (bool), last_run_at, created_at
- `icp_runs`: id, icp_id, started_at, finished_at, leads_found, leads_qualified, status, log

### Backend
- CRUD: `GET/POST /icp`, `PUT/DELETE /icp/<id>` (auth required)
- `POST /icp/<id>/run` — one manual run (background job, live log via JOBS)
- **ICP scheduler daemon** (like the sequence scheduler): daily per active profile at
  staggered hours → run discovery per (industry × geo) combination → feed results into
  the standard pipeline (verify websites → enrich+verify emails → research → score)
- CONFIG toggles: `icp_scheduler_enabled` (default true), `icp_daily_cap` (max searches/day)

### UI
- New **ICP page** (nav): profile cards with counts of leads found/qualified, last run,
  Run Now button, create/edit drawer
- Dashboard card: "Autonomous Prospecting — active ICPs, leads found this week"

### Acceptance
- Create ICP "Dental clinics · Dubai + Abu Dhabi" → scheduler discovers, pipelines and
  scores leads within 24h without human touch; manual Run Now works; duplicates
  deduped via existing place_id/phone/domain logic.

---

## M7 — AI Research & Pain Detection

**Goal:** every qualified lead carries a structured, AI-produced research dossier.

### Data model (migration 007_research.sql)
- `lead_research`: lead_id (unique), status, web_findings jsonb, reviews_summary text,
  tech_stack text[], hiring_signals text[], social_presence jsonb, pain_points jsonb
  (array of {pain, evidence, severity 1-5}), needs_summary text, recommended_angle text,
  sources jsonb, researched_at

### Research pipeline (new `research_lead(lead_id)` job)
1. **Web presence**: Crawl4AI scrape of company site (or Serper knowledge panel if none)
2. **Review mining**: search "<name> reviews" + stored rating/review count → Gemini
   extracts recurring complaints (slow service, no booking, outdated site…)
3. **Tech stack**: reuse existing `/tech-stack` intel (attached to the lead now)
4. **Hiring/intent signals**: reuse intent engine (Reddit/Craigslist/boards)
5. **Social footprint**: existing social scout
6. **Gemini synthesis** → structured JSON: pain_points (with evidence + severity),
   needs_summary, recommended_angle ("lead with online booking pitch")

### Backend + UI
- `POST /lead/<id>/research`, `POST /research/queue` (bulk for score≥X), auto-research
  step in ICP flow
- Lead detail: **Research panel** — pains as severity badges, evidence quotes,
  recommended angle, sources
- Pipeline page: "AI Research" card (queue + progress + stats)

### Acceptance
- 20 sample leads → ≥70% produce ≥1 pain point with evidence; research completes
  <90s/lead; old leads without research show "Not researched" cleanly.

---

## M8 — Pain-Aware Scoring & Messaging v2

**Goal:** score = fit × need, messages reference what the research actually found.

### Scoring v2 (`icp_score`)
- Inputs: ICP match (industry/geo/rules), pain severity sum, intent signals present,
  existing quality signals (rating, reviews, size proxies)
- Output: 0–100 composite **with breakdown** (stored jsonb on lead: `icp_score`,
  `score_breakdown`) — keeps legacy `ai_score` untouched

### Messaging v2
- Claude prompt upgraded: consumes pain_points + needs_summary + recommended_angle;
  generates subject/body that reference up to 2 specific pains; fallback to current
  no-website angle when no research exists (nothing breaks)
- Sequence steps 2–3 also consume research (nudge references the pain, final references angle)

### Acceptance
- Same lead, before/after: v2 email names a specific pain with evidence; scores
  differentiate (pain-heavy lead scores above equal-quality no-pain lead).

---

## M9 — CRM Integration

**Goal:** qualified opportunities flow into the client's CRM automatically.

### Data model (migration 008_crm.sql)
- `crm_connections`: id, type (pipedrive|hubspot|webhook), config jsonb (api tokens,
  webhook url+secret, pipeline/stage mapping), is_active
- `crm_push_log`: id, lead_id, connection_id, status (queued|ok|failed), external_id,
  response jsonb, pushed_at, error

### Backend
- `GET/POST /crm/connections`, `PUT/DELETE /crm/connections/<id>`
- `POST /crm/push` {lead_ids | filter: score ≥ N} → transforms lead + contact +
  research summary + score into:
  - **Pipedrive**: organization → person → deal (stage mapped), note with research dossier
  - **HubSpot**: company → contact → deal, note with dossier
  - **Webhook (generic)**: signed JSON payload (Zapier/n8n/custom)
- Auto-push rule on ICP profiles (`push_to_crm` + `min_lead_score`) — M6 tie-in
- Retry queue for failed pushes (scheduler pass), dedupe by lead+connection

### UI
- Settings → **CRM Connections** section (add Pipedrive token / HubSpot token / webhook)
- Leads table: CRM status column (—/✓/✗/retry) + "Push to CRM" bulk action
- Pipeline page card: push stats (sent/failed/last run)

### Acceptance
- Push 10 qualified leads to a Pipedrive sandbox: org+person+deal+note created, re-push
  is a no-op, failure marks ✗ and retries next pass.

---

## M10 — Phase-2 Suite + White-Label Polish

**Goal:** the client's "later" list, already half-built, finished and client-presentable.

1. **Reply classification** — Gemini classifies each reply (interested / objection /
   not interested / OOO / unsubscribe-intent) → sets lead status + one-line digest
   stored; Outreach page filter by classification
2. **Meeting booking** — configurable Calendly URL; sequence step 2/3 CTA includes it;
   Calendly webhook (routed through existing webhook handler pattern) marks lead
   `meeting_booked`
3. **Multi-decision-maker capture** — find_people results stored as additional contacts
   (title-aware); outreach targets best verified contact, others retained
4. **White-label basics** — config: client_brand_name, client_brand_color, footer text
   (compliance footer + dashboard header adopt branding) for agency resale
5. **Daily digest** — n8n/Resend email each morning: new qualified leads, research
   highlights, cost summary (reuses M5 cost stats)
6. **Public API completion** — finish `controva_api.py` v1 surface (leads, research,
   scoring read + webhook events) for client-side integration

### Acceptance
- End-to-end demo: ICP finds company → research finds pain → message references pain →
  reply classified "interested" → Calendly booked → CRM updated. Branded dashboard.

---

## Out of scope (documented deliberately)

- Apollo-scale contact database (no 200M-contact graph) — position as *discovery +
  qualification depth*, not database size
- Native email sending infrastructure beyond Resend/SMTP plans (M1–M4 approach stands)
- Multi-tenant SaaS accounts/login per seat (single-tenant per client deployment)

## Dependencies to procure (client side)

| Item | Needed by | Notes |
|---|---|---|
| Client's target-market answer (SMB local vs B2B) | M6 source mix | changes discovery weighting |
| Pipedrive or HubSpot sandbox/token | M9 | Pipedrive recommended first |
| Calendly URL | M10 | any booking link works |
| Domain + HTTPS (Caddy) | M9/M10 webhooks | already on roadmap |

## Standing rules

1. Nothing gets removed — every milestone is additive; legacy fields/behavior preserved
2. Every migration idempotent; API auto-applies at startup (existing pattern)
3. Every milestone: regression suite run → deploy → smoke test before "done"
4. Cost visibility: any new external API calls get `log_api_usage` hooks (M5 pattern)
5. Docs updated in the same commit as the feature, never after
