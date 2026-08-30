-- Migration 007: AI research & pain detection (M7)

CREATE TABLE IF NOT EXISTS lead_research (
    lead_id           UUID PRIMARY KEY REFERENCES leads(id) ON DELETE CASCADE,
    status            VARCHAR(30) NOT NULL DEFAULT 'pending',  -- pending|running|completed|failed
    web_findings      JSONB,
    reviews_summary   TEXT,
    tech_stack        TEXT[],
    hiring_signals    TEXT[],
    social_presence   JSONB,
    pain_points       JSONB,    -- [{"pain":..., "evidence":..., "severity":1-5}, ...]
    needs_summary     TEXT,
    recommended_angle TEXT,
    sources           JSONB,
    error             TEXT,
    researched_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_lead_research_status ON lead_research(status);
