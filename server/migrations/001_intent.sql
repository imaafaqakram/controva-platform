-- ============================================================
--  Migration 001: Intent Engine
--  SAFE — additive only, won't affect existing leads/data
-- ============================================================

-- Add lead_type to existing leads table
-- NULL = legacy business lead (default behavior preserved)
-- 'demand' = posted that they need a service (buyer intent)
-- 'supply' = offers/provides a service (seller intent)
ALTER TABLE leads ADD COLUMN IF NOT EXISTS lead_type VARCHAR(20);

-- New table: raw intent signals discovered via search dorks
CREATE TABLE IF NOT EXISTS intent_signals (
    id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id            UUID REFERENCES leads(id) ON DELETE CASCADE,
    direction          VARCHAR(20) NOT NULL,    -- 'demand' | 'supply'
    source             VARCHAR(50),             -- linkedin_jobs | reddit_forhire | hn_hiring | ...
    source_url         TEXT,
    raw_snippet        TEXT,
    posted_at          TIMESTAMP WITH TIME ZONE,
    confidence         SMALLINT DEFAULT 0,      -- 0-100 from Gemini classifier
    role_or_service    VARCHAR(300),
    location_hint      VARCHAR(200),
    contact_hint       TEXT,                    -- email/handle extracted by AI
    is_active          BOOLEAN DEFAULT TRUE,
    raw_classification JSONB,                   -- full Gemini response for debugging
    created_at         TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_intent_lead_id     ON intent_signals(lead_id);
CREATE INDEX IF NOT EXISTS idx_intent_direction   ON intent_signals(direction);
CREATE INDEX IF NOT EXISTS idx_intent_confidence  ON intent_signals(confidence DESC);
CREATE INDEX IF NOT EXISTS idx_intent_active      ON intent_signals(is_active);
CREATE INDEX IF NOT EXISTS idx_leads_type         ON leads(lead_type);

-- Confirm
SELECT 'Migration 001 applied — intent engine ready' AS message;
