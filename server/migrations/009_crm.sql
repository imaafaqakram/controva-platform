-- Migration 009: CRM integration (M9) — Pipedrive + generic signed webhook

CREATE TABLE IF NOT EXISTS crm_connections (
    id          SERIAL PRIMARY KEY,
    type        VARCHAR(30) NOT NULL,          -- pipedrive|webhook
    name        VARCHAR(200) NOT NULL DEFAULT '',
    config      JSONB NOT NULL DEFAULT '{}',   -- {api_token|webhook_url/webhook_secret, pipeline_id, stage_id}
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS crm_push_log (
    id             SERIAL PRIMARY KEY,
    lead_id        UUID REFERENCES leads(id) ON DELETE CASCADE,
    connection_id  INT REFERENCES crm_connections(id) ON DELETE CASCADE,
    status         VARCHAR(20) NOT NULL DEFAULT 'queued',  -- queued|ok|failed
    external_id    VARCHAR(200),
    response       JSONB,
    error          TEXT,
    pushed_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(lead_id, connection_id)
);

CREATE INDEX IF NOT EXISTS idx_crm_push_log_lead ON crm_push_log(lead_id);
