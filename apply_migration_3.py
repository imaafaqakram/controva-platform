import psycopg2

DB = dict(host='127.0.0.1', port=5433, database='leadgen_db', user='leadgen', password='CHANGE_ME_DB_PASS')

sql = """
-- ── TENANT LEADS — Many-to-many relationship for caching ──────────────────────
CREATE TABLE IF NOT EXISTS tenant_leads (
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    lead_id   UUID REFERENCES leads(id) ON DELETE CASCADE,
    added_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (tenant_id, lead_id)
);
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
