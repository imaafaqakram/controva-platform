-- Migration 017: Lead Hunter integration (M16). Mirrors ensure_leadhunter_tables()
-- in leads_api.py, which runs this at startup. Connection settings live in
-- crm_connections (type 'leadhunter'); this table records each event Lead Hunter
-- sent back (deduped on its X-ACL-Event-Id) and what Controva did with it.
CREATE TABLE IF NOT EXISTS leadhunter_events (
    id             SERIAL PRIMARY KEY,
    connection_id  INT REFERENCES crm_connections(id) ON DELETE CASCADE,
    event_id       VARCHAR(80) NOT NULL UNIQUE,
    event_type     VARCHAR(60),
    disposition    VARCHAR(80),
    lead_id        UUID REFERENCES leads(id) ON DELETE SET NULL,
    applied        VARCHAR(40),       -- meeting_booked | no_show | won | lost | do_not_contact | recorded | ignored | unknown_lead
    received_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_leadhunter_events_lead ON leadhunter_events(lead_id, received_at DESC);
