# Controva Platform — Improvement Roadmap & Milestones

> Created: August 2026 · Based on full code review vs Apollo / Hunter / Clay
> Track progress by checking boxes. Do not reorder phases — each one depends on the one before it.

---

## The Golden Rule

**Do not send any cold outreach emails until Milestone 3 (Verification Pipeline) is complete.**
Every email sent to an unverified address damages your sender reputation — and reputation is much
harder to repair than to lose.

---

## Milestone Summary

| # | Milestone | Phase | Target | Success Measure |
|---|-----------|-------|--------|-----------------|
| M1 | Security Lockdown | 1 — This week | Days 1–7 | No valid secrets in repo; login rejects bad credentials; HTTPS live |
| M2 | Email Verification Pipeline | 2 — Weeks 2–3 | Days 8–14 | 100% of saved emails carry a verification status |
| M3 | Compliance & Tracking | 2 — Weeks 3–4 | Days 15–21 | Unsubscribe works; opens/bounces appear in dashboard for real |
| M4 | Outreach Sequences | 3 — Month 2 | Weeks 5–8 | A lead can receive 3 automated touches over 8 days |
| M5 | Platform Maturity | 4 — Ongoing | Week 9+ | One frontend, modular backend, cost per search visible |

---

# Phase 1 — Security Lockdown (this week)

**Goal:** Nobody who finds the GitHub repo can access your server, spend your API credits, or send email as you.

### 1.1 Rotate every leaked key (Day 1 — do this before touching any code)

Every one of these is live in the public repo (`server/leads_api.py` + docs). Rotating makes the
leaked copies worthless, which also solves the "secrets in git history" problem.

- [ ] **Anthropic Claude key** (line 31) — console.anthropic.com → revoke old, create new
- [ ] **Resend key** (line 4767) — dashboard.resend.com → revoke + recreate. Highest urgency: this one sends email *as your company*
- [ ] **Google Cloud key** (line 28, Places/Geocoding) — console.cloud.google.com → Credentials → delete old key, create new with API restrictions (Places API + Geocoding only) and an application-restriction if possible
- [ ] **Gemini key** (line 30) — aistudio.google.com → delete + regenerate
- [ ] **Serper key** (line 29) — serper.dev → regenerate
- [ ] **Oxylabs key** (line 34) — regenerate from dashboard
- [ ] **Replicate token** (line 32) — replicate.com → account → API tokens → regenerate
- [ ] **Public API master secret** `the old master secret` (`controva_api.py`) — replace with a long random string via env var
- [ ] **PostgreSQL password** `the old PostgreSQL password` — change in docker-compose.yml, both API files, and inside the DB (`ALTER USER`)
- [ ] **Dashboard login** `the old dashboard login` — pick a real password (use a password manager)

### 1.2 Remove secrets from the code (Day 2)

- [ ] Delete all hardcoded key values in `server/leads_api.py` lines 28–56 and 4767–4769 — replace with empty strings; `load_config()` already reads `config.json`, so the fallbacks are the only leak
- [ ] Same for `controva_api.py` (DB password, master secret)
- [ ] Scrub the docs: remove server IP `YOUR_SERVER_IP`, dashboard credentials, and n8n webhook IP (`YOUR_N8N_HOST`) from `README.md`, `PLATFORM_OVERVIEW.md`, `deploy.env.example`, and any other file — search the whole repo for `YOUR_SERVER_IP` and `ChangeMe`
- [ ] Put new keys ONLY in `/opt/leadgen/config.json` on the server (never commit) — `server/config.json.template` already shows the right shape
- [ ] Commit + push the cleaned files

### 1.3 Fix the broken login (Day 2)

- [ ] `leads_api.py` around line 5336: the `/auth/login` route accepts **any** username + password (`pwd_match = (password in valid_pwds) or (username and password)`). Rewrite it to use the existing `auth_login()` function (line 4739) which checks the salted hash properly
- [ ] Add simple brute-force protection: after 5 failed logins from an IP, block for 15 minutes (an in-memory dict is fine at your scale)
- [ ] Test: wrong password → 401. Correct password → token. Random password → 401

