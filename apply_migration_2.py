import psycopg2

DB = dict(host='127.0.0.1', port=5433, database='leadgen_db', user='leadgen', password='CHANGE_ME_DB_PASS')

sql = """
CREATE TABLE IF NOT EXISTS tenants (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(200) NOT NULL,
    plan        VARCHAR(50) DEFAULT 'starter',
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id     UUID REFERENCES tenants(id) ON DELETE CASCADE,
    email         VARCHAR(300) UNIQUE NOT NULL,
    password_hash VARCHAR(200) NOT NULL,
    role          VARCHAR(20) DEFAULT 'viewer',
    is_active     BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sessions (
    token       VARCHAR(64) PRIMARY KEY,
    user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
    tenant_id   UUID REFERENCES tenants(id) ON DELETE CASCADE,
    expires_at  TIMESTAMP WITH TIME ZONE,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tenant_search_history (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id   UUID REFERENCES tenants(id) ON DELETE CASCADE,
    user_id     UUID REFERENCES users(id),
    query_text  VARCHAR(300) NOT NULL,
    niche       VARCHAR(200),
    city        VARCHAR(200),
    lead_count  INTEGER DEFAULT 0,
    served_from VARCHAR(20) DEFAULT 'live',
    searched_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS searched_tiles (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    niche       VARCHAR(200) NOT NULL,
    city        VARCHAR(200) NOT NULL,
    lat         DECIMAL(10,8),
    lng         DECIMAL(11,8),
    radius_m    INTEGER,
    lead_count  INTEGER DEFAULT 0,
    searched_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS credit_usage (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id   UUID REFERENCES tenants(id),
    event_type  VARCHAR(50),
    credits     INTEGER DEFAULT 1,
    saved       BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE leads ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL;
ALTER TABLE outreach_log ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL;

-- Create default tenant and user so the app still works for the current owner
INSERT INTO tenants (id, name, plan) VALUES ('00000000-0000-0000-0000-000000000001', 'Controva LLC', 'enterprise') ON CONFLICT DO NOTHING;
"""

def run_migration():
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    print("Applying schema changes...")
    cur.execute(sql)
    conn.commit()
    print("Migration successful.")
    cur.close()
    conn.close()

if __name__ == '__main__':
    run_migration()
