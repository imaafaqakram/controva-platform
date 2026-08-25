#!/usr/bin/env python3
"""
Controva API Key Manager CLI
============================
Generate, list, and revoke API keys for n8n, Zapier, Make, and external scripts.

Usage:
  python server/manage_keys.py create --name "n8n-automation" --scopes read,write
  python server/manage_keys.py create --name "admin-key" --scopes admin
  python server/manage_keys.py list
  python server/manage_keys.py revoke <KEY_ID_OR_PREFIX>
"""

import sys
import os
import argparse
import secrets
import hashlib
import uuid
import time
import json

# Try to import psycopg2 for DB mode
try:
    import psycopg2
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

DB_CONFIG = dict(
    host     = os.environ.get('DB_HOST', '127.0.0.1'),
    port     = int(os.environ.get('DB_PORT', 5433)),
    database = os.environ.get('DB_NAME', 'leadgen_db'),
    user     = os.environ.get('DB_USER', 'leadgen'),
    password = os.environ.get('DB_PASS', ''),
    connect_timeout = 2,
)

KEY_FILE = os.path.join(os.path.dirname(__file__), 'api_keys.json')

def load_file_keys():
    if os.path.exists(KEY_FILE):
        try:
            with open(KEY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_file_keys(keys):
    with open(KEY_FILE, 'w', encoding='utf-8') as f:
        json.dump(keys, f, indent=2, default=str)

def get_db():
    if not HAS_PSYCOPG2:
        return None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception:
        return None

def create_key(name, scopes_list):
    raw_key = 'ctrv_' + secrets.token_urlsafe(32)
    key_prefix = raw_key[:12]
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_id = str(uuid.uuid4())
    created_at = time.strftime('%Y-%m-%dT%H:%M:%SZ')

    # Normalize scopes
    if 'admin' in scopes_list:
        scopes_list = ['read', 'write', 'admin']
    scopes = list(set(scopes_list))

    # 1. Try DB
    db_saved = False
    conn = get_db()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    key_hash      TEXT UNIQUE NOT NULL,
                    key_prefix    VARCHAR(16) NOT NULL,
                    name          VARCHAR(200),
                    scopes        TEXT[]  DEFAULT ARRAY['read'],
                    is_active     BOOLEAN DEFAULT TRUE,
                    last_used     TIMESTAMP WITH TIME ZONE,
                    request_count BIGINT  DEFAULT 0,
                    created_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
            cur.execute("""
                INSERT INTO api_keys (id, key_hash, key_prefix, name, scopes, is_active)
                VALUES (%s, %s, %s, %s, %s, TRUE)
            """, (key_id, key_hash, key_prefix, name, scopes))
            conn.commit()
            cur.close()
            conn.close()
            db_saved = True
        except Exception as e:
            pass

    # 2. Always persist to JSON file as well
    keys = load_file_keys()
    keys.append({
        'id': key_id,
        'key_hash': key_hash,
        'key_prefix': key_prefix,
        'name': name,
        'scopes': scopes,
        'is_active': True,
        'created_at': created_at
    })
    save_file_keys(keys)

    print("\n" + "=" * 64)
    print("  CONTROVA API KEY GENERATED SUCCESSFULLY")
    print("=" * 64)
    print(f"  Name       : {name}")
    print(f"  ID         : {key_id}")
    print(f"  Scopes     : {', '.join(scopes)}")
    print(f"  Storage    : {'PostgreSQL + JSON Backup' if db_saved else 'api_keys.json (File)'}")
    print("-" * 64)
    print(f"  API KEY    : {raw_key}")
    print("-" * 64)
    print("  [!] Save this key now! It will not be shown in full again.")
    print("\n  Example HTTP Header for n8n / Curl:")
    print(f"  X-API-Key: {raw_key}")
    print("=" * 64 + "\n")
    return raw_key

def list_keys():
    print("\n" + "=" * 80)
    print(f"  {'NAME':<20} {'PREFIX':<15} {'SCOPES':<22} {'STATUS':<10} {'CREATED':<15}")
    print("=" * 80)
    
    # Try DB first
    conn = get_db()
    rows = []
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT id, name, key_prefix, scopes, is_active, created_at FROM api_keys ORDER BY created_at DESC")
            rows = cur.fetchall()
            cur.close()
            conn.close()
        except Exception:
            rows = []

    if not rows:
        # File fallback
        file_keys = load_file_keys()
        for k in file_keys:
            status = 'ACTIVE' if k.get('is_active', True) else 'REVOKED'
            scopes = ','.join(k.get('scopes', ['read']))
            print(f"  {k.get('name','unnamed'):<20} {k.get('key_prefix',''):<15} {scopes:<22} {status:<10} {k.get('created_at',''):<15}")
    else:
        for r in rows:
            kid, name, prefix, scopes, active, created = r
            status = 'ACTIVE' if active else 'REVOKED'
            scopes_str = ','.join(scopes) if isinstance(scopes, list) else str(scopes)
            created_str = str(created)[:19] if created else ''
            print(f"  {(name or 'unnamed'):<20} {(prefix or ''):<15} {scopes_str:<22} {status:<10} {created_str:<15}")
    print("=" * 80 + "\n")

def revoke_key(identifier):
    # Try DB
    revoked = False
    conn = get_db()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                UPDATE api_keys 
                SET is_active = FALSE 
                WHERE id::text = %s OR key_prefix = %s
                RETURNING id, name
            """, (identifier, identifier))
            row = cur.fetchone()
            if row:
                conn.commit()
                print(f"Revoked key in database: {row[1]} ({row[0]})")
                revoked = True
            cur.close()
            conn.close()
        except Exception as e:
            pass

    # File update
    file_keys = load_file_keys()
    for k in file_keys:
        if k.get('id') == identifier or k.get('key_prefix') == identifier:
            k['is_active'] = False
            revoked = True
            print(f"Revoked key in file: {k.get('name')} ({k.get('id')})")
    save_file_keys(file_keys)

    if not revoked:
        print(f"Key matching '{identifier}' not found.")

def main():
    parser = argparse.ArgumentParser(description="Controva Platform API Key Manager")
    subparsers = parser.add_subparsers(dest="command")

    # Create command
    create_p = subparsers.add_parser("create", help="Create a new API key")
    create_p.add_argument("--name", "-n", required=True, help="Name or label for this API key (e.g. 'n8n-automation')")
    create_p.add_argument("--scopes", "-s", default="read,write", help="Comma-separated scopes: read, write, admin (default: read,write)")

    # List command
    subparsers.add_parser("list", help="List all generated API keys")

    # Revoke command
    revoke_p = subparsers.add_parser("revoke", help="Revoke an API key")
    revoke_p.add_argument("identifier", help="Key ID or Key Prefix (e.g. ctrv_xxxx)")

    args = parser.parse_args()

    if args.command == "create":
        scopes = [s.strip().lower() for s in args.scopes.split(",") if s.strip()]
        create_key(args.name, scopes)
    elif args.command == "list":
        list_keys()
    elif args.command == "revoke":
        revoke_key(args.identifier)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