### 1.4 HTTPS in front of the dashboard (Day 3–4)

- [ ] Point a domain (or subdomain like `app.controvallc.com`) at `YOUR_SERVER_IP`
- [ ] Install **Caddy** on the VPS (easiest option — automatic Let's Encrypt certificates):
      ```
      apt install caddy
      # /etc/caddy/Caddyfile:
      #   app.controvallc.com {
      #       reverse_proxy localhost:8080
      #   }
      ```
- [ ] Firewall: close port 8080 to the outside (`ufw deny 8080`), keep 80/443 open — dashboard only reachable via HTTPS
- [ ] Do the same for the public API on 8081 if you're using it
- [ ] Update `deploy.py` / GitHub Actions if they reference the IP directly

### 1.5 Session persistence (Day 5 — small but important)

- [ ] `ACTIVE_TOKENS` (line 4734) lives in memory — every server restart logs you out and kills running jobs' auth. Store sessions in the existing Postgres `sessions` table instead
- [ ] Background enrichment jobs also die silently on restart — at minimum, log job state to `workflow_runs` so you can see what was interrupted

**✅ M1 done when:** old keys are dead (test one), `git grep` finds no secrets or server IPs, bad login is rejected, and `https://app.controvallc.com` loads with a padlock.

---

# Phase 2 — Deliverability Foundation (weeks 2–4)

**Goal:** Every email in your database is verified before it's saved, every send is legally compliant, and open/bounce stats are real numbers instead of dead UI.

## Milestone 2 — Email Verification Pipeline (week 2)

The codebase already has `verify_email()` (`leads_api.py:3789`) with DNS/MX/SMTP checks — it's just never called by the pipeline. Wire it in.

- [ ] **Fix portability:** `verify_email()` shells out to `dig`, which doesn't exist on Windows (your local machine). Replace with the `dnspython` package (`pip install dnspython`, `dns.resolver.resolve(domain, 'MX')`) — works everywhere
- [ ] **New DB columns on `contacts`:** `email_status` (`deliverable` / `risky` / `undeliverable` / `unknown`), `email_verified_at` timestamp. Add to `init.sql` and a migration `003_email_verification.sql`
- [ ] **Verify inside the pipeline:** in `save_enrichment()` (line 2052), run verification on every email before saving; store the status; never save an email marked `undeliverable`
- [ ] **Kill the domain guesser:** `enrich_with_email_permutator()` (line 1975) invents domains like `businessname.com` and calls them verified. Change it to only permute (`first@`, `first.last@`…) on domains you actually scraped from that business's own website/social pages — never on a guessed domain
- [ ] **Catch-all detection:** during SMTP check, if the server accepts a random address like `zzqq-test-9917@domain`, mark the domain catch-all → all its emails become `risky`, never `deliverable`
- [ ] **Role-account flag:** mark `info@`, `contact@`, `hello@`, `admin@` as `role` — allowed, but scored lower for outreach
- [ ] **Re-verify on schedule:** emails go stale. Add a check — if `email_verified_at` older than 60 days and lead not yet contacted, re-verify on next pipeline run
- [ ] **UI:** show the verification badge (✅ green / ⚠️ yellow / ❌ red) in the Leads table and Outreach review, and default the Outreach list to `deliverable` only
- [ ] Optional but recommended: sign up for a cheap verifier API (Reoon or MillionVerifier ≈ $1 per 1,000 emails) as a fallback for domains where your own SMTP check is inconclusive

**✅ M2 done when:** you run enrichment on fresh leads and 100% of saved contacts have an `email_status`, and sending is blocked for anything not `deliverable`/`risky`.

## Milestone 3 — Compliance & Real Tracking (weeks 3–4)

- [ ] **Unsubscribe system:**
  - [x] New table `unsubscribes` (email, lead_id, unsubscribed_at) + a per-lead random token stored on the lead
  - [x] New public endpoint `GET /u/<token>` — records the unsubscribe, shows a plain "You've been removed" page. No login required
  - [x] `send_email_via_resend()` always appends a footer: unsubscribe link + your physical business address + company name (CAN-SPAM requirement; GDPR needs this too)
  - [x] Before sending, check the suppression list — hard block if the address (or the whole domain) unsubscribed, bounced, or complained before
- [x] **Resend webhook endpoint** (`POST /webhook/resend`):
  - [x] Verify the Resend signature header
  - [x] Handle `email.delivered` → outreach_log status; `email.opened` → finally set `opened_at` (currently *never* written by any code); `email.bounced` → mark contact `undeliverable` + add to suppression; `email.complained` (spam report) → suppression immediately, and pause sending for the day if you get 2+ complaints
  - [ ] Register the webhook URL in the Resend dashboard (user action — needs real domain)
- [x] **Reply tracking (lightweight version):** set up a dedicated reply address (e.g. `reply@controvallc.com`) and check it via IMAP on a schedule — match replies to `outreach_log` by sender + subject → set `replied_at`, lead status → `replied`
- [ ] **Dashboard honesty pass:** until tracking is live, the "opened/replied" charts show zeros — fine. After M3 they should reflect webhook/IMAP data. Verify with a test send to your own Gmail: open it, confirm the dashboard registers the open
- [x] **Sending throttle (interim):** cap `send_lead_email` at 30 sends/hour and 100/day (config values) — protects the domain until real sequences exist in Phase 3

**✅ M3 done when:** a test send to your own inbox shows the unsubscribe footer, clicking it blocks future sends to that address, opening the email updates the dashboard, and a fake bounced address lands on the suppression list.

---

# Phase 3 — Outreach Engine (month 2)

**Goal:** Turn one-shot sends into automated multi-touch sequences — the single biggest reply-rate lever (60–80% of replies come from follow-ups 2–4).

## Milestone 4 — Sequences & Sending Infrastructure (weeks 5–8)

### 4.1 Sequence data model + engine (weeks 5–6)

- [x] Tables: `sequences` (name, status), `sequence_steps` (sequence_id, step_number, delay_days, email_variant), `enrollments` (lead_id, sequence_id, current_step, next_send_at, status)
- [x] Enrollment: from the Outreach page, enroll approved leads into a sequence (default starter: Day 0 initial pitch → Day 3 short nudge referencing the mockup → Day 8 final "should I close the file?" note)
- [x] Step variants: Claude already writes the step-1 email; add prompts for follow-ups (shorter, reference the mockup, one question). Store per-step so regeneration works
- [x] **A scheduler thread** runs every 10 minutes: picks due enrollments (`next_send_at` passed, lead not replied/unsubscribed), verifies the contact is still `deliverable`, sends, advances the step
- [x] **Auto-exit rules:** stop the sequence instantly on reply, unsubscribe, or bounce (all detectable thanks to M3)
- [x] UI: sequence card on Outreach page + per-lead timeline showing which steps sent/opened/clicked

### 4.2 Real sending infrastructure (weeks 7–8)

Resend's terms restrict unsolicited cold email — the account can be banned. Cold volume belongs on real mailboxes.

- [ ] Set up 2–3 real sending mailboxes (Google Workspace aliases on controvallc.com, e.g. `afaq@`, `hello@`, `team@`)
- [ ] **Mailbox rotation:** round-robin sends across mailboxes so no single box exceeds ~30/day
- [ ] **Warmup schedule (critical, non-negotiable):** weeks 1–2 send only 5–10 emails/day per mailbox, gradually raise to 30/day. During warmup keep Resend for nothing cold — transactional only
- [ ] Switch `send_email_via_resend()` internals to SMTP for cold mail (Python `smtplib`) while keeping the same function signature — the rest of the code doesn't change
- [ ] Set SPF, DKIM, and DMARC records for controvallc.com (Google Workspace guides walk you through it; DMARC starts at `p=none`, monitor, tighten later). Verify with mail-tester.com — target 9/10+
- [ ] Optional accelerator: an external warmup tool or Instantly/Smartlead for volume, keeping Controva as the lead *source* that pushes to them via your n8n integration — acceptable shortcut if SMTP gets painful

**✅ M4 done when:** one test lead goes Day 0 → Day 3 → Day 8 through three touches automatically, a reply mid-sequence stops it, and all three mailboxes pass mail-tester ≥ 9/10.

---

# Phase 4 — Platform Maturity (week 9+, ongoing)

**Goal:** Faster, safer development and visibility into costs. No deadline pressure — pick items between outreach campaigns.

## Milestone 5 — Consolidate & Instrument

### 5.1 Pick ONE frontend (decision first — 1 day)

- [x] **Cloudscape React rewrite removed** (2026-08-27 — preserved in git history; dashboard.html is the one frontend) (`frontend/`). It's ~30% done, half the pages are placeholders, and its login was the insecure one. `dashboard.html` works and users know it. Delete or archive the folder to remove confusion, revisit only if you need multi-user accounts later

### 5.2 Split the backend (weeks 9–10, incremental)

- [ ] Break `leads_api.py` (6,000 lines) into modules *without* changing behavior:
      `config.py`, `db.py`, `auth.py`, `discovery.py` (Places/OSM/HERE/tiles), `enrichment.py` (Serper/Oxylabs/verify), `scoring.py`, `outreach.py` (sequences/sending/webhooks), `research.py` (SEO/competitor/ecommerce), `routes.py`
- [ ] Optional after the split: move to Flask or FastAPI for proper routing + validation. Stdlib HTTPServer is fine at current scale; don't let this block Phase 3 work
- [x] Smoke test added to deploy.yml (health, auth-gate 401, bad-login 401, dashboard HTML): `/health`, login success + failure, one search with a mocked provider — catches "deploy broke prod" instantly
- [x] Auth consolidated in M1 (DB-backed auth_users + auth_sessions) (AUTH_USERS vs the users/sessions tables) into one

### 5.3 Cost tracking (week 11 — pays for itself)

- [x] `api_usage` table + logging in every paid provider call: provider, endpoint, cost_estimate, timestamp — log inside each provider wrapper (Serper search, Places call, Claude/Gemini tokens, Replicate image)
- [x] Dashboard API-spend widget with budget bar + 80% warning + per-lead cost, and cost per discovered lead
- [x] Budget alert in widget (cost_budget_monthly in config, default $50) (email yourself when projected spend crosses a threshold)

**✅ M5 done when:** the repo has one frontend, backend logic lives in ≤500-line modules, a deploy that breaks login gets caught by CI, and you can answer "what did this search cost me?" from the dashboard.

---

## Standing rules while executing this plan

1. **No cold sends until M3 is done.** Test sends to your own addresses are fine.
2. **One phase at a time.** Every phase's milestone gates the next.
3. **Commit after every checkbox or two** — small commits make breakages obvious.
4. **Deploy via your existing flow** (`python deploy.py api`) and check `journalctl -u leadgen-api -f` after each deploy.
5. Rotate again if any secret ever touches a commit: keys are cheap, incidents are not.

## Realistic effort budget (solo, part-time)

| Phase | Calendar | Focused hours |
|-------|----------|---------------|
| 1 — Security | 1 week | 8–12 h |
| 2 — Deliverability | 3 weeks | 25–35 h |
| 3 — Outreach engine | 4 weeks + 2 weeks mailbox warmup | 30–40 h |
| 4 — Maturity | ongoing | 20–30 h |

If you only have time for part of this plan: Phases 1 and 2 are non-negotiable.
Phase 3 roughly doubles reply rates; Phase 4 speeds up everything that comes after.
