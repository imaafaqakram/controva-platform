-- ============================================================
--  AI Lead Generation System — Database Schema
-- ============================================================

-- Extension for UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For fuzzy text search

-- ── LEADS TABLE — Raw discovered businesses ─────────────────
CREATE TABLE IF NOT EXISTS leads (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    place_id        VARCHAR(255) UNIQUE NOT NULL,  -- Google Places unique ID
    business_name   VARCHAR(500) NOT NULL,
    niche           VARCHAR(200),
    city            VARCHAR(200),
    country         VARCHAR(200),
    address         TEXT,
    phone           VARCHAR(100),
    website         VARCHAR(1000),                  -- NULL = hot lead!
    has_website     BOOLEAN GENERATED ALWAYS AS (website IS NOT NULL AND website != '') STORED,
    latitude        DECIMAL(10, 8),
    longitude       DECIMAL(11, 8),
    google_rating   DECIMAL(2, 1),
    review_count    INTEGER DEFAULT 0,
    ai_score        SMALLINT,                        -- 1-10 from Gemini scoring
    score_reason    TEXT,                            -- Gemini's justification
    status          VARCHAR(50) DEFAULT 'discovered',
                    -- discovered | enriched | scored | ready | approved | sent | replied | closed | rejected
    source          VARCHAR(100) DEFAULT 'google_places',
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ── CONTACTS TABLE — Decision maker data ────────────────────
CREATE TABLE IF NOT EXISTS contacts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id         UUID REFERENCES leads(id) ON DELETE CASCADE,
    first_name      VARCHAR(200),
    last_name       VARCHAR(200),
    full_name       VARCHAR(400),
    job_title       VARCHAR(300),
    email           VARCHAR(500),
    email_verified  BOOLEAN DEFAULT FALSE,
    phone           VARCHAR(100),
    linkedin_url    VARCHAR(1000),
    source          VARCHAR(100),   -- serper | oxylabs | crawl4ai | manual
    confidence      SMALLINT,       -- 1-100 confidence score
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ── ASSETS TABLE — Generated images & email copy ────────────
CREATE TABLE IF NOT EXISTS assets (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id         UUID REFERENCES leads(id) ON DELETE CASCADE,
    asset_type      VARCHAR(50),    -- mockup_image | email_subject | email_body
    content         TEXT,           -- URL for images, text for email copy
    model_used      VARCHAR(100),   -- flux.1-schnell | claude-3-5 | etc
    prompt_used     TEXT,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ── OUTREACH LOG — All emails sent ──────────────────────────
CREATE TABLE IF NOT EXISTS outreach_log (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id         UUID REFERENCES leads(id) ON DELETE CASCADE,
    contact_id      UUID REFERENCES contacts(id) ON DELETE SET NULL,
    email_to        VARCHAR(500) NOT NULL,
    email_subject   VARCHAR(1000),
    email_body      TEXT,
    mockup_url      VARCHAR(2000),
    approved_by     VARCHAR(200) DEFAULT 'operator',
    sent_at         TIMESTAMP WITH TIME ZONE,
    opened_at       TIMESTAMP WITH TIME ZONE,
    replied_at      TIMESTAMP WITH TIME ZONE,
    status          VARCHAR(50) DEFAULT 'draft',  -- draft | approved | sent | opened | replied | bounced
    reply_content   TEXT,
    resend_message_id VARCHAR(500),
    follow_up_due   DATE,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ── DEDUP CACHE TABLE — Prevent double processing ───────────
CREATE TABLE IF NOT EXISTS processed_cache (
    cache_key       VARCHAR(500) PRIMARY KEY,  -- place_id or email hash
    cache_type      VARCHAR(50),               -- place | email | domain
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ── WORKFLOW RUNS — Track n8n workflow executions ───────────
CREATE TABLE IF NOT EXISTS workflow_runs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_name   VARCHAR(200),
    trigger_input   JSONB,
    leads_found     INTEGER DEFAULT 0,
    leads_enriched  INTEGER DEFAULT 0,
    emails_sent     INTEGER DEFAULT 0,
    status          VARCHAR(50) DEFAULT 'running',  -- running | completed | failed
    error_message   TEXT,
    started_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at    TIMESTAMP WITH TIME ZONE
);

-- ── INDEXES for performance ──────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_has_website ON leads(has_website);
CREATE INDEX IF NOT EXISTS idx_leads_ai_score ON leads(ai_score);
CREATE INDEX IF NOT EXISTS idx_leads_city ON leads(city);
CREATE INDEX IF NOT EXISTS idx_leads_niche ON leads(niche);
CREATE INDEX IF NOT EXISTS idx_leads_created ON leads(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_contacts_lead_id ON contacts(lead_id);
CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email);
CREATE INDEX IF NOT EXISTS idx_outreach_status ON outreach_log(status);
CREATE INDEX IF NOT EXISTS idx_outreach_sent ON outreach_log(sent_at DESC);

-- ── AUTO-UPDATE timestamp trigger ───────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER leads_updated_at
    BEFORE UPDATE ON leads
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ── VIEWS for easy CRM querying ──────────────────────────────
CREATE OR REPLACE VIEW hot_leads AS
    SELECT
        l.id, l.business_name, l.niche, l.city, l.phone,
        l.ai_score, l.score_reason, l.status,
        c.full_name, c.email, c.linkedin_url,
        a_img.content AS mockup_url,
        a_subj.content AS email_subject,
        a_body.content AS email_body,
        l.created_at
    FROM leads l
    LEFT JOIN contacts c ON c.lead_id = l.id
    LEFT JOIN assets a_img ON a_img.lead_id = l.id AND a_img.asset_type = 'mockup_image'
    LEFT JOIN assets a_subj ON a_subj.lead_id = l.id AND a_subj.asset_type = 'email_subject'
    LEFT JOIN assets a_body ON a_body.lead_id = l.id AND a_body.asset_type = 'email_body'
    WHERE l.has_website = FALSE
      AND l.ai_score >= 7
    ORDER BY l.ai_score DESC, l.created_at DESC;

CREATE OR REPLACE VIEW pipeline_stats AS
    SELECT
        COUNT(*) FILTER (WHERE status = 'discovered') AS total_discovered,
        COUNT(*) FILTER (WHERE status = 'enriched') AS total_enriched,
        COUNT(*) FILTER (WHERE has_website = FALSE AND ai_score >= 7) AS hot_leads,
        COUNT(*) FILTER (WHERE status = 'sent') AS emails_sent,
        COUNT(*) FILTER (WHERE status = 'replied') AS replies_received,
        ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'replied') /
              NULLIF(COUNT(*) FILTER (WHERE status = 'sent'), 0), 2) AS reply_rate_pct
    FROM leads;

-- ── Seed data — test the connection ─────────────────────────
INSERT INTO processed_cache (cache_key, cache_type)
VALUES ('SCHEMA_INIT_OK', 'system')
ON CONFLICT DO NOTHING;

SELECT 'Database schema created successfully!' AS message;
