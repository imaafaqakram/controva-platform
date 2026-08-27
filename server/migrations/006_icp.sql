-- Migration 006: ICP engine — ideal customer profiles + autonomous discovery (M6)

ALTER TABLE leads ADD COLUMN IF NOT EXISTS icp_id INT;

CREATE TABLE IF NOT EXISTS icp_profiles (
    id             SERIAL PRIMARY KEY,
    name           VARCHAR(200) NOT NULL,
    industries     TEXT NOT NULL DEFAULT '',      -- comma separated: "dental clinics, vet clinics"
    geos           TEXT NOT NULL DEFAULT '',      -- comma separated: "Dubai AE, Abu Dhabi AE"
    keywords       TEXT NOT NULL DEFAULT '',      -- extra search hints
    exclusions     TEXT NOT NULL DEFAULT '',      -- "-franchise, -chain"
    source_mix     VARCHAR(30) NOT NULL DEFAULT 'all',   -- places|osm|here|intent|all
    min_lead_score SMALLINT NOT NULL DEFAULT 60,  -- qualification threshold (v2 score or ai_score*10)
    push_to_crm    BOOLEAN NOT NULL DEFAULT FALSE,
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    last_run_at    TIMESTAMPTZ,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS icp_runs (
    id             SERIAL PRIMARY KEY,
    icp_id         INT REFERENCES icp_profiles(id) ON DELETE CASCADE,
    started_at     TIMESTAMPTZ DEFAULT NOW(),
    finished_at    TIMESTAMPTZ,
    leads_found    INT DEFAULT 0,
    leads_new      INT DEFAULT 0,
    status         VARCHAR(30) DEFAULT 'running',  -- running|completed|failed
    log            TEXT
);

CREATE INDEX IF NOT EXISTS idx_leads_icp ON leads(icp_id);
CREATE INDEX IF NOT EXISTS idx_icp_runs_icp ON icp_runs(icp_id, started_at DESC);
