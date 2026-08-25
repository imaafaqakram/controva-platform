-- Migration 004: Outreach compliance & tracking (M3)
-- Unsubscribe/suppression list + per-lead unsubscribe tokens.

ALTER TABLE leads ADD COLUMN IF NOT EXISTS unsub_token VARCHAR(64);

CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_unsub_token ON leads(unsub_token) WHERE unsub_token IS NOT NULL;

-- One row per suppressed address/domain.
-- type: unsubscribe (user clicked) | bounce (hard) | complaint (spam report)
-- When email_domain is set and email is NULL → whole-domain suppression.
CREATE TABLE IF NOT EXISTS unsubscribes (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           VARCHAR(500),
    email_domain    VARCHAR(300),
    lead_id         UUID REFERENCES leads(id) ON DELETE SET NULL,
    type            VARCHAR(30) NOT NULL DEFAULT 'unsubscribe',
    reason          TEXT,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_unsub_email  ON unsubscribes(email);
CREATE INDEX IF NOT EXISTS idx_unsub_domain ON unsubscribes(email_domain);
