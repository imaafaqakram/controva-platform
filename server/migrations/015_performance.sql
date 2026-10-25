-- Migration 015: industry templates, campaign offer, sales outcomes & channel benchmarking (M14)
-- Mirrors ensure_m14_tables() in leads_api.py, which also runs this at startup.

-- ICP ownership (per client company) + what that client sells
ALTER TABLE icp_profiles ADD COLUMN IF NOT EXISTS tenant_id UUID;
ALTER TABLE icp_profiles ADD COLUMN IF NOT EXISTS created_by VARCHAR(100);
ALTER TABLE icp_profiles ADD COLUMN IF NOT EXISTS offer TEXT NOT NULL DEFAULT '';
ALTER TABLE icp_profiles ADD COLUMN IF NOT EXISTS industry_template VARCHAR(40);  -- construction_real_estate | banking_insurance | healthcare_clinics
CREATE INDEX IF NOT EXISTS idx_icp_profiles_tenant ON icp_profiles(tenant_id);

-- Sales outcomes per lead
ALTER TABLE leads ADD COLUMN IF NOT EXISTS meeting_attended BOOLEAN;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS deal_stage VARCHAR(20);            -- open | won | lost
ALTER TABLE leads ADD COLUMN IF NOT EXISTS deal_value NUMERIC(12,2);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS deal_closed_at TIMESTAMPTZ;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS outcome_notes TEXT;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS outcome_updated_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_leads_deal_stage ON leads(deal_stage) WHERE deal_stage IS NOT NULL;

-- Hand-entered figures for the client's other lead channels, per period
CREATE TABLE IF NOT EXISTS channel_benchmarks (
    id                SERIAL PRIMARY KEY,
    tenant_id         UUID,
    channel           VARCHAR(30) NOT NULL,    -- meta_ads | google_ads | website | other | prospecting_costs
    label             VARCHAR(120) NOT NULL DEFAULT '',
    period_start      DATE NOT NULL,
    period_end        DATE NOT NULL,
    spend             NUMERIC(12,2) NOT NULL DEFAULT 0,
    leads             INT NOT NULL DEFAULT 0,
    qualified_leads   INT,                     -- NULL = same as leads
    meetings_booked   INT NOT NULL DEFAULT 0,
    meetings_attended INT NOT NULL DEFAULT 0,
    customers         INT NOT NULL DEFAULT 0,
    revenue           NUMERIC(14,2) NOT NULL DEFAULT 0,
    notes             TEXT NOT NULL DEFAULT '',
    created_by        VARCHAR(100),
    created_at        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_channel_benchmarks_tenant ON channel_benchmarks(tenant_id, period_start);
