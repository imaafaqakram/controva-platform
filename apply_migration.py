import psycopg2

DB = dict(host='127.0.0.1', port=5433, database='leadgen_db', user='leadgen', password='LeadGen_Secure_2024!')

def run_migration():
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    
    with open('server/init.sql', 'r', encoding='utf-8') as f:
        sql = f.read()
        
    print("Applying schema changes...")
    cur.execute(sql)
    conn.commit()
    print("Migration successful.")
    
    cur.close()
    conn.close()

if __name__ == '__main__':
    run_migration()
