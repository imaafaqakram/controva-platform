-- Migration 012: multi-domain sending + outreach automation (M11)
-- Multiple verified sending identities to rotate outbound mail across,
-- plus a link from each sent email back to the domain it went out on
-- (used for per-domain daily caps and bounce/complaint health checks).

CREATE TABLE IF NOT EXISTS sending_domains (
    id SERIAL PRIMARY KEY,
    domain VARCHAR(255) NOT NULL UNIQUE,
    from_email VARCHAR(255) NOT NULL,
    from_name VARCHAR(255) NOT NULL DEFAULT 'Controva',
    daily_cap SMALLINT NOT NULL DEFAULT 20,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    paused_reason TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

ALTER TABLE outreach_log ADD COLUMN IF NOT EXISTS sending_domain_id INTEGER REFERENCES sending_domains(id);
