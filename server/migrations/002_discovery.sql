-- ============================================================
--  Migration 002: Multi-source Discovery Engine
--  SAFE — additive & idempotent. Mirrors ensure_discovery_tables()
--  in leads_api.py (runtime self-heal), so this is belt-and-suspenders.
-- ============================================================

-- Per (niche, city) search progress. Each "Find More" advances `round`,
-- which widens the radius, adds synonyms, and turns on extra sources.
CREATE TABLE IF NOT EXISTS discovery_state (
    id          SERIAL PRIMARY KEY,
    niche       VARCHAR(200) NOT NULL,
    city        VARCHAR(200) NOT NULL,
    country     VARCHAR(200) NOT NULL DEFAULT '',
    round       INTEGER NOT NULL DEFAULT 0,       -- how deep we've explored
    exhausted   BOOLEAN NOT NULL DEFAULT FALSE,   -- last widening found < 3 new
    total_found INTEGER NOT NULL DEFAULT 0,
    updated_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (niche, city, country)
);

CREATE INDEX IF NOT EXISTS idx_discovery_state_lookup
    ON discovery_state (niche, city, country);

-- Cross-source dedup keys on leads (so the same business found via Google
-- and OpenStreetMap is only stored once).
ALTER TABLE leads ADD COLUMN IF NOT EXISTS phone_norm VARCHAR(20);  -- last 10 digits
ALTER TABLE leads ADD COLUMN IF NOT EXISTS domain     VARCHAR(255); -- registrable domain

CREATE INDEX IF NOT EXISTS idx_leads_phone_norm ON leads(phone_norm);
CREATE INDEX IF NOT EXISTS idx_leads_domain     ON leads(domain);

-- Backfill dedup keys for existing leads where possible (best-effort).
UPDATE leads
SET domain = regexp_replace(
        regexp_replace(lower(website), '^https?://', ''),
        '^www\.', '')
WHERE website IS NOT NULL AND website <> '' AND domain IS NULL;

-- Trim domain to just the host (drop any path) for the backfilled rows.
UPDATE leads
SET domain = split_part(split_part(domain, '/', 1), '?', 1)
WHERE domain IS NOT NULL AND (domain LIKE '%/%' OR domain LIKE '%?%');

UPDATE leads
SET phone_norm = right(regexp_replace(phone, '\D', '', 'g'), 10)
WHERE phone IS NOT NULL AND phone <> '' AND phone_norm IS NULL;

-- Confirm
SELECT 'Migration 002 applied — multi-source discovery ready' AS message;
