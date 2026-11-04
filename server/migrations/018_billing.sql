-- Migration 018: Stripe billing and plans (M17). Mirrors ensure_billing_tables()
-- in leads_api.py, which runs this at startup. A plan sets a company's price, its
-- monthly API budget and its seat count; tenant_billing holds each company's
-- subscription as Stripe last reported it; stripe_events dedupes webhook deliveries.
CREATE TABLE IF NOT EXISTS plans (
    id                   SERIAL PRIMARY KEY,
    name                 VARCHAR(100) NOT NULL,
    description          TEXT NOT NULL DEFAULT '',
    price_cents          INT NOT NULL,
    currency             VARCHAR(3) NOT NULL DEFAULT 'usd',
    monthly_spend_limit  NUMERIC(10,2),          -- API budget; NULL = platform default
    max_users            INT,                    -- seats; NULL = unlimited
    stripe_price_id      VARCHAR(100),
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order           INT NOT NULL DEFAULT 0,
    created_at           TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS tenant_billing (
    tenant_id               UUID PRIMARY KEY,
    plan_id                 INT REFERENCES plans(id) ON DELETE SET NULL,
    status                  VARCHAR(30) NOT NULL DEFAULT 'none',   -- none | active | trialing | past_due | canceled | comped | ...
    stripe_customer_id      VARCHAR(100),
    stripe_subscription_id  VARCHAR(100),
    current_period_end      TIMESTAMPTZ,
    cancel_at_period_end    BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS stripe_events (
    event_id     VARCHAR(100) PRIMARY KEY,
    type         VARCHAR(80),
    tenant_id    UUID,
    received_at  TIMESTAMPTZ DEFAULT NOW()
);
