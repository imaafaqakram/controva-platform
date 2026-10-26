-- Migration 016: multi-company isolation, per-company settings, qualification
-- criteria, data erasure (M15). Mirrors ensure_m14_tables(), ensure_m15_tables()
-- and ensure_data_erasure_table() in leads_api.py, which run this at startup.

-- A business is unique per company, not globally (two client companies can
-- prospect the same business). NULL tenant = legacy/unowned rows, one group.
CREATE UNIQUE INDEX IF NOT EXISTS uq_leads_tenant_place ON leads
    ((COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid)), place_id);
ALTER TABLE leads DROP CONSTRAINT IF EXISTS leads_place_id_key;
CREATE INDEX IF NOT EXISTS idx_leads_place_id ON leads(place_id);

-- Company ownership
ALTER TABLE workflows        ADD COLUMN IF NOT EXISTS tenant_id UUID;
ALTER TABLE research_history ADD COLUMN IF NOT EXISTS tenant_id UUID;
ALTER TABLE sending_domains  ADD COLUMN IF NOT EXISTS tenant_id UUID;   -- NULL = the operator's own
ALTER TABLE crm_connections  ADD COLUMN IF NOT EXISTS tenant_id UUID;   -- NULL = the operator's own
CREATE INDEX IF NOT EXISTS idx_outreach_log_tenant ON outreach_log(tenant_id);

-- Per-company settings: sending identity, legal footer, Calendly (+ webhook
-- token), IMAP reply inbox, branding, digest, admin-set daily send cap
CREATE TABLE IF NOT EXISTS tenant_settings (
    tenant_id   UUID PRIMARY KEY,
    settings    JSONB NOT NULL DEFAULT '{}',
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Per-client qualification criteria on each ICP
ALTER TABLE icp_profiles ADD COLUMN IF NOT EXISTS score_weights JSONB;          -- {icp_fit, pain_severity, intent_signals, quality}
ALTER TABLE icp_profiles ADD COLUMN IF NOT EXISTS require_email BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE icp_profiles ADD COLUMN IF NOT EXISTS require_decision_maker BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE icp_profiles ADD COLUMN IF NOT EXISTS min_rating NUMERIC(2,1) NOT NULL DEFAULT 0;
ALTER TABLE icp_profiles ADD COLUMN IF NOT EXISTS min_reviews INT NOT NULL DEFAULT 0;
ALTER TABLE icp_profiles ADD COLUMN IF NOT EXISTS decision_maker_titles TEXT NOT NULL DEFAULT '';
ALTER TABLE icp_profiles ADD COLUMN IF NOT EXISTS qualification_notes TEXT NOT NULL DEFAULT '';

-- Right-to-erasure audit trail (hash only, never the erased data)
CREATE TABLE IF NOT EXISTS data_erasures (
    id                SERIAL PRIMARY KEY,
    tenant_id         UUID,
    business_hash     VARCHAR(64),
    emails_suppressed INT NOT NULL DEFAULT 0,
    erased_by         VARCHAR(100),
    erased_at         TIMESTAMPTZ DEFAULT NOW()
);
