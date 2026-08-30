-- Migration 008: pain-aware scoring v2 (M8) — legacy ai_score untouched

ALTER TABLE leads ADD COLUMN IF NOT EXISTS icp_score SMALLINT;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS score_breakdown JSONB;

CREATE INDEX IF NOT EXISTS idx_leads_icp_score ON leads(icp_score DESC NULLS LAST);
