#!/usr/bin/env python3
"""
LeadGen API v5 - Multi-Module Intelligence Platform
====================================================
Modules:
  - Lead Generation (existing)
  - SEO Keyword Research
  - Competitor Intelligence
  - E-commerce Research
  - Social Media Scout

Key Improvements:
  - Free-text search bar (natural language -> Gemini parses)
  - Worldwide geocoding (any city/country)
  - Provider toggle (Serper / Oxylabs / Auto)
  - Smart caching (no re-processing same leads)
  - Optional Replicate (use imagine.art if key provided)
  - Free alternatives for Apollo/Hunter
"""
import json, csv, io, re, time, urllib.request, urllib.parse, psycopg2
import threading, os, hashlib, smtplib, socket
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

# ──────────────────────────────────────────────────────────────
#  API KEYS
# ──────────────────────────────────────────────────────────────
# SECURITY: keys are loaded from config.json (LEADGEN_HOME or the
# directory containing this script) or from the matching env vars.
# NEVER hardcode real keys here — this file is committed to git.
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY', '')
SERPER_KEY     = os.environ.get('SERPER_KEY', '')
GEMINI_KEY     = os.environ.get('GEMINI_KEY', '')
CLAUDE_KEY     = os.environ.get('CLAUDE_KEY', '')
REPLICATE_TOKEN= os.environ.get('REPLICATE_TOKEN', '')
IMAGINE_ART_KEY= os.environ.get('IMAGINE_ART_KEY', '')
OXYLABS_KEY    = os.environ.get('OXYLABS_KEY', '')
CRAWL4AI_URL   = os.environ.get('CRAWL4AI_URL', 'http://localhost:11235')
CRAWL4AI_TOKEN = os.environ.get('CRAWL4AI_TOKEN', '')
HERE_API_KEY   = os.environ.get('HERE_API_KEY', '')  # Free 250k/mo: developer.here.com

# Internal token the public API (controva_api.py) uses to call this
# service. Auto-generated into config.json on first start.
SERVICE_TOKEN  = os.environ.get('SERVICE_TOKEN', '')

# ── N8N Webhook Integration ──────────────────────────────────────
# Fires after every completed search → sends leads to Google Sheets & Drive via N8N
N8N_WEBHOOK_URL = os.environ.get('N8N_WEBHOOK_URL', '')

# ── Scraping Alternatives (all have free monthly tiers) ──────────
SCRAPINGBEE_KEY = os.environ.get('SCRAPINGBEE_KEY', '')   # 1,000 free req/mo — scrapingbee.com
ZENROWS_KEY     = os.environ.get('ZENROWS_KEY', '')        # 1,000 free req/mo — zenrows.com
SCRAPINGDOG_KEY = os.environ.get('SCRAPINGDOG_KEY', '')    # 1,000 free req/mo — scrapingdog.com
FIRECRAWL_KEY   = os.environ.get('FIRECRAWL_KEY', '')      # 500  free req/mo  — firecrawl.dev

# ── eBay official Browse API (FREE — 5,000 calls/day) ────────────
# Register at developer.ebay.com → create app → copy App ID + Cert ID.
# Gives exact active-listing counts + real listing prices per marketplace.
EBAY_CLIENT_ID     = os.environ.get('EBAY_CLIENT_ID', '')
EBAY_CLIENT_SECRET = os.environ.get('EBAY_CLIENT_SECRET', '')

# ── Live intent sources (free tiers) ─────────────────────────────
# Reddit: create a free "script" app at reddit.com/prefs/apps → paste
# the client id + secret here or into config.json. Enables r/forhire live.
REDDIT_CLIENT_ID     = os.environ.get('REDDIT_CLIENT_ID', '')
REDDIT_CLIENT_SECRET = os.environ.get('REDDIT_CLIENT_SECRET', '')
# Freelancer.com: free API key from developers.freelancer.com (optional)
FREELANCER_API_KEY   = os.environ.get('FREELANCER_API_KEY', '')
# MillionVerifier: paid fallback (~$1/1000 checks) for emails our SMTP probe
# can't resolve ('unknown'). millionverifier.com — optional.
MILLIONVERIFIER_KEY = os.environ.get('MILLIONVERIFIER_KEY', '')

# ── M3: outreach compliance & tracking ───────────────────────────
PUBLIC_BASE_URL     = os.environ.get('PUBLIC_BASE_URL', '')   # e.g. https://app.controvallc.com
COMPANY_NAME        = os.environ.get('COMPANY_NAME', 'Controva LLC')
COMPANY_ADDRESS     = os.environ.get('COMPANY_ADDRESS', '')   # CAN-SPAM requires a postal address
RESEND_WEBHOOK_SECRET = os.environ.get('RESEND_WEBHOOK_SECRET', '')  # svix signing secret (wh_...)
IMAP_HOST = os.environ.get('IMAP_HOST', '')   # reply detection (e.g. imap.gmail.com)
IMAP_USER = os.environ.get('IMAP_USER', '')
IMAP_PASS = os.environ.get('IMAP_PASS', '')

# Configuration toggles (can be changed via /config endpoint)
CONFIG = {
    'enrichment_strategy': 'serper_then_oxylabs',  # serper_only | oxylabs_only | serper_then_oxylabs | free_only
    'enrichment_primary': 'serper',       # kept for backwards-compat; enrichment_strategy takes precedence
    'enrichment_fallback': 'oxylabs',     # kept for backwards-compat
    'image_provider': 'none',             # none | replicate | imagine_art
    'auto_score': True,                   # Run Gemini scoring during pipeline
    'auto_email_copy': False,             # Claude email writing OFF by default (saves credits)
    'auto_image': False,                  # Image generation OFF by default
    # M3 send throttle — protects sender reputation (mailbox-provider safe zone)
    'send_hourly_limit': 30,
    'send_daily_limit': 100,
    # M4 sequences — automatic multi-touch follow-ups
    'sequences_enabled': True,
    'sequence_interval_minutes': 10,
    # M5: monthly API budget (USD) — dashboard alert at 80%
    'cost_budget_monthly': 50,
}

# Map enrichment_strategy → providers list for enrich_lead()
_STRATEGY_PROVIDERS = {
    'free_first':          ['free_scrape', 'permutator', 'serper', 'oxylabs'],
    'serper_only':         ['serper'],
    'oxylabs_only':        ['oxylabs'],
    'serper_then_oxylabs': ['serper', 'oxylabs'],
    'free_only':           ['serper'],
}

# ──────────────────────────────────────────────────────────────
#  PERSISTENT CONFIG (saved to /opt/leadgen/config.json)
# ──────────────────────────────────────────────────────────────
# LEADGEN_HOME env var lets you run locally without /opt/leadgen.
# Set it to any writable directory, e.g.:
#   Windows: set LEADGEN_HOME=C:\leadgen
#   Linux/Mac: export LEADGEN_HOME=$HOME/leadgen
LEADGEN_HOME = os.environ.get('LEADGEN_HOME', '/opt/leadgen')
# Also check alongside the script itself (useful for local dev without env var)
_script_dir = os.path.dirname(os.path.abspath(__file__))
_local_config = os.path.join(_script_dir, 'config.json')
if not os.path.isdir(LEADGEN_HOME) and os.path.exists(_local_config):
    LEADGEN_HOME = _script_dir
CONFIG_FILE = os.path.join(LEADGEN_HOME, 'config.json')

def load_config():
    """Load config from disk, fall back to defaults."""
    global GOOGLE_API_KEY, SERPER_KEY, GEMINI_KEY, CLAUDE_KEY, REPLICATE_TOKEN, IMAGINE_ART_KEY, OXYLABS_KEY, RESEND_KEY, FROM_EMAIL, FROM_NAME, HERE_API_KEY, SCRAPINGBEE_KEY, ZENROWS_KEY, SCRAPINGDOG_KEY, FIRECRAWL_KEY, EBAY_CLIENT_ID, EBAY_CLIENT_SECRET, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, FREELANCER_API_KEY, MILLIONVERIFIER_KEY, PUBLIC_BASE_URL, COMPANY_NAME, COMPANY_ADDRESS, RESEND_WEBHOOK_SECRET, IMAP_HOST, IMAP_USER, IMAP_PASS
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                saved = json.load(f)
            # API keys
            keys_map = {
                'google_api_key':   'GOOGLE_API_KEY',
                'serper_key':       'SERPER_KEY',
                'gemini_key':       'GEMINI_KEY',
                'claude_key':       'CLAUDE_KEY',
                'replicate_token':  'REPLICATE_TOKEN',
                'imagine_art_key':  'IMAGINE_ART_KEY',
                'oxylabs_key':      'OXYLABS_KEY',
                'resend_key':       'RESEND_KEY',
                'from_email':       'FROM_EMAIL',
                'from_name':        'FROM_NAME',
                'here_api_key':     'HERE_API_KEY',
                'scrapingbee_key':  'SCRAPINGBEE_KEY',
                'zenrows_key':      'ZENROWS_KEY',
                'scrapingdog_key':  'SCRAPINGDOG_KEY',
                'firecrawl_key':    'FIRECRAWL_KEY',
                'ebay_client_id':     'EBAY_CLIENT_ID',
                'ebay_client_secret': 'EBAY_CLIENT_SECRET',
                'service_token':      'SERVICE_TOKEN',
                'reddit_client_id':   'REDDIT_CLIENT_ID',
                'reddit_client_secret':'REDDIT_CLIENT_SECRET',
                'freelancer_api_key': 'FREELANCER_API_KEY',
                'millionverifier_key': 'MILLIONVERIFIER_KEY',
                'public_base_url':     'PUBLIC_BASE_URL',
                'company_name':        'COMPANY_NAME',
                'company_address':     'COMPANY_ADDRESS',
                'resend_webhook_secret':'RESEND_WEBHOOK_SECRET',
                'imap_host':           'IMAP_HOST',
                'imap_user':           'IMAP_USER',
                'imap_pass':           'IMAP_PASS',
            }
            for key, var_name in keys_map.items():
                if key in saved and saved[key]:
                    globals()[var_name] = saved[key]
            # Config toggles
            if 'config' in saved:
                for k, v in saved['config'].items():
                    if k in CONFIG: CONFIG[k] = v
            print(f'Loaded config from {CONFIG_FILE}')
    except Exception as e:
        print(f'Config load error: {e}')

def save_config():
    """Save current config to disk."""
    try:
        data = {
            'google_api_key':  GOOGLE_API_KEY,
            'serper_key':      SERPER_KEY,
            'gemini_key':      GEMINI_KEY,
            'claude_key':      CLAUDE_KEY,
            'replicate_token': REPLICATE_TOKEN,
            'imagine_art_key': IMAGINE_ART_KEY,
            'oxylabs_key':     OXYLABS_KEY,
            'resend_key':      RESEND_KEY,
            'from_email':      FROM_EMAIL,
            'from_name':       FROM_NAME,
            'here_api_key':    HERE_API_KEY,
            'scrapingbee_key': SCRAPINGBEE_KEY,
            'zenrows_key':     ZENROWS_KEY,
            'scrapingdog_key': SCRAPINGDOG_KEY,
            'firecrawl_key':   FIRECRAWL_KEY,
            'ebay_client_id':     EBAY_CLIENT_ID,
            'ebay_client_secret': EBAY_CLIENT_SECRET,
            'service_token':      SERVICE_TOKEN,
            'reddit_client_id':     REDDIT_CLIENT_ID,
            'reddit_client_secret': REDDIT_CLIENT_SECRET,
            'freelancer_api_key':   FREELANCER_API_KEY,
            'millionverifier_key':  MILLIONVERIFIER_KEY,
            'public_base_url':      PUBLIC_BASE_URL,
            'company_name':         COMPANY_NAME,
            'company_address':      COMPANY_ADDRESS,
            'resend_webhook_secret':RESEND_WEBHOOK_SECRET,
            'imap_host':            IMAP_HOST,
            'imap_user':            IMAP_USER,
            'imap_pass':            IMAP_PASS,
            'config':          CONFIG,
        }
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f'Config save error: {e}')
        return False

def update_api_key(name, value):
    """Update an API key and save."""
    global GOOGLE_API_KEY, SERPER_KEY, GEMINI_KEY, CLAUDE_KEY, REPLICATE_TOKEN, IMAGINE_ART_KEY, OXYLABS_KEY, RESEND_KEY, FROM_EMAIL, FROM_NAME, HERE_API_KEY, SCRAPINGBEE_KEY, ZENROWS_KEY, SCRAPINGDOG_KEY, FIRECRAWL_KEY, EBAY_CLIENT_ID, EBAY_CLIENT_SECRET, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, FREELANCER_API_KEY, MILLIONVERIFIER_KEY, PUBLIC_BASE_URL, COMPANY_NAME, COMPANY_ADDRESS, RESEND_WEBHOOK_SECRET, IMAP_HOST, IMAP_USER, IMAP_PASS
    name_lower = name.lower()
    valid_keys = ['google_api_key', 'serper_key', 'gemini_key', 'claude_key',
                  'replicate_token', 'imagine_art_key', 'oxylabs_key', 'resend_key',
                  'from_email', 'from_name', 'here_api_key',
                  'scrapingbee_key', 'zenrows_key', 'scrapingdog_key', 'firecrawl_key',
                  'ebay_client_id', 'ebay_client_secret',
                  'reddit_client_id', 'reddit_client_secret', 'freelancer_api_key',
                  'millionverifier_key',
                  'public_base_url', 'company_name', 'company_address',
                  'resend_webhook_secret', 'imap_host', 'imap_user', 'imap_pass']
    if name_lower not in valid_keys: return False
    var_name = name_lower.upper()
    globals()[var_name] = value
    return save_config()

def get_api_keys_masked():
    """Return current API keys with values masked except last 4 chars."""
    def mask(v):
        if not v: return {'set': False, 'preview': ''}
        s = str(v)
        if len(s) <= 8: return {'set': True, 'preview': '****'}
        return {'set': True, 'preview': '****' + s[-4:]}
    return {
        'google_api_key':  mask(GOOGLE_API_KEY),
        'serper_key':      mask(SERPER_KEY),
        'gemini_key':      mask(GEMINI_KEY),
        'claude_key':      mask(CLAUDE_KEY),
        'replicate_token': mask(REPLICATE_TOKEN),
        'imagine_art_key': mask(IMAGINE_ART_KEY),
        'oxylabs_key':     mask(OXYLABS_KEY),
        'resend_key':      mask(RESEND_KEY),
        'from_email':      {'set': bool(FROM_EMAIL), 'preview': FROM_EMAIL},
        'from_name':       {'set': bool(FROM_NAME), 'preview': FROM_NAME},
        'here_api_key':    mask(HERE_API_KEY),
        'scrapingbee_key': mask(SCRAPINGBEE_KEY),
        'zenrows_key':     mask(ZENROWS_KEY),
        'scrapingdog_key': mask(SCRAPINGDOG_KEY),
        'firecrawl_key':   mask(FIRECRAWL_KEY),
        'ebay_client_id':     mask(EBAY_CLIENT_ID),
        'ebay_client_secret': mask(EBAY_CLIENT_SECRET),
        'reddit_client_id':     mask(REDDIT_CLIENT_ID),
        'reddit_client_secret': mask(REDDIT_CLIENT_SECRET),
        'freelancer_api_key':   mask(FREELANCER_API_KEY),
        'millionverifier_key':  mask(MILLIONVERIFIER_KEY),
        'public_base_url':      {'set': bool(PUBLIC_BASE_URL), 'preview': PUBLIC_BASE_URL},
        'company_name':         {'set': bool(COMPANY_NAME), 'preview': COMPANY_NAME},
        'company_address':      {'set': bool(COMPANY_ADDRESS), 'preview': COMPANY_ADDRESS},
        'resend_webhook_secret':mask(RESEND_WEBHOOK_SECRET),
        'imap_host':            {'set': bool(IMAP_HOST), 'preview': IMAP_HOST},
        'imap_user':            {'set': bool(IMAP_USER), 'preview': IMAP_USER},
        'imap_pass':            mask(IMAP_PASS),
    }

# Load saved config at startup
load_config()


FIELD_MASK = 'places.id,places.displayName,places.formattedAddress,places.location,places.websiteUri,places.nationalPhoneNumber,places.rating,places.userRatingCount'

DB = dict(host=os.environ.get('DB_HOST', '127.0.0.1'), port=int(os.environ.get('DB_PORT', 5433)),
          database=os.environ.get('DB_NAME', 'leadgen_db'),
          user=os.environ.get('DB_USER', 'leadgen'),
          password=os.environ.get('DB_PASS', ''), connect_timeout=2)

JOBS = {}  # background job tracker

# ──────────────────────────────────────────────────────────────
#  OXYLABS SDK (lazy load)
# ──────────────────────────────────────────────────────────────
os.environ["OXYLABS_AI_STUDIO_API_KEY"] = OXYLABS_KEY
try:
    from oxylabs_ai_studio.apps.ai_scraper import AiScraper
    OXYLABS = AiScraper(api_key=OXYLABS_KEY)
    print("Oxylabs AI Studio: initialized")
except Exception as e:
    print(f"Oxylabs init failed: {e}")
    OXYLABS = None

# ──────────────────────────────────────────────────────────────
#  MARKET / COUNTRY CONFIG  (for e-commerce research)
# ──────────────────────────────────────────────────────────────
MARKET_CONFIG = {
    'us': {'gl': 'us', 'hl': 'en', 'ebay': 'www.ebay.com',    'amazon': 'www.amazon.com',    'currency': 'USD', 'symbol': '$',   'name': 'United States',  'ebay_marketplace': 'EBAY_US'},
    'uk': {'gl': 'gb', 'hl': 'en', 'ebay': 'www.ebay.co.uk',  'amazon': 'www.amazon.co.uk',  'currency': 'GBP', 'symbol': '£',   'name': 'United Kingdom', 'ebay_marketplace': 'EBAY_GB'},
    'au': {'gl': 'au', 'hl': 'en', 'ebay': 'www.ebay.com.au', 'amazon': 'www.amazon.com.au', 'currency': 'AUD', 'symbol': 'A$',  'name': 'Australia',      'ebay_marketplace': 'EBAY_AU'},
    'ca': {'gl': 'ca', 'hl': 'en', 'ebay': 'www.ebay.ca',     'amazon': 'www.amazon.ca',     'currency': 'CAD', 'symbol': 'C$',  'name': 'Canada',         'ebay_marketplace': 'EBAY_ENCA'},
    'de': {'gl': 'de', 'hl': 'de', 'ebay': 'www.ebay.de',     'amazon': 'www.amazon.de',     'currency': 'EUR', 'symbol': '€',   'name': 'Germany',        'ebay_marketplace': 'EBAY_DE'},
    'fr': {'gl': 'fr', 'hl': 'fr', 'ebay': 'www.ebay.fr',     'amazon': 'www.amazon.fr',     'currency': 'EUR', 'symbol': '€',   'name': 'France',         'ebay_marketplace': 'EBAY_FR'},
    'it': {'gl': 'it', 'hl': 'it', 'ebay': 'www.ebay.it',     'amazon': 'www.amazon.it',     'currency': 'EUR', 'symbol': '€',   'name': 'Italy',          'ebay_marketplace': 'EBAY_IT'},
    'es': {'gl': 'es', 'hl': 'es', 'ebay': 'www.ebay.es',     'amazon': 'www.amazon.es',     'currency': 'EUR', 'symbol': '€',   'name': 'Spain',          'ebay_marketplace': 'EBAY_ES'},
}

# ──────────────────────────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────────────────────────
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
EMAIL_SKIP_DOMAINS = ['example.com','sentry.io','schema.org','w3.org','cloudflare.com',
                     'wixstatic.com','wix.com','google.com','googleapis.com','goog.le',
                     'facebook.com','instagram.com','twitter.com','linkedin.com',
                     'youtube.com','apple.com','gstatic.com','noreply','no-reply',
                     'donotreply','support@apple','feedback@','abuse@','postmaster@',
                     'trustindex.io','findmyspa.ae','fresha.com','editionhotels.com']

def db_conn():
    return psycopg2.connect(**DB)

def extract_emails(text):
    if not text: return []
    found = EMAIL_RE.findall(text)
    cleaned, seen = [], set()
    for e in found:
        el = e.lower()
        if any(s in el for s in EMAIL_SKIP_DOMAINS): continue
        if el in seen or len(e) > 80: continue
        seen.add(el); cleaned.append(e)
    return cleaned

def cache_key(query_type, payload):
    """Hash a query so we can dedupe repeated requests."""
    raw = json.dumps({'type': query_type, 'data': payload}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]

def is_query_cached(query_type, payload, max_age_hours=24):
    """Check if we already ran this exact query recently."""
    ck = cache_key(query_type, payload)
    conn = db_conn(); cur = conn.cursor()
    cur.execute("""
        SELECT created_at FROM processed_cache
        WHERE cache_key=%s AND cache_type=%s
        AND created_at > NOW() - INTERVAL '%s hours'
    """, (ck, query_type, max_age_hours))
    result = cur.fetchone() is not None
    cur.close(); conn.close()
    return result

def mark_query_cached(query_type, payload):
    ck = cache_key(query_type, payload)
    conn = db_conn(); cur = conn.cursor()
    cur.execute("INSERT INTO processed_cache(cache_key,cache_type) VALUES(%s,%s) ON CONFLICT DO NOTHING",
               (ck, query_type))
    conn.commit(); cur.close(); conn.close()

# ── Full-result research cache ────────────────────────────────
# Unlike processed_cache (which only stores hashes), this stores the complete
# JSON response, so repeating an e-commerce / product-hunt query within the
# TTL costs ZERO API credits and returns instantly.

def ensure_research_cache_table():
    conn = db_conn(); cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS research_cache (
            cache_key  VARCHAR(64) PRIMARY KEY,
            cache_type VARCHAR(40) NOT NULL,
            payload    JSONB NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )""")
    conn.commit(); cur.close(); conn.close()

def get_cached_research(cache_type, payload_key, max_age_hours=24):
    try:
        ck = cache_key(cache_type, payload_key)
        conn = db_conn(); cur = conn.cursor()
        cur.execute("""SELECT payload FROM research_cache
                       WHERE cache_key=%s AND created_at > NOW() - INTERVAL '%s hours'""",
                    (ck, max_age_hours))
        row = cur.fetchone()
        cur.close(); conn.close()
        return row[0] if row else None
    except Exception as e:
        print(f'research cache read error: {e}')
        return None

def save_cached_research(cache_type, payload_key, result):
    try:
        ck = cache_key(cache_type, payload_key)
        conn = db_conn(); cur = conn.cursor()
        cur.execute("""INSERT INTO research_cache(cache_key, cache_type, payload)
                       VALUES(%s,%s,%s)
                       ON CONFLICT (cache_key) DO UPDATE
                       SET payload=EXCLUDED.payload, created_at=NOW()""",
                    (ck, cache_type, json.dumps(result)))
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        print(f'research cache write error: {e}')

# ── Permanent research history (append-only) ─────────────────────
# research_cache above is a dedup/TTL cache keyed by exact query — repeat
# queries overwrite the row, so it can't show "what have I looked at over
# time". This table is a separate, insert-only log of every run that
# actually spent credits, so results survive tab navigation, page refresh,
# and logout, and can be browsed/re-opened/exported later.

def ensure_research_history_table():
    conn = db_conn(); cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS research_history (
            id           SERIAL PRIMARY KEY,
            run_type     VARCHAR(20) NOT NULL,
            query_text   VARCHAR(300) NOT NULL,
            country      VARCHAR(10) NOT NULL DEFAULT 'us',
            result       JSONB NOT NULL,
            credits_used INTEGER DEFAULT 0,
            data_sources TEXT[],
            created_at   TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )""")
    cur.execute("""CREATE INDEX IF NOT EXISTS idx_research_history_type
                   ON research_history(run_type, created_at DESC)""")
    conn.commit(); cur.close(); conn.close()

def save_research_history(run_type, query_text, country, result):
    try:
        conn = db_conn(); cur = conn.cursor()
        cur.execute("""INSERT INTO research_history
                       (run_type, query_text, country, result, credits_used, data_sources)
                       VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (run_type, query_text[:300], country, json.dumps(result),
                     result.get('credits_used', 0), result.get('data_sources', [])))
        new_id = cur.fetchone()[0]
        conn.commit(); cur.close(); conn.close()
        return new_id
    except Exception as e:
        print(f'research history write error: {e}')
        return None

def list_research_history(run_type, limit=30):
    """Lightweight list for the History panel — no full payload, just enough
    to identify and preview each past run."""
    conn = db_conn(); cur = conn.cursor()
    cur.execute("""
        SELECT id, query_text, country, credits_used, data_sources, created_at,
               CASE WHEN run_type='product_hunt'
                    THEN jsonb_array_length(COALESCE(result->'products', '[]'::jsonb))
                    ELSE NULL END AS product_count,
               CASE WHEN run_type='ecommerce'
                    THEN result->>'ai_verdict' ELSE NULL END AS verdict_preview
        FROM research_history
        WHERE run_type=%s
        ORDER BY created_at DESC LIMIT %s
    """, (run_type, limit))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [{
        'id': r[0], 'query_text': r[1], 'country': r[2], 'credits_used': r[3],
        'data_sources': r[4] or [], 'created_at': r[5].isoformat(),
        'product_count': r[6],
        'verdict_preview': (r[7][:140] if r[7] else None),
    } for r in rows]

def get_research_history_entry(entry_id):
    conn = db_conn(); cur = conn.cursor()
    cur.execute('SELECT result FROM research_history WHERE id=%s', (entry_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return row[0] if row else None

def delete_research_history_entry(entry_id):
    conn = db_conn(); cur = conn.cursor()
    cur.execute('DELETE FROM research_history WHERE id=%s', (entry_id,))
    deleted = cur.rowcount > 0
    conn.commit(); cur.close(); conn.close()
    return deleted

def research_result_to_csv(result):
    """Build a CSV download from a stored /product-hunt or /ecommerce result."""
    buf = io.StringIO()
    if 'products' in result:  # product_hunt
        fields = ['rank', 'name', 'verdict', 'hunter_score', 'demand', 'competition',
                  'margin', 'trend', 'entry_price', 'est_monthly_sales', 'active_listings',
                  'competition_level', 'price_min', 'price_median', 'price_max',
                  'sources_checked', 'why', 'angle', 'strategy', 'example_link']
        w = csv.DictWriter(buf, fieldnames=fields)
        w.writeheader()
        for p in result.get('products', []):
            sc = p.get('scores', {}) or {}
            ps = p.get('price_stats', {}) or {}
            w.writerow({
                'rank': p.get('rank'), 'name': p.get('name'), 'verdict': p.get('verdict'),
                'hunter_score': p.get('hunter_score'), 'demand': sc.get('demand'),
                'competition': sc.get('competition'), 'margin': sc.get('margin'), 'trend': sc.get('trend'),
                'entry_price': p.get('entry_price'), 'est_monthly_sales': p.get('est_monthly_sales'),
                'active_listings': p.get('active_listings'), 'competition_level': p.get('competition_level'),
                'price_min': ps.get('min'), 'price_median': ps.get('median'), 'price_max': ps.get('max'),
                'sources_checked': ' | '.join(p.get('sources_checked', [])),
                'why': p.get('why'), 'angle': p.get('angle'), 'strategy': p.get('strategy'),
                'example_link': (p.get('example') or {}).get('link', ''),
            })
    else:  # ecommerce deep research
        fields = ['platform', 'title', 'price', 'rating', 'link']
        w = csv.DictWriter(buf, fieldnames=fields)
        w.writeheader()
        for p in result.get('top_products', []):
            w.writerow({'platform': 'google_shopping', 'title': p.get('title'),
                       'price': p.get('price_str') or p.get('price_value'),
                       'rating': p.get('rating'), 'link': p.get('link')})
        for p in result.get('ebay_listings', []):
            w.writerow({'platform': 'ebay', 'title': p.get('title'),
                       'price': p.get('price_str'), 'rating': '', 'link': p.get('link')})
        for p in result.get('amazon_listings', []):
            w.writerow({'platform': 'amazon', 'title': p.get('title'),
                       'price': p.get('price_value'), 'rating': p.get('rating'), 'link': p.get('link')})
    return buf.getvalue().encode('utf-8')

# ──────────────────────────────────────────────────────────────
#  GEMINI - Natural Language Query Parser
# ──────────────────────────────────────────────────────────────
_GEMINI_MODELS = ['gemini-2.5-flash', 'gemini-flash-latest', 'gemini-2.0-flash', 'gemini-1.5-flash']

def gemini_call(prompt, max_tokens=300):
    log_api_usage('gemini', 'gemini_call')
    """Call Gemini, trying a few model names so a deprecated/renamed model
    or a per-model quota limit doesn't silently break query parsing.
    Quota (429) and unknown-model (404) errors are model-specific on the
    free tier — different model IDs have separate quotas — so both fall
    through to the next model instead of giving up immediately."""
    if not GEMINI_KEY:
        print('Gemini error: no API key set')
        return None
    body = json.dumps({
        'contents': [{'parts': [{'text': prompt}]}],
        # thinkingBudget=0 disables Gemini 2.5's extended "thinking" tokens.
        # Those are invisible reasoning tokens that count against
        # maxOutputTokens, so without this a small budget can be silently
        # consumed entirely by thinking, truncating the real answer
        # (finishReason: MAX_TOKENS with empty/partial text). All our calls
        # are structured extraction/classification, not deep reasoning, so
        # disabling it is pure upside: faster, cheaper, no truncation risk.
        'generationConfig': {'temperature': 0.2, 'maxOutputTokens': max_tokens,
                             'thinkingConfig': {'thinkingBudget': 0}}
    }).encode()
    last_err = None
    for model in _GEMINI_MODELS:
        try:
            req = urllib.request.Request(
                f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_KEY}',
                data=body, method='POST',
                headers={'Content-Type': 'application/json'}
            )
            resp = urllib.request.urlopen(req, timeout=20)
            data = json.loads(resp.read().decode())
            return data['candidates'][0]['content']['parts'][0]['text']
        except urllib.error.HTTPError as e:
            last_err = f'{e.code} {e.reason}'
            if e.code in (404, 429):
                # 404 = model renamed/gone, 429 = this model's quota exhausted.
                # Both are model-specific — try the next model in the list.
                print(f'Gemini {model}: {last_err}, trying next model')
                continue
            # 401/403 = bad key, other 4xx/5xx = not model-specific — stop.
            print(f'Gemini error ({model}): {last_err}')
            return None
        except Exception as e:
            last_err = str(e)
            continue
    print(f'Gemini error: all models failed — {last_err}')
    return None

def parse_search_query(text):
    """Convert natural language to structured query.
    Uses Gemini AI first, falls back to smart regex parser.
    """
    # Try Gemini first
    prompt = f"""Parse this business search query into structured fields.

Query: "{text}"

Return ONLY valid JSON in this format:
{{"niche":"<business type>","city":"<city name>","country":"<2-letter ISO>","modifiers":[]}}

Rules:
- "niche" = the business type EXACTLY as the user described it (keep the full phrase, e.g. "pest control and exterminators", "personal injury lawyer"). Do NOT substitute a different category.
- "city" = the real CITY the user named. If they give BOTH a city and a state (e.g. "edison new jersey"), use the CITY (Edison) — never replace it with another city. ONLY when the user gives a state with NO city (e.g. "in texas") do you use that state's largest city.
- "country" = 2-letter ISO code.

Country codes: US, GB, AE, IN, PK, BD, SA, AU, CA, SG, MY, EG, NG, ZA, BR, MX, AR, TR, ID, PH, TH, VN, JP, KR, CN, DE, FR, ES, IT, NL, BE, CH, SE, NO, DK, FI, PL, RU, UA, IR, IQ, JO, KW, BH, OM, QA, LB, MA, KE

Examples:
- "barber shops in Manchester UK" -> {{"niche":"barber","city":"Manchester","country":"GB","modifiers":[]}}
- "restaurants in Lahore Pakistan" -> {{"niche":"restaurant","city":"Lahore","country":"PK","modifiers":[]}}
- "Pest Control and Exterminators in edison new jersey USA" -> {{"niche":"pest control and exterminators","city":"Edison","country":"US","modifiers":[]}}
- "pest control in new jersey" -> {{"niche":"pest control","city":"Newark","country":"US","modifiers":[]}}
- "personal injury lawyers in texas" -> {{"niche":"personal injury lawyer","city":"Houston","country":"US","modifiers":[]}}
- "salons in Karachi" -> {{"niche":"salon","city":"Karachi","country":"PK","modifiers":[]}}
- "restaurants in Pakistan" -> {{"niche":"restaurant","city":"Islamabad","country":"PK","modifiers":[]}}"""

    response = gemini_call(prompt, 250)
    if response:
        try:
            m = re.search(r'\{[\s\S]*\}', response)
            if m:
                parsed = json.loads(m.group())
                # Validate country is a real ISO code
                if parsed.get('country') and len(parsed.get('country', '')) == 2:
                    return _fix_state_as_city(parsed)
        except Exception as e:
            print(f'Gemini parse error: {e}')

    # FALLBACK: smart regex parser
    print('Using regex fallback')
    text_lower = text.lower()

    # ── Country detection with city hints ──────────────────────
    # Map country names to ISO codes and their major cities
    country_to_iso = {
        'pakistan': 'PK', 'pk': 'PK',
        'india': 'IN', 'bharat': 'IN',
        'bangladesh': 'BD',
        'sri lanka': 'LK',
        'nepal': 'NP',
        'afghanistan': 'AF',
        'uk': 'GB', 'united kingdom': 'GB', 'britain': 'GB', 'england': 'GB',
            'scotland': 'GB', 'wales': 'GB',
        'usa': 'US', 'united states': 'US', 'america': 'US', 'u.s.': 'US',
        'canada': 'CA',
        'australia': 'AU',
        'new zealand': 'NZ',
        'uae': 'AE', 'united arab emirates': 'AE', 'emirates': 'AE',
        'saudi arabia': 'SA', 'saudi': 'SA', 'ksa': 'SA',
        'qatar': 'QA',
        'bahrain': 'BH',
        'kuwait': 'KW',
        'oman': 'OM',
        'jordan': 'JO',
        'lebanon': 'LB',
        'egypt': 'EG',
        'morocco': 'MA',
        'south africa': 'ZA',
        'nigeria': 'NG',
        'kenya': 'KE',
        'ghana': 'GH',
        'singapore': 'SG',
        'malaysia': 'MY',
        'indonesia': 'ID',
        'philippines': 'PH',
        'thailand': 'TH',
        'vietnam': 'VN',
        'japan': 'JP',
        'china': 'CN',
        'korea': 'KR', 'south korea': 'KR',
        'germany': 'DE', 'deutschland': 'DE',
        'france': 'FR',
        'spain': 'ES',
        'italy': 'IT',
        'netherlands': 'NL', 'holland': 'NL',
        'belgium': 'BE',
        'switzerland': 'CH',
        'sweden': 'SE',
        'norway': 'NO',
        'denmark': 'DK',
        'poland': 'PL',
        'turkey': 'TR',
        'iran': 'IR',
        'iraq': 'IQ',
        'brazil': 'BR',
        'mexico': 'MX',
        'argentina': 'AR',
        'colombia': 'CO',
        'russia': 'RU',
        'ukraine': 'UA',
    }

    # City -> country hints (for when only city is mentioned)
    city_to_country = {
        # Pakistan
        'lahore': 'PK', 'karachi': 'PK', 'islamabad': 'PK', 'rawalpindi': 'PK',
        'faisalabad': 'PK', 'multan': 'PK', 'peshawar': 'PK', 'quetta': 'PK',
        'sialkot': 'PK', 'gujranwala': 'PK', 'hyderabad pk': 'PK',
        # India
        'mumbai': 'IN', 'delhi': 'IN', 'new delhi': 'IN', 'bangalore': 'IN',
        'bengaluru': 'IN', 'chennai': 'IN', 'kolkata': 'IN', 'hyderabad': 'IN',
        'pune': 'IN', 'ahmedabad': 'IN', 'jaipur': 'IN', 'lucknow': 'IN',
        # Bangladesh
        'dhaka': 'BD', 'chittagong': 'BD',
        # UK
        'london': 'GB', 'manchester': 'GB', 'birmingham': 'GB', 'leeds': 'GB',
        'glasgow': 'GB', 'liverpool': 'GB', 'sheffield': 'GB', 'edinburgh': 'GB',
        'bristol': 'GB', 'cardiff': 'GB',
        # USA
        'new york': 'US', 'los angeles': 'US', 'chicago': 'US', 'houston': 'US',
        'phoenix': 'US', 'philadelphia': 'US', 'san antonio': 'US', 'san diego': 'US',
        'dallas': 'US', 'austin': 'US', 'miami': 'US', 'atlanta': 'US',
        'boston': 'US', 'seattle': 'US', 'denver': 'US', 'beverly hills': 'US',
        # Canada
        'toronto': 'CA', 'vancouver': 'CA', 'montreal': 'CA', 'calgary': 'CA',
        'ottawa': 'CA', 'edmonton': 'CA',
        # Australia
        'sydney': 'AU', 'melbourne': 'AU', 'brisbane': 'AU', 'perth': 'AU',
        'adelaide': 'AU',
        # UAE
        'dubai': 'AE', 'abu dhabi': 'AE', 'sharjah': 'AE', 'ajman': 'AE',
        # Saudi
        'riyadh': 'SA', 'jeddah': 'SA', 'mecca': 'SA', 'medina': 'SA',
        # Other
        'doha': 'QA', 'manama': 'BH', 'kuwait city': 'KW', 'muscat': 'OM',
        'amman': 'JO', 'beirut': 'LB', 'cairo': 'EG', 'casablanca': 'MA',
        'singapore': 'SG', 'kuala lumpur': 'MY', 'jakarta': 'ID',
        'bangkok': 'TH', 'manila': 'PH', 'ho chi minh': 'VN', 'hanoi': 'VN',
        'tokyo': 'JP', 'osaka': 'JP', 'seoul': 'KR', 'beijing': 'CN',
        'shanghai': 'CN', 'hong kong': 'HK',
        'paris': 'FR', 'berlin': 'DE', 'madrid': 'ES', 'rome': 'IT',
        'amsterdam': 'NL', 'brussels': 'BE', 'zurich': 'CH',
        'stockholm': 'SE', 'oslo': 'NO', 'copenhagen': 'DK', 'warsaw': 'PL',
        'istanbul': 'TR', 'sao paulo': 'BR', 'rio de janeiro': 'BR',
        'mexico city': 'MX', 'buenos aires': 'AR', 'moscow': 'RU',
        'lagos': 'NG', 'nairobi': 'KE', 'johannesburg': 'ZA', 'cape town': 'ZA',
    }

    # Detect country (explicit country name in text). Longest names first so
    # "united states" wins over a stray "us", "saudi arabia" over "saudi".
    country = None
    country_match_str = None
    for cname, code in sorted(country_to_iso.items(), key=lambda kv: len(kv[0]), reverse=True):
        if re.search(r'\b' + re.escape(cname) + r'\b', text_lower):
            country = code
            country_match_str = cname
            break

    # ── Split "<niche> in/at/near <location>" ──────────────────
    # Everything before the location preposition is the niche; everything
    # after is the location. This works for ANY niche, not just a fixed list.
    loc_split = re.split(r'\s+\b(?:in|at|near|around|located in|based in|serving)\b\s+',
                         text.strip(), maxsplit=1, flags=re.IGNORECASE)
    niche_part = loc_split[0].strip()
    location_part = loc_split[1].strip() if len(loc_split) > 1 else ''

    # ── Niche: use the actual words the user typed (no "restaurant" default) ──
    niche = re.sub(r'\b(business(?:es)?|companies|company|services|service|'
                   r'near me|leads?|find|list of|all|the)\b', '', niche_part,
                   flags=re.IGNORECASE)
    niche = re.sub(r'\s+', ' ', niche).strip(' ,.-')
    if not niche:
        # Last resort: a known niche keyword anywhere in the text
        niche_words = ['restaurant', 'cafe', 'coffee', 'salon', 'hair', 'beauty', 'nail',
                       'barber', 'hotel', 'bar', 'pub', 'gym', 'fitness', 'clinic',
                       'pharmacy', 'bakery', 'spa', 'dentist', 'plumber', 'electrician',
                       'roofer', 'lawyer', 'accountant', 'contractor', 'landscaper']
        niche = next((w for w in niche_words if w in text_lower), text.strip())

    # ── City detection ─────────────────────────────────────────
    # Priority: the explicit "<niche> in LOCATION" text the user typed wins.
    # We only fall back to "state's largest city" when the user gave a BARE
    # state with no city (e.g. "plumbers in Texas").
    city = None
    state_full = None   # set when the location is just a US state → triggers sweep

    def _strip_country_words(s):
        out = s
        for w in [country_match_str or '', 'usa', 'u.s.a', 'u.s.', 'u.s',
                  'united states', 'america', 'uk', 'u.k.', 'united kingdom',
                  'uae', 'united arab emirates', 'ksa']:
            if w:
                out = re.sub(r'\b' + re.escape(w) + r'\b', '', out, flags=re.IGNORECASE)
        out = re.sub(r'[,\.]', ' ', out)
        return re.sub(r'\s+', ' ', out).strip(' ,.-')

    # 1) Trust the location the user wrote after "in/at/near"
    if location_part:
        loc_clean = re.sub(r'[,\.]', ' ', location_part)
        loc_clean = re.sub(r'\s+', ' ', loc_clean).strip(' ,.-')
        if loc_clean.lower() in COUNTRY_PRIMARY_CITY:
            # ONLY a country given ("restaurants in Pakistan") → its primary city
            city, country = COUNTRY_PRIMARY_CITY[loc_clean.lower()]
        else:
            loc = _strip_country_words(location_part)
            loc_lower = loc.lower()
            if loc_lower in US_STATE_CITIES:
                # ONLY a state given → sweep its top cities for maximum coverage
                state_full = loc_lower
                city = US_STATE_CITIES[loc_lower]
                country = country or 'US'
            elif loc:
                # A real place (city, "city state", neighborhood) → keep it whole
                # so the geocoder resolves it precisely (e.g. "Edison New Jersey").
                city = loc.title()
                if any(re.search(r'\b' + re.escape(s) + r'\b', loc_lower) for s in US_STATE_CITIES):
                    country = country or 'US'
                elif not country:
                    # Infer country from a known city mentioned in the location
                    for cn, cc in city_to_country.items():
                        if re.search(r'\b' + re.escape(cn) + r'\b', loc_lower):
                            country = cc
                            break

    # 2) No "in" clause → known major city mentioned anywhere
    if not city:
        for city_name in sorted(city_to_country.keys(), key=len, reverse=True):
            if re.search(r'\b' + re.escape(city_name) + r'\b', text_lower):
                city = city_name.title()
                country = country or city_to_country[city_name]
                break

    # 3) Still nothing → a bare US state mentioned anywhere in the text
    if not city:
        for state_name in sorted(US_STATE_CITIES.keys(), key=len, reverse=True):
            if re.search(r'\b' + re.escape(state_name) + r'\b', text_lower):
                state_full = state_name
                city = US_STATE_CITIES[state_name]
                country = country or 'US'
                break

    # 4) Still nothing → a bare country mentioned anywhere → its primary city
    if not city:
        for cname in sorted(COUNTRY_PRIMARY_CITY.keys(), key=len, reverse=True):
            if re.search(r'\b' + re.escape(cname) + r'\b', text_lower):
                city, country = COUNTRY_PRIMARY_CITY[cname]
                break

    # No reliable location → tell the caller instead of silently searching Dubai
    if not city:
        return {'niche': niche, 'city': '', 'country': country or '',
                'modifiers': [], '_parse_failed': True}

    # Sanity check: if the "city" is actually a country name, use its primary city
    if city.lower() in COUNTRY_PRIMARY_CITY:
        city, country = COUNTRY_PRIMARY_CITY[city.lower()]

    result = {'niche': niche, 'city': city, 'country': country or '', 'modifiers': []}
    if state_full:
        result['_state_cities'] = US_STATE_TOP_CITIES.get(state_full, [city])
    return _fix_state_as_city(result)


# Bare country name → its primary business city (for "restaurants in Pakistan")
COUNTRY_PRIMARY_CITY = {
    'pakistan': ('Islamabad','PK'), 'india': ('Mumbai','IN'), 'bangladesh': ('Dhaka','BD'),
    'sri lanka': ('Colombo','LK'), 'nepal': ('Kathmandu','NP'),
    'uae': ('Dubai','AE'), 'united arab emirates': ('Dubai','AE'), 'emirates': ('Dubai','AE'),
    'saudi arabia': ('Riyadh','SA'), 'saudi': ('Riyadh','SA'), 'ksa': ('Riyadh','SA'),
    'singapore': ('Singapore','SG'), 'qatar': ('Doha','QA'), 'bahrain': ('Manama','BH'),
    'kuwait': ('Kuwait City','KW'), 'oman': ('Muscat','OM'), 'jordan': ('Amman','JO'),
    'lebanon': ('Beirut','LB'), 'egypt': ('Cairo','EG'), 'morocco': ('Casablanca','MA'),
    'usa': ('New York City','US'), 'united states': ('New York City','US'), 'america': ('New York City','US'),
    'uk': ('London','GB'), 'united kingdom': ('London','GB'), 'britain': ('London','GB'), 'england': ('London','GB'),
    'canada': ('Toronto','CA'), 'australia': ('Sydney','AU'), 'new zealand': ('Auckland','NZ'),
    'south africa': ('Johannesburg','ZA'), 'nigeria': ('Lagos','NG'), 'kenya': ('Nairobi','KE'),
    'malaysia': ('Kuala Lumpur','MY'), 'indonesia': ('Jakarta','ID'), 'philippines': ('Manila','PH'),
    'thailand': ('Bangkok','TH'), 'vietnam': ('Ho Chi Minh City','VN'), 'japan': ('Tokyo','JP'),
    'china': ('Shanghai','CN'), 'south korea': ('Seoul','KR'), 'korea': ('Seoul','KR'),
    'germany': ('Berlin','DE'), 'france': ('Paris','FR'), 'spain': ('Madrid','ES'), 'italy': ('Rome','IT'),
    'netherlands': ('Amsterdam','NL'), 'belgium': ('Brussels','BE'), 'switzerland': ('Zurich','CH'),
    'sweden': ('Stockholm','SE'), 'norway': ('Oslo','NO'), 'denmark': ('Copenhagen','DK'),
    'poland': ('Warsaw','PL'), 'turkey': ('Istanbul','TR'), 'brazil': ('Sao Paulo','BR'),
    'mexico': ('Mexico City','MX'), 'argentina': ('Buenos Aires','AR'), 'russia': ('Moscow','RU'),
    'ukraine': ('Kyiv','UA'),
}

# US state names/abbreviations → largest city (fixes "gyms in Texas" / "lawyers in Florida")
US_STATE_CITIES = {
    'alabama':'Birmingham','alaska':'Anchorage','arizona':'Phoenix','arkansas':'Little Rock',
    'california':'Los Angeles','colorado':'Denver','connecticut':'Hartford','delaware':'Wilmington',
    'florida':'Miami','georgia':'Atlanta','hawaii':'Honolulu','idaho':'Boise','illinois':'Chicago',
    'indiana':'Indianapolis','iowa':'Des Moines','kansas':'Wichita','kentucky':'Louisville',
    'louisiana':'New Orleans','maine':'Portland','maryland':'Baltimore','massachusetts':'Boston',
    'michigan':'Detroit','minnesota':'Minneapolis','mississippi':'Jackson','missouri':'Kansas City',
    'montana':'Billings','nebraska':'Omaha','nevada':'Las Vegas','new hampshire':'Manchester',
    'new jersey':'Newark','new mexico':'Albuquerque','new york':'New York City',
    'north carolina':'Charlotte','north dakota':'Fargo','ohio':'Columbus',
    'oklahoma':'Oklahoma City','oregon':'Portland','pennsylvania':'Philadelphia',
    'rhode island':'Providence','south carolina':'Columbia','south dakota':'Sioux Falls',
    'tennessee':'Nashville','texas':'Houston','utah':'Salt Lake City','vermont':'Burlington',
    'virginia':'Virginia Beach','washington':'Seattle','west virginia':'Charleston',
    'wisconsin':'Milwaukee','wyoming':'Cheyenne',
}

# When someone searches a whole US state ("pest control in New Jersey") we sweep
# the biggest cities so coverage isn't limited to one metro. ~5-8 cities each.
US_STATE_TOP_CITIES = {
    'alabama':['Birmingham','Montgomery','Mobile','Huntsville','Tuscaloosa'],
    'alaska':['Anchorage','Fairbanks','Juneau'],
    'arizona':['Phoenix','Tucson','Mesa','Chandler','Scottsdale','Tempe','Gilbert'],
    'arkansas':['Little Rock','Fayetteville','Fort Smith','Springdale'],
    'california':['Los Angeles','San Diego','San Jose','San Francisco','Fresno','Sacramento','Long Beach','Oakland'],
    'colorado':['Denver','Colorado Springs','Aurora','Fort Collins','Boulder'],
    'connecticut':['Bridgeport','New Haven','Hartford','Stamford','Waterbury'],
    'delaware':['Wilmington','Dover','Newark'],
    'florida':['Jacksonville','Miami','Tampa','Orlando','St. Petersburg','Fort Lauderdale','Tallahassee'],
    'georgia':['Atlanta','Augusta','Columbus','Savannah','Athens','Macon'],
    'hawaii':['Honolulu','Hilo','Kailua'],
    'idaho':['Boise','Meridian','Nampa','Idaho Falls'],
    'illinois':['Chicago','Aurora','Naperville','Joliet','Rockford','Springfield'],
    'indiana':['Indianapolis','Fort Wayne','Evansville','South Bend','Carmel'],
    'iowa':['Des Moines','Cedar Rapids','Davenport','Iowa City'],
    'kansas':['Wichita','Overland Park','Kansas City','Topeka','Olathe'],
    'kentucky':['Louisville','Lexington','Bowling Green','Owensboro'],
    'louisiana':['New Orleans','Baton Rouge','Shreveport','Lafayette'],
    'maine':['Portland','Lewiston','Bangor','Augusta'],
    'maryland':['Baltimore','Columbia','Germantown','Silver Spring','Rockville'],
    'massachusetts':['Boston','Worcester','Springfield','Cambridge','Lowell'],
    'michigan':['Detroit','Grand Rapids','Warren','Ann Arbor','Lansing','Flint'],
    'minnesota':['Minneapolis','Saint Paul','Rochester','Duluth','Bloomington'],
    'mississippi':['Jackson','Gulfport','Southaven','Hattiesburg'],
    'missouri':['Kansas City','Saint Louis','Springfield','Columbia','Independence'],
    'montana':['Billings','Missoula','Great Falls','Bozeman'],
    'nebraska':['Omaha','Lincoln','Bellevue','Grand Island'],
    'nevada':['Las Vegas','Henderson','Reno','North Las Vegas','Sparks'],
    'new hampshire':['Manchester','Nashua','Concord','Dover'],
    'new jersey':['Newark','Jersey City','Paterson','Elizabeth','Edison','Trenton','Camden'],
    'new mexico':['Albuquerque','Las Cruces','Santa Fe','Rio Rancho'],
    'new york':['New York City','Buffalo','Rochester','Yonkers','Syracuse','Albany'],
    'north carolina':['Charlotte','Raleigh','Greensboro','Durham','Winston-Salem','Fayetteville'],
    'north dakota':['Fargo','Bismarck','Grand Forks','Minot'],
    'ohio':['Columbus','Cleveland','Cincinnati','Toledo','Akron','Dayton'],
    'oklahoma':['Oklahoma City','Tulsa','Norman','Broken Arrow'],
    'oregon':['Portland','Salem','Eugene','Gresham','Hillsboro','Bend'],
    'pennsylvania':['Philadelphia','Pittsburgh','Allentown','Erie','Reading','Scranton'],
    'rhode island':['Providence','Warwick','Cranston','Pawtucket'],
    'south carolina':['Charleston','Columbia','North Charleston','Greenville','Myrtle Beach'],
    'south dakota':['Sioux Falls','Rapid City','Aberdeen'],
    'tennessee':['Nashville','Memphis','Knoxville','Chattanooga','Clarksville'],
    'texas':['Houston','San Antonio','Dallas','Austin','Fort Worth','El Paso','Arlington','Plano'],
    'utah':['Salt Lake City','West Valley City','Provo','Ogden','Sandy'],
    'vermont':['Burlington','Essex','Rutland'],
    'virginia':['Virginia Beach','Norfolk','Richmond','Arlington','Alexandria','Chesapeake'],
    'washington':['Seattle','Spokane','Tacoma','Vancouver','Bellevue','Everett'],
    'west virginia':['Charleston','Huntington','Morgantown','Parkersburg'],
    'wisconsin':['Milwaukee','Madison','Green Bay','Kenosha','Racine'],
    'wyoming':['Cheyenne','Casper','Laramie'],
}


def _fix_state_as_city(parsed):
    """If city is a US state name (or 'State City' compound), redirect to largest city.
    Also attaches _state_cities so the discovery engine can sweep the whole state."""
    city = (parsed.get('city') or '').strip()
    country = (parsed.get('country') or '').upper()
    if not city:
        return parsed
    city_lower = city.lower()
    # Handle "Florida Miami" → first word is a state, rest is the actual city
    parts = city_lower.split()
    if len(parts) >= 2 and parts[0] in US_STATE_CITIES:
        parsed['city'] = ' '.join(p.capitalize() for p in parts[1:])
        if not parsed.get('country'):
            parsed['country'] = 'US'
        return parsed
    # Whole city field is a state name — only when country is US or unset
    if city_lower in US_STATE_CITIES and country in ('US', 'USA', ''):
        parsed['_state_search'] = city  # keep original for logging
        parsed['city'] = US_STATE_CITIES[city_lower]
        parsed['country'] = 'US'
        parsed.setdefault('_state_cities', US_STATE_TOP_CITIES.get(city_lower, [parsed['city']]))
    return parsed
GEOCODE_CACHE = {}  # in-memory cache for same session

def geocode_city(city, country=''):
    """Convert any city name to lat/lng. Cached in memory."""
    key = f"{city.lower()}_{country.lower()}"
    if key in GEOCODE_CACHE:
        return GEOCODE_CACHE[key]

    # Check DB cache
    conn = db_conn(); cur = conn.cursor()
    cur.execute("SELECT content FROM assets WHERE asset_type='geocode' AND content LIKE %s LIMIT 1",
               (f'%{key}%',))
    cached = cur.fetchone()
    cur.close(); conn.close()
    if cached:
        try:
            data = json.loads(cached[0])
            GEOCODE_CACHE[key] = data
            return data
        except: pass

    # Call Google Geocoding API
    query = urllib.parse.quote(f'{city}, {country}' if country else city)
    url = f'https://maps.googleapis.com/maps/api/geocode/json?address={query}&key={GOOGLE_API_KEY}'
    try:
        resp = urllib.request.urlopen(url, timeout=10)
        data = json.loads(resp.read().decode())
        if data.get('results'):
            loc = data['results'][0]['geometry']['location']
            bounds = data['results'][0]['geometry'].get('bounds') or data['results'][0]['geometry'].get('viewport')

            # Estimate radius from bounds (default 15km)
            radius = 15000
            if bounds:
                ne = bounds['northeast']; sw = bounds['southwest']
                # Rough distance in meters
                lat_d = abs(ne['lat'] - sw['lat']) * 111000
                lng_d = abs(ne['lng'] - sw['lng']) * 111000 * 0.7
                radius = int(max(lat_d, lng_d) / 2)
                radius = max(5000, min(50000, radius))  # clamp 5-50km

            result = {
                'lat': loc['lat'],
                'lng': loc['lng'],
                'radius': radius,
                'formatted': data['results'][0].get('formatted_address', '')
            }
            GEOCODE_CACHE[key] = result
            _cache_geocode_db(key, result, 'google-geocode')
            return result
    except Exception as e:
        print(f'Geocode error (google): {e}')

    # ── FREE FALLBACK: Nominatim / OpenStreetMap (no API key, no billing) ──
    nomi = _geocode_nominatim(city, country)
    if nomi:
        GEOCODE_CACHE[key] = nomi
        _cache_geocode_db(key, nomi, 'nominatim')
        return nomi
    return None


def _cache_geocode_db(key, result, model):
    try:
        conn = db_conn(); cur = conn.cursor()
        cur.execute("INSERT INTO assets(asset_type, content, model_used) VALUES('geocode', %s, %s)",
                    (json.dumps({**result, 'key': key}), model))
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        print(f'Cache geocode error: {e}')


def _geocode_nominatim(city, country=''):
    """Free geocoding via OpenStreetMap Nominatim. No key needed.
    Respects their usage policy with a descriptive User-Agent + 1 req."""
    try:
        q = urllib.parse.quote(f'{city}, {country}' if country else city)
        url = (f'https://nominatim.openstreetmap.org/search?q={q}'
               f'&format=json&limit=1&addressdetails=0')
        req = urllib.request.Request(url, headers={
            'User-Agent': 'ControvaLeadGen/1.0 (lead discovery geocoder)'
        })
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode())
        if not data:
            return None
        item = data[0]
        lat, lng = float(item['lat']), float(item['lon'])
        radius = 15000
        bb = item.get('boundingbox')
        if bb and len(bb) == 4:
            south, north, west, east = (float(bb[0]), float(bb[1]),
                                        float(bb[2]), float(bb[3]))
            lat_d = abs(north - south) * 111000
            lng_d = abs(east - west) * 111000 * 0.7
            radius = int(max(lat_d, lng_d) / 2)
            radius = max(5000, min(50000, radius))
        return {'lat': lat, 'lng': lng, 'radius': radius,
                'formatted': item.get('display_name', f'{city}, {country}')}
    except Exception as e:
        print(f'Geocode error (nominatim): {e}')
        return None

# ──────────────────────────────────────────────────────────────
#  DISCOVERY (works with any city worldwide now)
# ──────────────────────────────────────────────────────────────
NICHE_MAP = {
    'restaurant':'restaurant','food':'restaurant','cafe':'cafe','coffee':'cafe',
    'salon':'hair_salon','hair':'hair_salon','beauty':'beauty_salon',
    'nail':'nail_salon','barbershop':'hair_care','barber':'hair_care',
    'hotel':'lodging','bar':'bar','pub':'bar','gym':'gym','fitness':'gym',
    'clinic':'doctor','pharmacy':'pharmacy','bakery':'bakery',
    'shop':'store','retail':'store','spa':'spa','dentist':'dentist',
    'laundry':'laundry','supermarket':'supermarket','grocery':'supermarket',
    'car_wash':'car_wash','garage':'car_repair','mechanic':'car_repair',
    'school':'school','tutor':'school','plumber':'plumber','electrician':'electrician',
}

def search_zone(place_type, lat, lng, radius):
    body = json.dumps({
        'includedTypes':[place_type],'maxResultCount':20,
        'locationRestriction':{'circle':{'center':{'latitude':lat,'longitude':lng},'radius':radius}}
    }).encode()
    req = urllib.request.Request(
        'https://places.googleapis.com/v1/places:searchNearby',
        data=body, method='POST',
        headers={'Content-Type':'application/json','X-Goog-Api-Key':GOOGLE_API_KEY,'X-Goog-FieldMask':FIELD_MASK}
    )
    resp = urllib.request.urlopen(req, timeout=15)
    return json.loads(resp.read().decode())

# ──────────────────────────────────────────────────────────────
#  MULTI-SOURCE DISCOVERY ENGINE  (v2)
#  - Google Places Text Search (New) + pageToken pagination → up to 60/query
#    (the old searchNearby was hard-capped at 20 and rejected non-place-type
#     niches like "marketing agency" → that's why many searches returned 0)
#  - Gemini-driven niche expansion (synonyms / subtypes / related / OSM tags)
#  - OpenStreetMap Overpass (free, no key) as a second source
#  - Round-based widening so "Find More" keeps surfacing NEW businesses
#  - Cross-source dedup on place_id / phone / domain
# ──────────────────────────────────────────────────────────────
PLACES_TEXT_URL  = 'https://places.googleapis.com/v1/places:searchText'
PLACES_CLASSIC_URL = 'https://maps.googleapis.com/maps/api/place/textsearch/json'
TEXT_FIELD_MASK = ('places.id,places.displayName,places.formattedAddress,places.location,'
                   'places.websiteUri,places.nationalPhoneNumber,places.rating,'
                   'places.userRatingCount,nextPageToken')
OVERPASS_ENDPOINTS = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
]
NICHE_EXPANSION_CACHE = {}
_PLACES_LAST_ERROR  = None   # set by _places_text_post on non-retryable failure


def _places_text_post(body, tries=3):
    log_api_usage('google_places', 'text_search_new')
    """POST to Places Text Search (New) with retry/backoff.
    Captures both HTTP errors and JSON-embedded errors (Google returns some
    errors as 200 OK with {error:{code,message}} in the body)."""
    global _PLACES_LAST_ERROR
    headers = {
        'Content-Type': 'application/json',
        'X-Goog-Api-Key': GOOGLE_API_KEY,
        'X-Goog-FieldMask': TEXT_FIELD_MASK,
    }
    delay = 2.0
    for attempt in range(tries):
        try:
            req = urllib.request.Request(PLACES_TEXT_URL, data=json.dumps(body).encode(),
                                         method='POST', headers=headers)
            resp = urllib.request.urlopen(req, timeout=20)
            data = json.loads(resp.read().decode())
            # Google sometimes returns 200 OK with an error body
            if 'error' in data:
                err = data['error']
                _PLACES_LAST_ERROR = f"API {err.get('code','?')}: {err.get('message','')[:200]}"
                print(f'TextSearch (New) JSON error: {_PLACES_LAST_ERROR}')
                return {}
            _PLACES_LAST_ERROR = None
            return data
        except Exception as e:
            code = getattr(e, 'code', None)
            if code in (400, 429) and attempt < tries - 1:
                time.sleep(delay); delay *= 2; continue
            err_body = ''
            try: err_body = e.read().decode()[:300]
            except: pass
            _PLACES_LAST_ERROR = f'HTTP {code}: {err_body or str(e)}'
            print(f'TextSearch (New) error: {_PLACES_LAST_ERROR}')
            return {}
    return {}


def _classic_text_search(text_query, lat, lng, radius_m, max_pages=3):
    log_api_usage('google_places', 'text_search_classic')
    """Classic Places Text Search (maps.googleapis.com) — works with any Maps key,
    no billing tier needed beyond basic Maps. Falls back from the New API on 403."""
    params = {'query': text_query, 'key': GOOGLE_API_KEY}
    if lat is not None and lng is not None:
        params['location'] = f'{lat},{lng}'
    if radius_m:
        params['radius'] = int(min(radius_m, 50000))
    results = []
    for _ in range(max_pages):
        url = PLACES_CLASSIC_URL + '?' + urllib.parse.urlencode(params)
        try:
            resp = urllib.request.urlopen(url, timeout=20)
            data = json.loads(resp.read().decode())
            status = data.get('status', '')
            if status not in ('OK', 'ZERO_RESULTS'):
                print(f'Classic Places error: {status} — {data.get("error_message","")}')
                break
            for p in data.get('results', []):
                loc = (p.get('geometry') or {}).get('location', {})
                results.append({
                    'source': 'google',
                    'source_id': p.get('place_id', ''),
                    'name': p.get('name', ''),
                    'phone': '',
                    'website': None,
                    'address': p.get('formatted_address', ''),
                    'lat': loc.get('lat'), 'lng': loc.get('lng'),
                    'rating': p.get('rating'),
                    'review_count': p.get('user_ratings_total', 0),
                })
            token = data.get('next_page_token')
            if not token:
                break
            params = {'pagetoken': token, 'key': GOOGLE_API_KEY}
            time.sleep(2.0)
        except Exception as e:
            print(f'Classic Places exception: {e}')
            break
    return results


def text_search_places(text_query, lat=None, lng=None, radius_m=None, rank='RELEVANCE', max_pages=3):
    """Google Places Text Search. Tries the New API first (up to 60 results via
    nextPageToken). If the New API returns a 403/auth error, falls back to the
    classic textsearch endpoint which works with any Maps API key."""
    global _PLACES_LAST_ERROR
    base = {'textQuery': text_query, 'pageSize': 20}
    if rank in ('DISTANCE', 'RELEVANCE'):
        base['rankPreference'] = rank
    if lat is not None and lng is not None and radius_m:
        base['locationRestriction'] = {'circle': {
            'center': {'latitude': float(lat), 'longitude': float(lng)},
            'radius': float(min(radius_m, 50000))}}
    results, token = [], None
    used_new_api = False
    for _page in range(max_pages):
        body = dict(base)
        if token:
            body['pageToken'] = token
        data = _places_text_post(body)
        places = data.get('places', [])
        if places:
            used_new_api = True
        results.extend(places)
        token = data.get('nextPageToken')
        if not token:
            break
        time.sleep(2.0)
    # Fall back to classic API on any error (billing, key issue, quota, etc.)
    if not results and _PLACES_LAST_ERROR:
        classic = _classic_text_search(text_query, lat, lng, radius_m, max_pages)
        if classic:
            _PLACES_LAST_ERROR = None
        return classic  # already normalized by _classic_text_search
    # New API results need normalization
    return [_norm_google_place(p) for p in results]


def gemini_expand_niche(niche, city, country=''):
    """Use Gemini to expand a niche into search variants (cached per niche+city).
    Returns synonyms / subtypes / related / osm_tags / adjacent_areas."""
    key = f'{niche.lower()}|{city.lower()}|{country.lower()}'
    if key in NICHE_EXPANSION_CACHE:
        return NICHE_EXPANSION_CACHE[key]
    data = {'synonyms': [], 'subtypes': [], 'related': [], 'osm_tags': [], 'adjacent_areas': []}
    prompt = f"""You expand a business niche into search variants for a B2B lead-gen tool.
Niche: "{niche}"   Location: {city}, {country}

Return ONLY valid JSON:
{{"synonyms":["..."],"subtypes":["..."],"related":["..."],"osm_tags":["amenity=dentist"],"adjacent_areas":["..."]}}

Rules:
- synonyms: direct equivalents (dentist -> dental clinic, dental surgery)
- subtypes: narrower kinds (orthodontist, cosmetic dentist, pediatric dentist)
- related: adjacent business types serving similar customers (dental lab)
- osm_tags: valid OpenStreetMap key=value tags for this niche. Examples:
  amenity=dentist, healthcare=dentist, amenity=restaurant, amenity=cafe,
  shop=hairdresser, shop=beauty, office=lawyer, craft=plumber, craft=electrician,
  leisure=fitness_centre, amenity=pharmacy, shop=car_repair, amenity=clinic
- adjacent_areas: up to 6 suburbs / nearby towns of {city}
Max 8 items per list. Keep terms short."""
    out = gemini_call(prompt, 700)
    if out:
        try:
            m = re.search(r'\{[\s\S]*\}', out)
            if m:
                parsed = json.loads(m.group())
                for k in data:
                    v = parsed.get(k)
                    if isinstance(v, list):
                        data[k] = [str(x).strip() for x in v if str(x).strip()][:8]
        except Exception as e:
            print(f'Niche expansion parse error: {e}')
    NICHE_EXPANSION_CACHE[key] = data
    return data


def overpass_search(osm_tags, lat, lng, radius_m=8000, timeout=50):
    """Free local-business search via OpenStreetMap Overpass API. No key required.
    osm_tags: list like ['amenity=dentist','healthcare=dentist']."""
    clauses = []
    for tag in (osm_tags or []):
        if '=' not in tag:
            continue
        k, v = tag.split('=', 1)
        k = re.sub(r'[^a-zA-Z0-9_:]', '', k)
        v = re.sub(r'["\\]', '', v)
        if k and v:
            clauses.append(f'nwr["{k}"="{v}"](around:{int(radius_m)},{lat},{lng});')
    if not clauses:
        return []
    query = f'[out:json][timeout:{timeout}];\n(\n' + '\n'.join(clauses) + '\n);\nout center tags;'
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            req = urllib.request.Request(
                endpoint, data=urllib.parse.urlencode({'data': query}).encode(),
                headers={'User-Agent': 'controva-leadgen/1.0 (lead discovery)'})
            resp = urllib.request.urlopen(req, timeout=timeout + 25)
            data = json.loads(resp.read().decode())
            out = []
            for el in data.get('elements', []):
                t = el.get('tags', {})
                name = t.get('name')
                if not name:
                    continue
                if el.get('type') == 'node':
                    elat, elng = el.get('lat'), el.get('lon')
                else:
                    c = el.get('center') or {}
                    elat, elng = c.get('lat'), c.get('lon')
                addr_parts = [t.get('addr:housenumber'), t.get('addr:street'),
                              t.get('addr:city'), t.get('addr:postcode')]
                out.append({
                    'source': 'osm',
                    'source_id': f"osm_{el.get('type')}_{el.get('id')}",
                    'name': name,
                    'phone': t.get('phone') or t.get('contact:phone') or '',
                    'website': t.get('website') or t.get('contact:website') or t.get('url') or None,
                    'address': ', '.join(p for p in addr_parts if p),
                    'lat': elat, 'lng': elng, 'rating': None, 'review_count': 0,
                })
            return out
        except Exception as e:
            print(f'Overpass error ({endpoint}): {e}')
            time.sleep(1)
    return []


def here_search(text_query, lat, lng, radius_m=8000, limit=100):
    """HERE Maps Geocoding & Search API — Discover endpoint.
    Returns up to 100 POI results per call.  Free 250k transactions/month.
    Skipped silently when HERE_API_KEY is not set.
    Sign up: developer.here.com (no credit card for free tier)."""
    if not HERE_API_KEY:
        return []
    params = urllib.parse.urlencode({
        'q': text_query,
        'at': f'{lat},{lng}',
        'in': f'circle:{lat},{lng};r={int(min(radius_m, 100000))}',
        'limit': min(int(limit), 100),
        'apiKey': HERE_API_KEY,
    })
    url = f'https://discover.search.hereapi.com/v1/discover?{params}'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'controva-leadgen/1.0'})
        resp = urllib.request.urlopen(req, timeout=20)
        data = json.loads(resp.read().decode())
        out = []
        for item in data.get('items', []):
            pos = item.get('position', {})
            addr = item.get('address', {})
            contacts = (item.get('contacts') or [{}])[0]
            phone = ''
            phones = contacts.get('phone') or []
            if phones:
                phone = phones[0].get('value', '')
            www = contacts.get('www') or []
            website = www[0].get('value', '') if www else None
            here_id = item.get('id', '')
            out.append({
                'source': 'here',
                'source_id': f'here_{here_id}',
                'name': item.get('title', ''),
                'phone': phone,
                'website': website or None,
                'address': addr.get('label', ''),
                'lat': pos.get('lat'), 'lng': pos.get('lng'),
                'rating': None, 'review_count': 0,
            })
        return out
    except Exception as e:
        print(f'HERE search error: {e}')
        return []


def norm_phone(phone):
    """Loose cross-source phone key = last 10 digits."""
    if not phone:
        return ''
    d = re.sub(r'\D', '', str(phone))
    return d[-10:] if len(d) >= 10 else d


def norm_domain(website):
    """Registrable-ish domain, stripped of scheme/www/path."""
    if not website:
        return ''
    w = str(website).lower().strip()
    w = re.sub(r'^https?://', '', w)
    w = re.sub(r'^www\.', '', w)
    return w.split('/')[0].split('?')[0]


def _norm_google_place(p):
    name = (p.get('displayName') or {}).get('text', 'Unknown')
    loc = p.get('location') or {}
    return {
        'source': 'google',
        'source_id': p.get('id', ''),
        'name': name,
        'phone': p.get('nationalPhoneNumber', '') or '',
        'website': p.get('websiteUri') or None,
        'address': p.get('formattedAddress', '') or '',
        'lat': loc.get('latitude'), 'lng': loc.get('longitude'),
        'rating': p.get('rating'), 'review_count': p.get('userRatingCount', 0),
    }


def build_tiles(lat, lng, city_radius, rnd):
    """Concentric-ring tiling. Round 0 = one city-wide query; each extra round
    adds a finer/wider ring so every 'Find More' reaches businesses the previous
    runs never queried. Hard-capped so a single run never explodes API cost."""
    import math
    city_radius = max(3000, min(int(city_radius), 50000))
    if rnd <= 0:
        return [(lat, lng, city_radius)]
    tiles = [(lat, lng, city_radius)]
    tile_r = max(2500, int(city_radius * 0.55))
    ring_specs = [(6, 0.55), (10, 0.9), (12, 1.25)][:min(rnd, 3)]
    for (count, frac) in ring_specs:
        dist = city_radius * frac
        for k in range(count):
            ang = 2 * math.pi * k / count
            dlat = (dist * math.cos(ang)) / 111320.0
            dlng = (dist * math.sin(ang)) / (111320.0 * max(0.2, math.cos(math.radians(lat))))
            tiles.append((lat + dlat, lng + dlng, tile_r))
    return tiles[:25]


def ensure_discovery_tables():
    """Self-healing schema for discovery state + dedup columns (idempotent).
    Runs at discovery time so it works even if the SQL migration didn't."""
    try:
        conn = db_conn(); cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS discovery_state (
                id          SERIAL PRIMARY KEY,
                niche       VARCHAR(200) NOT NULL,
                city        VARCHAR(200) NOT NULL,
                country     VARCHAR(200) NOT NULL DEFAULT '',
                round       INTEGER NOT NULL DEFAULT 0,
                exhausted   BOOLEAN NOT NULL DEFAULT FALSE,
                total_found INTEGER NOT NULL DEFAULT 0,
                updated_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                UNIQUE(niche, city, country)
            )""")
        cur.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS phone_norm VARCHAR(20)")
        cur.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS domain VARCHAR(255)")
        cur.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS website_verified BOOLEAN DEFAULT NULL")
        cur.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS search_batch_id VARCHAR(50)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_leads_phone_norm ON leads(phone_norm)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_leads_domain ON leads(domain)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_leads_website_verified ON leads(website_verified)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_leads_search_batch_id ON leads(search_batch_id)")
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        print(f'ensure_discovery_tables error: {e}')

def ensure_intent_tables():
    """Self-healing schema for the Intent Engine (mirrors migrations/001_intent.sql).
    Without this, intent_search() silently fails every INSERT — the leads
    table lacks lead_type and intent_signals doesn't exist at all until the
    .sql migration is manually applied, which is easy to miss on a fresh
    or existing install."""
    try:
        conn = db_conn(); cur = conn.cursor()
        cur.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS lead_type VARCHAR(20)")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS intent_signals (
                id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                lead_id            UUID REFERENCES leads(id) ON DELETE CASCADE,
                direction          VARCHAR(20) NOT NULL,
                source             VARCHAR(50),
                source_url         TEXT,
                raw_snippet        TEXT,
                posted_at          TIMESTAMP WITH TIME ZONE,
                confidence         SMALLINT DEFAULT 0,
                role_or_service    VARCHAR(300),
                location_hint      VARCHAR(200),
                contact_hint       TEXT,
                is_active          BOOLEAN DEFAULT TRUE,
                raw_classification JSONB,
                created_at         TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )""")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_intent_lead_id    ON intent_signals(lead_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_intent_direction  ON intent_signals(direction)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_intent_confidence ON intent_signals(confidence DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_intent_active     ON intent_signals(is_active)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_leads_type        ON leads(lead_type)")
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        print(f'ensure_intent_tables error: {e}')


def discover_leads_smart(niche, city, country='', original_query='',
                         filter_mode='no_website', density='standard',
                         find_more=False, job_id=None, extra_cities=None, tenant_id=None):
    """Multi-source, round-based discovery.

    filter_mode  : 'no_website' | 'with_website' | 'all'
    density      : 'low' | 'standard' | 'high' (how aggressive each round starts)
    find_more    : advance to the next round → wider radius, more synonyms, +OSM
    extra_cities : list of cities to sweep (used for whole-state searches)
    job_id      : if set, live progress is written to JOBS[job_id]
    tenant_id   : link discovered leads to this tenant
    """
    ensure_discovery_tables()

    def _log(msg, pct=None):
        if job_id and job_id in JOBS:
            JOBS[job_id]['log'].append(msg)
            if pct is not None:
                JOBS[job_id]['progress'] = int(pct)

    geo = geocode_city(city, country)
    if not geo:
        return [], 'geocode_failed'
    lat, lng, base_rad = geo['lat'], geo['lng'], geo['radius']

    # ── load / advance the round counter for this (niche, city) ──
    cc = (country or '').upper()
    conn = db_conn(); cur = conn.cursor()
    cur.execute("SELECT round, total_found FROM discovery_state WHERE niche=%s AND city=%s AND country=%s",
                (niche.lower(), city.lower(), cc))
    row = cur.fetchone()
    if row:
        rnd = row[0] + 1 if find_more else row[0]
    else:
        rnd = 0
        cur.execute("""INSERT INTO discovery_state(niche,city,country,round)
                       VALUES(%s,%s,%s,0) ON CONFLICT (niche,city,country) DO NOTHING""",
                    (niche.lower(), city.lower(), cc))
        conn.commit()
    cur.close(); conn.close()

    # density sets how much we widen even on the first run
    aggression = {'low': 0, 'standard': 1, 'high': 2}.get(density, 1)
    eff_round = rnd + aggression

    # ── build the query-term list (round controls how deep we go) ──
    exp = gemini_expand_niche(niche, city, country)
    ordered = [niche] + exp['synonyms'] + exp['subtypes'] + exp['related']
    seen_t, terms = set(), []
    for t in ordered:
        tl = t.lower().strip()
        if tl and tl not in seen_t:
            seen_t.add(tl); terms.append(t)
    term_count = min(len(terms), 3 + eff_round)
    round_terms = terms[:term_count] or [niche]

    # ── Build the search areas (tiles) ─────────────────────────
    state_sweep = bool(extra_cities and len(extra_cities) > 1)
    if state_sweep:
        # Whole-state search: one search area per major city. Each round widens
        # every city's radius so "Find More" keeps reaching new businesses.
        widen = 1.0 + 0.35 * eff_round
        tiles, swept = [], []
        for cname in extra_cities:
            g = geocode_city(cname, country)
            if g:
                tiles.append((g['lat'], g['lng'], min(int(g['radius'] * widen), 25000)))
                swept.append(cname)
        if not tiles:
            tiles = build_tiles(lat, lng, base_rad, eff_round)  # fallback
            state_sweep = False
    else:
        tiles = build_tiles(lat, lng, base_rad, eff_round)

    # cost guard: never exceed ~36 searches in a single run
    MAX_SEARCHES = 36
    if len(tiles) * len(round_terms) > MAX_SEARCHES:
        tiles = tiles[:max(1, MAX_SEARCHES // len(round_terms))]
    use_osm  = eff_round >= 1 and bool(exp['osm_tags'])
    use_here = bool(HERE_API_KEY)  # runs per-term on primary tile; 100 results/call

    sources_str = 'Google Places'
    if use_osm:  sources_str += ' + OpenStreetMap'
    if use_here: sources_str += ' + HERE Maps'
    if state_sweep:
        _log(f'State-wide sweep: {len(tiles)} cities ({", ".join(swept[:len(tiles)])}) · '
             f'{len(round_terms)} search terms · sources: {sources_str}')
    else:
        _log(f'Round {rnd} · {len(round_terms)} search terms · {len(tiles)} map tiles · sources: {sources_str}')
    if len(round_terms) > 1:
        _log(f'Terms: {", ".join(round_terms)}')

    # ── harvest (collect raw, dedup in-memory by source_id) ──
    raw = {}
    here_units = len(round_terms) if use_here else 0
    total_units = len(tiles) * len(round_terms) + (len(tiles) if use_osm else 0) + here_units
    done_units = 0
    def _cancelled():
        return job_id and JOBS.get(job_id, {}).get('cancelled')

    for (tlat, tlng, trad) in tiles:
        if _cancelled():
            _log('Search stopped by user.', pct=100)
            break
        for term in round_terms:
            if _cancelled():
                break
            try:
                for p in text_search_places(term, tlat, tlng, trad):
                    pid = p.get('source_id') or p.get('id')
                    if pid and pid not in raw:
                        raw[pid] = p  # already normalized by text_search_places
            except Exception as e:
                print(f'text_search error: {e}')
            done_units += 1
            if done_units % 2 == 0 or done_units >= total_units:
                _log(f'Searched {done_units}/{total_units} · {len(raw)} candidates so far',
                     pct=min(80, done_units / max(1, total_units) * 80))
        if use_osm and not _cancelled():
            try:
                for o in overpass_search(exp['osm_tags'], tlat, tlng, int(trad * 1.2)):
                    if o['source_id'] not in raw:
                        raw[o['source_id']] = o
            except Exception as e:
                print(f'overpass error: {e}')
            done_units += 1

    # HERE Maps: one call per term on the primary tile (100 results each)
    if use_here and not _cancelled():
        _log('Searching HERE Maps…')
        for term in round_terms:
            try:
                for h in here_search(term, lat, lng, int(base_rad)):
                    if h['source_id'] not in raw:
                        raw[h['source_id']] = h
            except Exception as e:
                print(f'HERE error for "{term}": {e}')
            done_units += 1
            _log(f'Searched {done_units}/{total_units} · {len(raw)} candidates so far',
                 pct=min(85, done_units / max(1, total_units) * 85))

    if len(raw) == 0 and _PLACES_LAST_ERROR:
        _log(f'Google Places API error: {_PLACES_LAST_ERROR}. '
             f'Check your Google API key has Places API enabled in Google Cloud Console.', pct=88)
    _log(f'Collected {len(raw)} unique candidates. De-duplicating against your database…', pct=88)

    # ── dedup against DB (place_id / phone / domain) + insert NEW ──
    new_leads = []
    filtered_by_website = 0
    already_in_db = 0
    conn = db_conn(); cur = conn.cursor()
    for cand in raw.values():
        website = cand.get('website')
        has_website = bool(website)
        if filter_mode == 'no_website' and has_website:
            filtered_by_website += 1
            continue
        if filter_mode == 'with_website' and not has_website:
            filtered_by_website += 1
            continue
        pid = cand.get('source_id')
        if not pid:
            continue
        pn = norm_phone(cand.get('phone'))
        dom = norm_domain(website)
        try:
            cur.execute("""SELECT id FROM leads
                           WHERE place_id=%s
                              OR (%s <> '' AND phone_norm=%s)
                              OR (%s <> '' AND domain=%s)
                           LIMIT 1""",
                        (pid, pn, pn, dom, dom))
            row = cur.fetchone()
            if row:
                lead_id = row[0]
                already_in_db += 1
            else:
                cur.execute("""INSERT INTO leads(place_id,business_name,niche,city,country,address,phone,
                              website,latitude,longitude,google_rating,review_count,status,source,phone_norm,domain,search_batch_id)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'discovered',%s,%s,%s,%s)
                    ON CONFLICT (place_id) DO NOTHING RETURNING id""",
                    (pid, (cand.get('name') or 'Unknown')[:480], niche.lower(), city, country,
                     cand.get('address', ''), cand.get('phone', ''), website,
                     cand.get('lat'), cand.get('lng'), cand.get('rating'),
                     cand.get('review_count', 0), cand.get('source', 'google'),
                     pn or None, dom or None, job_id))
                row = cur.fetchone()
                if row:
                    lead_id = row[0]
                    new_leads.append({
                        'place_id': pid, 'business_name': cand.get('name', 'Unknown'),
                        'niche': niche, 'city': city, 'phone': cand.get('phone', ''),
                        'has_website': has_website, 'website': website,
                        'address': cand.get('address', ''), 'source': cand.get('source', 'google'),
                    })
                else:
                    continue # Race condition, another thread inserted it
                    
            if tenant_id:
                cur.execute("INSERT INTO tenant_leads(tenant_id, lead_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (tenant_id, lead_id))
            conn.commit()
        except Exception as e:
            print(f'dedup/insert error: {e}')
            conn.rollback()
    cur.close(); conn.close()

    # ── persist round state; mark exhausted if a widening round found little ──
    exhausted = find_more and len(new_leads) < 3
    try:
        conn = db_conn(); cur = conn.cursor()
        cur.execute("""UPDATE discovery_state
                       SET round=%s, exhausted=%s, total_found=total_found+%s, updated_at=NOW()
                       WHERE niche=%s AND city=%s AND country=%s""",
                    (rnd, exhausted, len(new_leads), niche.lower(), city.lower(), cc))
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        print(f'discovery_state update error: {e}')

    total_found = len(raw)
    if len(new_leads) == 0 and total_found > 0:
        if filtered_by_website > 0 and already_in_db == 0:
            why = 'have websites' if filter_mode == 'no_website' else 'have no website'
            _log(f'Found {total_found} businesses but all were filtered out '
                 f'({filtered_by_website} {why}). Switch the Website Filter to "All" to capture them.', pct=100)
        elif already_in_db > 0 and filtered_by_website == 0:
            _log(f'Found {total_found} businesses — all {already_in_db} already in your database. '
                 f'Click "Find More Leads" to search a wider area.', pct=100)
        else:
            _log(f'Found {total_found} businesses: {filtered_by_website} filtered by website, '
                 f'{already_in_db} already in database. Try "All" filter or "Find More Leads".', pct=100)
    else:
        _log(f'Done — {len(new_leads)} new leads added'
             + (f' ({already_in_db} already in DB, {filtered_by_website} filtered)' if already_in_db or filtered_by_website else '')
             + f' · round {rnd}.', pct=100)
    return new_leads, ('exhausted' if exhausted else 'success')


# ──────────────────────────────────────────────────────────────
#  ENRICHMENT - Provider toggle (Serper / Oxylabs / Both)
# ──────────────────────────────────────────────────────────────
def _serper_request(url, body, timeout, label, retries=2):
    """POST to a Serper endpoint with retries. Serper occasionally returns a
    transient 4xx/5xx (rate-limit blip, backend hiccup) that has nothing to
    do with the query itself — without a retry, that gets silently treated
    as 'this product doesn't exist', which is exactly the false-negative
    risk that undermines accuracy. Retrying once or twice catches those
    blips instead of reporting them as real zero-result findings."""
    last_err = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=body, method='POST',
                headers={'X-API-KEY': SERPER_KEY, 'Content-Type': 'application/json'})
            resp = urllib.request.urlopen(req, timeout=timeout)
            return json.loads(resp.read().decode())
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(0.8 * (attempt + 1))
    print(f'{label} error (after {retries+1} attempts): {last_err}')
    return {}

def serper_search(query, num=10):
    log_api_usage('serper', 'search', meta=query[:200])
    body = json.dumps({'q': query, 'num': num}).encode()
    return _serper_request('https://google.serper.dev/search', body, 15, 'Serper')

def oxylabs_scrape(url, output='markdown'):
    log_api_usage('oxylabs', 'scrape')
    if not OXYLABS: return None
    try:
        result = OXYLABS.scrape(url=url, output_format=output, render_javascript=False)
        if result and result.data:
            return result.data if isinstance(result.data, str) else json.dumps(result.data)
    except Exception as e:
        print(f'Oxylabs scrape error: {e}')
    return None

# Markers that identify bot-check / error pages. Sites like eBay and Amazon
# return these with enough text to pass a naive length check, which used to
# make smart_scrape treat a "403 Forbidden" page as a successful scrape.
_BLOCK_MARKERS = [
    'pardon our interruption', 'something went wrong on our end',
    'target url returned error 4', 'target url returned error 5',
    'access denied', 'are you a robot', 'robot check', 'captcha',
    'checking your browser', 'verify you are a human', 'request blocked',
    'error page | ebay', 'enable javascript and cookies to continue',
]

def _scrape_ok(text, min_len=300):
    """A scrape only counts if it's long enough AND isn't a bot-check page."""
    if not text or len(text.strip()) < min_len:
        return False
    head = text[:3000].lower()
    return not any(m in head for m in _BLOCK_MARKERS)

def smart_scrape(url, timeout=20, prefer_direct=False):
    """
    Multi-tier URL-to-markdown scraper. Falls through cheaper/free tiers first.
    Tier 0: Direct fetch      (free, only when prefer_direct=True)
    Tier 1: Jina Reader       (free, no key, unlimited)
    Tier 2: Crawl4AI          (self-hosted Docker, free)
    Tier 3: ScrapingBee       (free 1k req/mo — set SCRAPINGBEE_KEY)
    Tier 4: ZenRows           (free 1k req/mo — set ZENROWS_KEY)
    Tier 5: Scrapingdog       (free 1k req/mo — set SCRAPINGDOG_KEY)
    Tier 6: Firecrawl         (free 500 req/mo — set FIRECRAWL_KEY)
    Tier 7: Oxylabs           (paid, powerful residential proxies)
    Every tier's output is validated with _scrape_ok so a blocked/error page
    falls through to the next tier instead of being returned as a result.
    """
    # ── Tier 0: direct fetch with browser headers ─────────────────────────
    # Opt-in (prefer_direct) because it returns plain text without link URLs,
    # which the enrichment pipeline needs from Jina's markdown.
    if prefer_direct:
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
            })
            resp = urllib.request.urlopen(req, timeout=min(timeout, 12))
            html = resp.read().decode('utf-8', errors='replace')
            mailtos = ' '.join(set(re.findall(r'mailto:([^"\'>\s?]+)', html)))
            text = re.sub(r'<script[\s\S]*?</script>|<style[\s\S]*?</style>', ' ', html)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            if mailtos: text += ' ' + mailtos
            if _scrape_ok(text):
                print(f'smart_scrape[direct]: OK  {url[:70]}')
                return text
        except Exception as e:
            print(f'smart_scrape[direct]: {e}')

    # ── Tier 1: Jina Reader ───────────────────────────────────────────────
    try:
        jina_url = 'https://r.jina.ai/' + url
        req = urllib.request.Request(jina_url, headers={
            'Accept': 'text/plain',
            'X-Return-Format': 'markdown',
            'User-Agent': 'Mozilla/5.0 LeadGen/1.0',
        })
        resp = urllib.request.urlopen(req, timeout=timeout)
        text = resp.read().decode('utf-8', errors='replace')
        if _scrape_ok(text):
            print(f'smart_scrape[Jina]: OK  {url[:70]}')
            return text
    except Exception as e:
        print(f'smart_scrape[Jina]: {e}')

    # ── Tier 2: Crawl4AI ─────────────────────────────────────────────────
    # Current Docker image API (0.7.x) is synchronous: POST /crawl with a
    # 'urls' array returns results immediately — no more task_id polling,
    # and markdown comes back as an object ({'raw_markdown': ...}), not a string.
    try:
        body = json.dumps({
            'urls': [url],
            'crawler_config': {'word_count_threshold': 10},
        }).encode()
        req = urllib.request.Request(
            CRAWL4AI_URL + '/crawl', data=body, method='POST',
            headers={'Content-Type': 'application/json',
                     'Authorization': 'Bearer ' + CRAWL4AI_TOKEN}
        )
        resp = urllib.request.urlopen(req, timeout=timeout)
        data = json.loads(resp.read().decode())
        results = data.get('results') or []
        if results:
            md_field = results[0].get('markdown')
            md = md_field.get('raw_markdown', '') if isinstance(md_field, dict) else (md_field or '')
            if _scrape_ok(md):
                print(f'smart_scrape[Crawl4AI]: OK  {url[:70]}')
                return md
    except Exception as e:
        print(f'smart_scrape[Crawl4AI]: {e}')

    # ── Tier 3: ScrapingBee ───────────────────────────────────────────────
    if SCRAPINGBEE_KEY:
        try:
            sb_url = ('https://app.scrapingbee.com/api/v1/?api_key=' + SCRAPINGBEE_KEY
                      + '&url=' + urllib.parse.quote(url, safe='')
                      + '&render_js=False&return_page_source=True')
            resp = urllib.request.urlopen(sb_url, timeout=30)
            html = resp.read().decode('utf-8', errors='replace')
            text = re.sub(r'<[^>]+>', ' ', html)
            text = re.sub(r'\s+', ' ', text).strip()
            if _scrape_ok(text):
                print(f'smart_scrape[ScrapingBee]: OK  {url[:70]}')
                return text
        except Exception as e:
            print(f'smart_scrape[ScrapingBee]: {e}')

    # ── Tier 4: ZenRows ──────────────────────────────────────────────────
    if ZENROWS_KEY:
        try:
            zr_url = ('https://api.zenrows.com/v1/?apikey=' + ZENROWS_KEY
                      + '&url=' + urllib.parse.quote(url, safe=''))
            resp = urllib.request.urlopen(zr_url, timeout=30)
            html = resp.read().decode('utf-8', errors='replace')
            text = re.sub(r'<[^>]+>', ' ', html)
            text = re.sub(r'\s+', ' ', text).strip()
            if _scrape_ok(text):
                print(f'smart_scrape[ZenRows]: OK  {url[:70]}')
                return text
        except Exception as e:
            print(f'smart_scrape[ZenRows]: {e}')

    # ── Tier 5: Scrapingdog ───────────────────────────────────────────────
    if SCRAPINGDOG_KEY:
        try:
            sd_url = ('https://api.scrapingdog.com/scrape?api_key=' + SCRAPINGDOG_KEY
                      + '&url=' + urllib.parse.quote(url, safe='') + '&dynamic=false')
            resp = urllib.request.urlopen(sd_url, timeout=30)
            html = resp.read().decode('utf-8', errors='replace')
            text = re.sub(r'<[^>]+>', ' ', html)
            text = re.sub(r'\s+', ' ', text).strip()
            if _scrape_ok(text):
                print(f'smart_scrape[Scrapingdog]: OK  {url[:70]}')
                return text
        except Exception as e:
            print(f'smart_scrape[Scrapingdog]: {e}')

    # ── Tier 6: Firecrawl ────────────────────────────────────────────────
    if FIRECRAWL_KEY:
        try:
            fc_body = json.dumps({'url': url, 'formats': ['markdown']}).encode()
            fc_req = urllib.request.Request(
                'https://api.firecrawl.dev/v1/scrape', data=fc_body, method='POST',
                headers={'Authorization': 'Bearer ' + FIRECRAWL_KEY,
                         'Content-Type': 'application/json'}
            )
            fc_resp = urllib.request.urlopen(fc_req, timeout=30)
            fc_data = json.loads(fc_resp.read().decode())
            md = fc_data.get('data', {}).get('markdown', '')
            if _scrape_ok(md):
                print(f'smart_scrape[Firecrawl]: OK  {url[:70]}')
                return md
        except Exception as e:
            print(f'smart_scrape[Firecrawl]: {e}')

    # ── Tier 7: Oxylabs (paid) ────────────────────────────────────────────
    if OXYLABS:
        try:
            text = oxylabs_scrape(url, 'markdown')
            if _scrape_ok(text):
                print(f'smart_scrape[Oxylabs]: OK  {url[:70]}')
                return text
        except Exception as e:
            print(f'smart_scrape[Oxylabs]: {e}')

    print(f'smart_scrape: ALL tiers failed for {url[:70]}')
    return None

def enrich_with_free_scrape(business_name, city):
    """Completely free enrichment: guess domain → scrape with Jina → extract emails/socials.
    No Serper or Oxylabs credits consumed."""
    result = {'email': None, 'linkedin_url': None, 'facebook_url': None,
              'instagram_url': None, 'owner_name': None}

    # Build candidate domain guesses from the business name
    clean = re.sub(r"[^a-z0-9]+", '', business_name.lower())[:30]
    city_clean = re.sub(r"[^a-z0-9]+", '', city.lower())[:15] if city else ''
    domains = []
    if clean:
        domains = [
            f'{clean}.com',
            f'{clean}business.com',
        ]
        if city_clean:
            domains.append(f'{clean}{city_clean}.com')

    # Also try DuckDuckGo instant-answer (free, no key)
    try:
        ddg_q = urllib.parse.quote(f'{business_name} {city} official site')
        req = urllib.request.Request(
            f'https://api.duckduckgo.com/?q={ddg_q}&format=json&no_redirect=1',
            headers={'User-Agent': 'Mozilla/5.0 LeadGen/1.0'}
        )
        ddg = json.loads(urllib.request.urlopen(req, timeout=8).read().decode())
        ab = ddg.get('AbstractURL') or ddg.get('OfficialWebsite') or ''
        if ab and ab.startswith('http'):
            m = re.match(r'https?://([^/]+)', ab)
            if m:
                domains.insert(0, m.group(1))
    except Exception:
        pass

    seen = set()
    for dom in domains:
        if dom in seen: continue
        seen.add(dom)
        for path in ['', '/contact', '/about']:
            url = f'https://{dom}{path}'
            try:
                jina_url = 'https://r.jina.ai/' + url
                req = urllib.request.Request(jina_url, headers={
                    'Accept': 'text/plain', 'X-Return-Format': 'markdown',
                    'User-Agent': 'Mozilla/5.0 LeadGen/1.0',
                })
                text = urllib.request.urlopen(req, timeout=12).read().decode('utf-8', errors='replace')
                if not _scrape_ok(text, min_len=100): continue

                emails = extract_emails(text)
                if emails and not result['email']:
                    result['email'] = emails[0]

                for link in re.findall(r'https?://[^\s\)"\'>]+', text):
                    if 'linkedin.com/in/' in link and not result['linkedin_url']:
                        result['linkedin_url'] = link.split('?')[0]
                    if 'facebook.com/' in link and '/pages/' not in link and not result['facebook_url']:
                        result['facebook_url'] = link.split('?')[0]
                    if 'instagram.com/' in link and not result['instagram_url']:
                        result['instagram_url'] = link.split('?')[0]

                if result['email']:
                    return result  # good enough, stop early
            except Exception:
                pass

    return result


def enrich_with_serper(business_name, city, niche):
    """Find LinkedIn + Facebook + email via Serper."""
    result = {'email': None, 'linkedin_url': None, 'facebook_url': None,
              'instagram_url': None, 'owner_name': None}

    queries = [
        f'"{business_name}" {city} contact email phone',
        f'site:linkedin.com/in "{business_name}" {city} (owner OR founder OR CEO)',
    ]
    for q in queries:
        data = serper_search(q, 8)
        for item in data.get('organic', []):
            link = item.get('link', '')
            snippet = item.get('snippet', '')
            title = item.get('title', '')

            if 'linkedin.com/in/' in link and not result['linkedin_url']:
                result['linkedin_url'] = link.split('?')[0]
                m = re.match(r'^([^\-|]+?)\s*[\-|]', title)
                if m: result['owner_name'] = m.group(1).strip()

            if 'facebook.com/' in link and '/pages/' not in link and not result['facebook_url']:
                result['facebook_url'] = link.split('?')[0]

            if 'instagram.com/' in link and not result['instagram_url']:
                result['instagram_url'] = link.split('?')[0]

            emails = extract_emails(snippet + ' ' + title)
            if emails and not result['email']:
                result['email'] = emails[0]
    return result

def enrich_with_oxylabs(business_name, city):
    """Deep email search via Oxylabs."""
    if not OXYLABS: return {'email': None}
    query = f'{business_name} {city} contact email phone OR @gmail OR @hotmail'
    url = f'https://www.google.com/search?q={urllib.parse.quote(query)}'
    text = oxylabs_scrape(url, 'markdown')
    if not text: return {'email': None}
    emails = extract_emails(text)
    return {'email': emails[0] if emails else None, 'all_emails': emails}

def enrich_with_email_permutator(business_name, owner_name='', domain=''):
    """Free Hunter-style pattern generator — STRICTLY limited to domains we
    actually observed for this business (scraped website/social page).
    Never guesses domains: inventing businessname.com produced addresses that
    belonged to unrelated companies and wrecked bounce rates."""
    domain = norm_domain(domain) if domain else ''
    if not domain:
        return []   # refuse to permute on a guessed domain

    patterns = []
    if owner_name:
        names = owner_name.lower().split()
        first = names[0] if names else ''
        last = names[-1] if len(names) > 1 else ''
        if first and last and first != last:
            patterns += [f'{first}.{last}@{domain}', f'{first}@{domain}',
                         f'{first}{last}@{domain}', f'{first[0]}{last}@{domain}']
        elif first:
            patterns += [f'{first}@{domain}']
    # Role addresses are only reasonable at the company's own domain
    patterns += [f'info@{domain}', f'contact@{domain}', f'hello@{domain}']

    out = []
    for email in patterns:
        local = email.split('@')[0]
        out.append({'email': email, 'verified': 'unverified_pattern',
                    'pattern': True, 'is_role': local in ROLE_LOCALS})
    return out

def enrich_lead(lead_id, business_name, city, phone, niche, providers=None, website=''):
    """Smart enrichment with provider selection.

    providers: list of strategies in order. Options:
      - 'serper' (default)
      - 'oxylabs'
      - 'serper+oxylabs' (Serper first, Oxylabs only if no email)
      - 'permutator' (free Hunter alternative — needs a real website domain)

    website: the lead's own scraped URL; the permutator only ever generates
    addresses at a domain the business actually controls.
    """
    if providers is None:
        strategy = CONFIG.get('enrichment_strategy', 'serper_then_oxylabs')
        providers = _STRATEGY_PROVIDERS.get(strategy, ['serper', 'oxylabs'])

    result = {'lead_id': lead_id, 'email': None, 'linkedin_url': None,
              'facebook_url': None, 'instagram_url': None,
              'owner_name': None, 'sources_tried': []}

    for prov in providers:
        if result['email'] and prov not in ('serper',):
            continue  # already found email, no need to fallback

        if prov == 'free_scrape':
            r = enrich_with_free_scrape(business_name, city)
            result['sources_tried'].append('free_scrape')
            for k, v in r.items():
                if v and not result.get(k): result[k] = v
        elif prov == 'serper':
            r = enrich_with_serper(business_name, city, niche)
            result['sources_tried'].append('serper')
            for k, v in r.items():
                if v and not result.get(k): result[k] = v
        elif prov == 'oxylabs':
            r = enrich_with_oxylabs(business_name, city)
            result['sources_tried'].append('oxylabs')
            if r.get('email') and not result['email']:
                result['email'] = r['email']
        elif prov == 'permutator':
            r = enrich_with_email_permutator(business_name, result.get('owner_name', ''), domain=website)
            result['sources_tried'].append('permutator')
            if r and not result['email']:
                result['email'] = r[0]['email']
                result['email_method'] = 'permutator_pattern'
    return result

def save_enrichment(result):
    conn = db_conn(); cur = conn.cursor()
    try:
        # Verify the email BEFORE storing it. Undeliverable addresses are
        # dropped entirely — a bounced cold email costs sender reputation.
        email_status, email_verified = 'unknown', False
        stored_email = result.get('email') or ''
        if stored_email:
            vr = verify_email(stored_email)
            email_status = vr['status']
            email_verified = (vr['status'] == 'deliverable')
            if vr['status'] == 'undeliverable':
                print(f'[enrich] dropping undeliverable email for {result.get("lead_id")}: '
                      f'{stored_email} — {vr["details"][:1]}')
                stored_email = ''

        confidence = 0
        if stored_email:
            confidence += 40
            if email_status == 'deliverable': confidence += 20   # SMTP-confirmed
            elif email_status == 'risky':      confidence += 5
        if result.get('linkedin_url'): confidence += 30
        if result.get('facebook_url'): confidence += 15
        if result.get('owner_name'):   confidence += 5
        confidence = min(confidence, 100)

        if stored_email or result.get('linkedin_url') or result.get('facebook_url'):
            cur.execute("""
                INSERT INTO contacts (lead_id, full_name, email, linkedin_url, source, confidence,
                                      email_status, email_checked_at, email_method, email_verified)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s)
            """, (result['lead_id'], result.get('owner_name', '') or '',
                  stored_email, result.get('linkedin_url', '') or '',
                  '+'.join(result.get('sources_tried', [])), confidence,
                  email_status if stored_email else None,
                  result.get('email_method', ''), email_verified))

        cur.execute("UPDATE leads SET status='enriched' WHERE id=%s", (result['lead_id'],))
        conn.commit()
    except Exception as e:
        print(f'Save error: {e}')
        conn.rollback()
    finally:
        cur.close(); conn.close()

def enrich_all_discovered(provider_strategy='serper_then_oxylabs'):
    """Enrich all discovered leads that don't have contact info yet."""
    conn = db_conn(); cur = conn.cursor()
    # Target: status=discovered, regardless of has_website, with no useful contact info yet
    cur.execute("""
        SELECT l.id, l.business_name, l.city, l.phone, l.niche, COALESCE(l.website,'') as website
        FROM leads l
        LEFT JOIN contacts c ON c.lead_id = l.id
        WHERE l.status = 'discovered' AND l.lead_type IS NULL
          AND (c.id IS NULL OR (COALESCE(c.email,'') = '' AND COALESCE(c.linkedin_url,'') = ''))
        ORDER BY l.created_at ASC
    """)
    leads = cur.fetchall()
    cur.close(); conn.close()

    if provider_strategy == 'serper_only':
        providers = ['serper']
    elif provider_strategy == 'oxylabs_only':
        providers = ['oxylabs']
    elif provider_strategy == 'serper_then_oxylabs':
        providers = ['serper', 'oxylabs']
    elif provider_strategy == 'free_only':
        providers = ['serper', 'permutator']
    else:
        providers = ['serper']

    results = []
    for ld in leads:
        lead_id, bname, city, phone, niche, website = ld
        try:
            r = enrich_lead(str(lead_id), bname, city, phone, niche, providers, website=website)
            save_enrichment(r)
            results.append({
                'business_name': bname, 'city': city,
                'email_found': bool(r.get('email')),
                'linkedin_found': bool(r.get('linkedin_url')),
                'email': r.get('email'),
                'sources': r.get('sources_tried', [])
            })
            time.sleep(0.3)
        except Exception as e:
            print(f'Enrich error {bname}: {e}')
    return results

def enrich_single_company(company_name, city='', niche='', website='', strategy='free_first'):
    """Enrich one company by name. Inserts a lead row if not already present, enriches it."""
    conn = db_conn(); cur = conn.cursor()
    try:
        # Check if already in DB
        cur.execute("SELECT id FROM leads WHERE lower(business_name)=lower(%s) AND lead_type IS NULL LIMIT 1",
                    (company_name,))
        row = cur.fetchone()
        if row:
            lead_id = str(row[0])
        else:
            place_id = 'manual_' + hashlib.md5(f'{company_name}{city}{time.time()}'.encode()).hexdigest()[:12]
            cur.execute("""
                INSERT INTO leads(place_id, business_name, niche, city, country, website, status, source, lead_type)
                VALUES(%s, %s, %s, %s, %s, %s, 'discovered', 'manual', NULL)
                RETURNING id
            """, (place_id, company_name, niche or '', city or '', '', website or ''))
            lead_id = str(cur.fetchone()[0])
            conn.commit()
    except Exception as e:
        conn.rollback()
        return {'error': str(e)}
    finally:
        cur.close(); conn.close()

    providers = _STRATEGY_PROVIDERS.get(strategy, _STRATEGY_PROVIDERS['free_first'])
    r = enrich_lead(lead_id, company_name, city, '', niche, providers, website=website or '')
    save_enrichment(r)
    return {
        'lead_id': lead_id,
        'company': company_name,
        'city': city,
        'email': r.get('email'),
        'linkedin_url': r.get('linkedin_url'),
        'facebook_url': r.get('facebook_url'),
        'instagram_url': r.get('instagram_url'),
        'owner_name': r.get('owner_name'),
        'sources_tried': r.get('sources_tried', []),
        'email_found': bool(r.get('email')),
        'contact_found': bool(r.get('email') or r.get('linkedin_url')),
    }


def run_csv_enrich_bg(job_id, rows, strategy):
    """Background worker for bulk CSV enrichment."""
    total = len(rows)
    JOBS[job_id]['log'].append(f'Starting enrichment of {total} companies…')
    results = []
    for i, row in enumerate(rows):
        company = (row.get('company_name') or row.get('company') or row.get('name') or row.get('business_name') or '').strip()
        if not company:
            continue
        city  = (row.get('city') or row.get('location') or '').strip()
        niche = (row.get('niche') or row.get('industry') or '').strip()
        website = (row.get('website') or row.get('url') or '').strip()
        try:
            r = enrich_single_company(company, city, niche, website, strategy)
            results.append(r)
            found = '✓' if r.get('contact_found') else '—'
            JOBS[job_id]['log'].append(f'{found} {company}: {r.get("email") or r.get("linkedin_url") or "no contact"}')
        except Exception as e:
            JOBS[job_id]['log'].append(f'Error {company}: {e}')
        JOBS[job_id]['progress'] = int((i + 1) / total * 100)
        time.sleep(0.2)

    found_count = sum(1 for r in results if r.get('contact_found'))
    JOBS[job_id]['status'] = 'completed'
    JOBS[job_id]['progress'] = 100
    JOBS[job_id]['results'] = {
        'total': total, 'contact_found': found_count, 'no_contact': total - found_count
    }
    JOBS[job_id]['csv_results'] = results
    JOBS[job_id]['log'].append(f'Done — {found_count}/{total} contacts found')


def reenrich_missing_emails(use_oxylabs=True):
    """Find emails for leads that have no email yet, using Oxylabs deep scrape."""
    conn = db_conn(); cur = conn.cursor()
    cur.execute("""
        SELECT l.id, l.business_name, l.city, l.phone, l.niche, COALESCE(l.website,'') as website
        FROM leads l
        LEFT JOIN contacts c ON c.lead_id = l.id
        WHERE l.status IN ('enriched', 'ready') AND l.lead_type IS NULL
          AND (c.email IS NULL OR c.email = '')
        ORDER BY l.created_at DESC LIMIT 50
    """)
    leads = cur.fetchall(); cur.close(); conn.close()
    results = []
    for ld in leads:
        lead_id, bname, city, phone, niche, website = ld
        try:
            if use_oxylabs and OXYLABS:
                r = enrich_with_oxylabs(bname, city)
                email = (r.get('email') or '').strip()
                if email:
                    # Verify before saving — same gate as the main pipeline.
                    vr = verify_email(email)
                    if vr['status'] == 'undeliverable':
                        results.append({'business_name': bname, 'email': email,
                                        'email_status': 'undeliverable',
                                        'note': 'dropped — failed verification'})
                        time.sleep(0.3)
                        continue
                    conn = db_conn(); cur = conn.cursor()
                    cur.execute("""UPDATE contacts SET email=%s, email_status=%s,
                                   email_checked_at=NOW(), email_method='oxylabs_reenrich'
                                   WHERE lead_id=%s AND (email IS NULL OR email='')""",
                               (email, vr['status'], lead_id))
                    if cur.rowcount == 0:
                        cur.execute("""INSERT INTO contacts(lead_id, email, source, confidence,
                                       email_status, email_checked_at, email_method)
                                       VALUES(%s, %s, 'oxylabs', 40, %s, NOW(), 'oxylabs_reenrich')""",
                                   (lead_id, email, vr['status']))
                    conn.commit(); cur.close(); conn.close()
                    results.append({'business_name': bname, 'email': email,
                                    'email_status': vr['status']})
            time.sleep(0.3)
        except Exception as e:
            print(f'Reenrich error {bname}: {e}')
    return results

# ──────────────────────────────────────────────────────────────
#  SEO KEYWORD RESEARCH
# ──────────────────────────────────────────────────────────────
def keyword_research(seed_keyword, location=''):
    """Get keyword suggestions, related searches, People Also Ask, autocomplete."""
    result = {
        'seed': seed_keyword,
        'location': location,
        'related_keywords': [],
        'people_also_ask': [],
        'autocomplete': [],
        'top_competitors': []
    }

    # 1. Serper search returns PAA + related
    data = serper_search(f'{seed_keyword} {location}'.strip(), 20)
    if data:
        # People Also Ask
        for paa in data.get('peopleAlsoAsk', []):
            result['people_also_ask'].append({
                'question': paa.get('question', ''),
                'answer': paa.get('snippet', '')[:200]
            })
        # Related searches
        for rel in data.get('relatedSearches', []):
            result['related_keywords'].append(rel.get('query', ''))
        # Top organic competitors
        for org in data.get('organic', [])[:10]:
            result['top_competitors'].append({
                'title': org.get('title', ''),
                'url': org.get('link', ''),
                'snippet': org.get('snippet', '')[:150]
            })

    # 2. Google autocomplete
    try:
        url = f'http://suggestqueries.google.com/complete/search?client=firefox&q={urllib.parse.quote(seed_keyword)}'
        resp = urllib.request.urlopen(url, timeout=10)
        suggestions = json.loads(resp.read().decode())
        if isinstance(suggestions, list) and len(suggestions) > 1:
            result['autocomplete'] = suggestions[1][:15]
    except Exception as e:
        print(f'Autocomplete error: {e}')

    # 3. Use Gemini to expand semantically
    if result['autocomplete'] or result['related_keywords']:
        prompt = f"""Based on these keywords, generate 15 more high-value SEO keyword variations:

Seed: {seed_keyword}
Autocomplete: {result['autocomplete'][:5]}
Related: {result['related_keywords'][:5]}

Return ONLY a JSON array of strings, like:
["keyword 1", "keyword 2", ...]"""
        ai_response = gemini_call(prompt, 400)
        if ai_response:
            m = re.search(r'\[[\s\S]*?\]', ai_response)
            if m:
                try:
                    expanded = json.loads(m.group())
                    result['ai_expanded'] = expanded
                except: pass

    return result

def serp_analysis(keyword, location=''):
    """Analyze SERP for a keyword - who ranks, what features show up."""
    data = serper_search(f'{keyword} {location}'.strip(), 20)
    if not data: return None

    return {
        'keyword': keyword,
        'location': location,
        'total_results': data.get('searchInformation', {}).get('totalResults', 'unknown'),
        'organic_results': [
            {
                'position': i + 1,
                'title': o.get('title', ''),
                'url': o.get('link', ''),
                'domain': o.get('link', '').split('/')[2] if '/' in o.get('link', '') else '',
                'snippet': o.get('snippet', '')[:200]
            }
            for i, o in enumerate(data.get('organic', [])[:10])
        ],
        'has_local_pack': bool(data.get('places')),
        'local_pack': data.get('places', [])[:5],
        'has_featured_snippet': bool(data.get('answerBox')),
        'featured_snippet': data.get('answerBox', {}),
        'has_knowledge_graph': bool(data.get('knowledgeGraph')),
        'people_also_ask_count': len(data.get('peopleAlsoAsk', [])),
        'related_searches_count': len(data.get('relatedSearches', []))
    }

# ──────────────────────────────────────────────────────────────
#  COMPETITOR INTELLIGENCE
# ──────────────────────────────────────────────────────────────
def competitor_intel(domain_or_company):
    """Quick competitor analysis."""
    result = {
        'target': domain_or_company,
        'ranking_keywords': [],
        'social_presence': {},
        'tech_clues': [],
        'recent_mentions': []
    }

    # 1. Find their ranking keywords (Serper search for site:)
    if '.' in domain_or_company:  # looks like a domain
        d = data = serper_search(f'site:{domain_or_company}', 20)
        if d:
            for o in d.get('organic', [])[:15]:
                result['ranking_keywords'].append({
                    'title': o.get('title', ''),
                    'url': o.get('link', ''),
                    'snippet': o.get('snippet', '')[:150]
                })

    # 2. Social media discovery
    for platform in ['linkedin.com', 'facebook.com', 'instagram.com', 'twitter.com']:
        d = serper_search(f'{domain_or_company} site:{platform}', 3)
        if d:
            org = d.get('organic', [])
            if org:
                result['social_presence'][platform.split('.')[0]] = org[0].get('link', '')

    # 3. Recent news/mentions
    d = serper_search(f'"{domain_or_company}" news', 5)
    if d:
        for o in d.get('organic', [])[:5]:
            result['recent_mentions'].append({
                'title': o.get('title', ''),
                'url': o.get('link', ''),
                'snippet': o.get('snippet', '')[:150]
            })

    return result

# ──────────────────────────────────────────────────────────────
#  E-COMMERCE RESEARCH  (Professional Intelligence Engine)
# ──────────────────────────────────────────────────────────────

# ── eBay official Browse API (free 5,000 calls/day) ──────────────────────
_EBAY_TOKEN = {'token': None, 'expires': 0}

def _ebay_oauth_token():
    """Client-credentials OAuth token for the eBay Browse API.
    Needs ebay_client_id + ebay_client_secret (developer.ebay.com, free)."""
    if not (EBAY_CLIENT_ID and EBAY_CLIENT_SECRET):
        return None
    if _EBAY_TOKEN['token'] and time.time() < _EBAY_TOKEN['expires'] - 60:
        return _EBAY_TOKEN['token']
    try:
        import base64
        cred = base64.b64encode(f'{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}'.encode()).decode()
        body = urllib.parse.urlencode({
            'grant_type': 'client_credentials',
            'scope': 'https://api.ebay.com/oauth/api_scope',
        }).encode()
        req = urllib.request.Request(
            'https://api.ebay.com/identity/v1/oauth2/token', data=body, method='POST',
            headers={'Authorization': 'Basic ' + cred,
                     'Content-Type': 'application/x-www-form-urlencoded'})
        data = json.loads(urllib.request.urlopen(req, timeout=15).read().decode())
        _EBAY_TOKEN['token'] = data.get('access_token')
        _EBAY_TOKEN['expires'] = time.time() + int(data.get('expires_in', 7200))
        return _EBAY_TOKEN['token']
    except Exception as e:
        print(f'eBay OAuth error: {e}')
        return None

def ebay_browse_search(query, country='us', limit=50):
    """Official eBay Browse API — exact active-listing total + real listings
    with prices, per marketplace. Returns {} when keys aren't configured."""
    token = _ebay_oauth_token()
    if not token:
        return {}
    cfg = MARKET_CONFIG.get(country, MARKET_CONFIG['us'])
    try:
        params = urllib.parse.urlencode({'q': query, 'limit': max(1, min(limit, 200))})
        req = urllib.request.Request(
            'https://api.ebay.com/buy/browse/v1/item_summary/search?' + params,
            headers={'Authorization': 'Bearer ' + token,
                     'X-EBAY-C-MARKETPLACE-ID': cfg.get('ebay_marketplace', 'EBAY_US')})
        data = json.loads(urllib.request.urlopen(req, timeout=15).read().decode())
        items = []
        for it in data.get('itemSummaries') or []:
            price = it.get('price') or {}
            try: pv = float(price.get('value') or 0)
            except Exception: pv = 0.0
            items.append({
                'title':           it.get('title', ''),
                'link':            it.get('itemWebUrl', ''),
                'price_value':     pv,
                'price_str':       ('%s %s' % (cfg['symbol'], price.get('value', ''))).strip() if price.get('value') else '',
                'condition':       it.get('condition', ''),
                'image_url':       (it.get('image') or {}).get('imageUrl', ''),
                'seller_feedback': (it.get('seller') or {}).get('feedbackScore', 0),
                'buying_options':  it.get('buyingOptions', []),
                'platform':        'ebay',
            })
        return {'total': int(data.get('total') or 0), 'items': items}
    except Exception as e:
        print(f'eBay Browse API error: {e}')
        return {}

def serper_shopping_search(query, country='us', num=20):
    """Google Shopping via Serper — structured product data with prices + ratings."""
    cfg = MARKET_CONFIG.get(country, MARKET_CONFIG['us'])
    body = json.dumps({'q': query, 'gl': cfg['gl'], 'hl': cfg['hl'], 'num': num}).encode()
    return _serper_request('https://google.serper.dev/shopping', body, 15, 'Serper shopping')

def _parse_price(price_str):
    """Extract float from price string like '$12.99', '£45', 'A$30.00', '€25,99'."""
    if not price_str: return 0.0
    cleaned = re.sub(r'[^\d.,]', '', price_str.replace(',', '.'))
    # Handle cases like "12.99.00" — keep only first valid float
    m = re.search(r'(\d+\.?\d{0,2})', cleaned)
    try: return float(m.group(1)) if m else 0.0
    except: return 0.0

def _price_stats(prices):
    """Comprehensive price statistics with outlier trimming."""
    if not prices: return {}
    prices = sorted(p for p in prices if p > 0.5)
    if not prices: return {}
    n = len(prices)
    # Trim top/bottom 5% on large samples
    if n >= 20:
        cut = max(1, int(n * 0.05))
        core = prices[cut:-cut]
    else:
        core = prices
    if not core: core = prices
    avg = sum(core) / len(core)
    median = core[len(core) // 2]
    # Most common price bucket (5 equal-width buckets)
    lo, hi = core[0], core[-1]
    if hi > lo:
        bw = (hi - lo) / 5
        buckets = {}
        for p in core:
            idx = min(4, int((p - lo) / bw))
            key = '%s-%s' % (round(lo + idx * bw), round(lo + (idx + 1) * bw))
            buckets[key] = buckets.get(key, 0) + 1
        top_bucket = max(buckets, key=buckets.get)
    else:
        top_bucket = '~%s' % round(avg)
    return {
        'min': round(prices[0], 2),
        'max': round(prices[-1], 2),
        'avg': round(avg, 2),
        'median': round(median, 2),
        'sample_size': n,
        'sweet_spot': top_bucket,
    }

def _competition_label(count):
    if count < 200: return 'Low'
    if count < 2000: return 'Medium'
    if count < 20000: return 'High'
    return 'Very High'

def _parse_ebay_sold_page(text):
    """
    Extract prices and sold-count badges from Jina/Crawl4AI markdown of eBay sold page.
    eBay sold search markdown typically contains:
      - Prices like "$12.99", "£15.00", "€20,99", "A$30"
      - "42 sold", "100+ sold" badges on popular items
      - Item count in header like "2,345 results"
    Sets 'available': False when the page yielded no usable sales signals
    (blocked page or empty result) so callers can report honestly instead
    of showing zeros as if they were real data.
    """
    if not text:
        return {'prices': [], 'sold_mentions': [], 'total_sold': 0,
                'items_visible': 0, 'results_total': 0, 'available': False}

    # Multi-currency price extraction
    price_patterns = [
        r'\$(\d[\d,]*\.?\d{0,2})',
        r'£(\d[\d,]*\.?\d{0,2})',
        r'€(\d[\d,]*[,.]?\d{0,2})',
        r'A\$(\d[\d,]*\.?\d{0,2})',
        r'C\$(\d[\d,]*\.?\d{0,2})',
    ]
    prices = []
    for pat in price_patterns:
        for m in re.findall(pat, text):
            try:
                v = float(m.replace(',', '').replace(' ', ''))
                if 0.5 < v < 50000:
                    prices.append(v)
            except: pass

    # Sold count badges: "42 sold", "1,234 sold", "100+ sold"
    sold_raw = re.findall(r'(\d[\d,]*)\+?\s+sold', text, re.IGNORECASE)
    sold_ints = []
    for s in sold_raw:
        try:
            v = int(s.replace(',', ''))
            if v < 1000000: sold_ints.append(v)
        except: pass
    total_sold = sum(sold_ints)

    # Count sold-date markers = distinct sold items. eBay renders these with
    # NO space ("SoldJul 3, 2026") on some layouts and a space on others, so
    # the separator must be optional, not required.
    item_blocks = len(re.findall(r'Sold\s?[A-Z][a-z]{2}\s+\d', text))
    if not item_blocks:
        item_blocks = len(re.findall(r'\bSold\b', text, re.IGNORECASE))

    # Header result count: "2,345 results" / "2.345 Ergebnisse"
    results_total = 0
    m = re.search(r'([\d][\d,.]*)\+?\s+(?:results?|ergebnisse|résultats|risultati|resultados)', text, re.IGNORECASE)
    if m:
        try: results_total = int(re.sub(r'[,.]', '', m.group(1)))
        except Exception: pass

    return {
        'prices': prices[:200],
        'sold_mentions': sold_ints,
        'total_sold': total_sold,
        'items_visible': min(item_blocks, 240),
        'results_total': results_total,
        'available': bool(prices or sold_ints),
    }

def _get_ebay_sold(query, country):
    """Fetch eBay sold items page and parse it. _ipg=240 = max items per page."""
    cfg = MARKET_CONFIG.get(country, MARKET_CONFIG['us'])
    encoded = urllib.parse.quote_plus(query)
    url = 'https://%s/sch/i.html?_nkw=%s&LH_Sold=1&LH_Complete=1&_sop=13&_ipg=240' % (cfg['ebay'], encoded)
    text = smart_scrape(url, timeout=25, prefer_direct=True)
    return _parse_ebay_sold_page(text)

def _get_ebay_active_fallback(query, country):
    """Active listing count without the Browse API: read the count printed
    on the eBay search page itself (free — no Serper credits).
    The old Serper site-search approach always returned 0 because Serper
    doesn't include searchInformation.totalResults in its responses."""
    cfg = MARKET_CONFIG.get(country, MARKET_CONFIG['us'])
    url = 'https://%s/sch/i.html?_nkw=%s' % (cfg['ebay'], urllib.parse.quote_plus(query))
    text = smart_scrape(url, timeout=20, prefer_direct=True)
    if text:
        m = re.search(r'([\d][\d,.]*)\+?\s+(?:results?|ergebnisse|résultats|risultati|resultados)', text, re.IGNORECASE)
        if m:
            try: return int(re.sub(r'[,.]', '', m.group(1))), 'ebay_page'
            except Exception: pass
    return 0, 'unavailable'

def ecommerce_research(query, country='us'):
    """
    Professional e-commerce product intelligence.
    Aggregates: Google Shopping, eBay Browse API (official active listings),
    eBay Sold Items (real historical sales), Google Trends, keyword research,
    AI verdict. Tracks which data sources actually delivered so the UI can
    show provenance instead of silent zeros.
    """
    cfg = MARKET_CONFIG.get(country, MARKET_CONFIG['us'])
    result = {
        'query': query,
        'country': country,
        'country_name': cfg['name'],
        'currency': cfg['currency'],
        'symbol': cfg['symbol'],
        'price_analysis': {},
        'market_overview': {},
        'sales_data': {},
        'top_products': [],
        'amazon_listings': [],
        'ebay_listings': [],
        'trends': {},
        'keywords': {},
        'ai_verdict': '',
        'data_sources': [],
        'credits_used': 0,
    }

    all_prices = []

    # ── 1. Google Shopping ────────────────────────────────────────────────
    shop_data = serper_shopping_search(query, country, 20)
    products = []
    for item in shop_data.get('shopping', []):
        pv = _parse_price(item.get('price', ''))
        products.append({
            'title':        item.get('title', ''),
            'source':       item.get('source', ''),
            'link':         item.get('link', ''),
            'price_str':    item.get('price', ''),
            'price_value':  pv,
            'rating':       item.get('rating') or 0,
            'rating_count': item.get('ratingCount') or 0,
            'delivery':     item.get('delivery', ''),
            'image_url':    item.get('imageUrl', ''),
            'platform':     'google_shopping',
        })
        if pv > 0: all_prices.append(pv)
    result['top_products'] = products[:20]
    result['credits_used'] += 1
    if products: result['data_sources'].append('google_shopping')

    # ── 2. Amazon via Serper organic ─────────────────────────────────────
    amazon_domain = cfg['amazon']
    amz_data = serper_search('site:%s %s' % (amazon_domain, query), 10)
    result['credits_used'] += 1
    amz_listings = []
    for item in amz_data.get('organic', [])[:10]:
        snippet = item.get('snippet', '')
        pm = re.search(r'[\$£€A-Z]*\s*(\d[\d,]*\.?\d{0,2})', snippet)
        pv = float(pm.group(1).replace(',', '')) if pm else 0
        rm = re.search(r'(\d+\.?\d)\s*out of\s*5', snippet)
        rv = float(rm.group(1)) if rm else 0
        amz_listings.append({
            'title':   item.get('title', ''),
            'link':    item.get('link', ''),
            'snippet': snippet[:250],
            'price_value': pv,
            'rating':      rv,
            'platform': 'amazon',
        })
        if pv > 0: all_prices.append(pv)
    result['amazon_listings'] = amz_listings
    if amz_listings: result['data_sources'].append('amazon_serper')

    # ── 3. eBay Active Listings via official Browse API (free, exact) ─────
    browse = ebay_browse_search(query, country, limit=50)
    if browse:
        result['ebay_listings'] = browse.get('items', [])[:12]
        for it in browse.get('items', []):
            if it.get('price_value', 0) > 0:
                all_prices.append(it['price_value'])
        if browse.get('items'): result['data_sources'].append('ebay_browse_api')

    # ── 4. eBay Sold Items (real historical sales data) ───────────────────
    ebay_sold = _get_ebay_sold(query, country)
    sold_available = ebay_sold.get('available', False)
    ebay_sold_prices = ebay_sold.get('prices', [])
    all_prices.extend(ebay_sold_prices)

    if sold_available:
        total_sold_badges = ebay_sold.get('total_sold', 0)
        visible_items = ebay_sold.get('items_visible', 0)
        # Estimate monthly from visible sold count (eBay shows ~last 90 days of sold)
        monthly_estimate = max(
            total_sold_badges // 3 if total_sold_badges else 0,
            visible_items * 2
        )
        ebay_sold_avg = round(sum(ebay_sold_prices) / len(ebay_sold_prices), 2) if ebay_sold_prices else 0
        result['sales_data'] = {
            'monthly_sold_estimate': monthly_estimate,
            'sold_items_visible': visible_items,
            'total_sold_badges': total_sold_badges,
            'ebay_sold_avg_price': ebay_sold_avg,
            'data_source': 'ebay_sold_filter',
            'note': 'Based on eBay Sold Items filter — real completed transactions',
        }
        result['data_sources'].append('ebay_sold_page')
    else:
        result['sales_data'] = {
            'monthly_sold_estimate': None,
            'sold_items_visible': 0,
            'total_sold_badges': 0,
            'ebay_sold_avg_price': 0,
            'data_source': 'unavailable',
            'note': 'eBay blocked the sold-items page from this server. Add a free scraper key (ScrapingBee/ZenRows, 1,000 req/mo free) in Settings to unlock real sold data.',
        }

    # ── 5. Competition (Browse API total > page count > unknown) ─────────
    if browse and browse.get('total'):
        ebay_active, active_source = browse['total'], 'ebay_browse_api'
    elif ebay_sold.get('results_total'):
        # sold-results count is a decent lower-bound proxy when browse is off
        ebay_active, active_source = ebay_sold['results_total'], 'ebay_sold_page'
    else:
        ebay_active, active_source = _get_ebay_active_fallback(query, country)
    competition = _competition_label(ebay_active) if ebay_active else 'Unknown'
    result['market_overview'] = {
        'ebay_active_listings': ebay_active,
        'active_listings_source': active_source,
        'competition_level': competition,
        'total_shopping_products': len(products),
        'amazon_results_found': len(amz_listings),
        'ebay_results_found': len(result['ebay_listings']),
        'ebay_domain': cfg['ebay'],
        'amazon_domain': amazon_domain,
    }

    # ── 6. Price Analysis ─────────────────────────────────────────────────
    result['price_analysis'] = _price_stats(all_prices)

    # ── 7. Google Trends ──────────────────────────────────────────────────
    result['trends'] = google_trends(query, cfg['gl'].upper())
    result['credits_used'] += 1

    # ── 8. Keyword Research ───────────────────────────────────────────────
    kw = keyword_research(query, cfg['hl'])
    result['credits_used'] += 1
    result['keywords'] = {
        'related':         kw.get('related_keywords', [])[:12],
        'people_also_ask': kw.get('people_also_ask', [])[:6],
        'autocomplete':    kw.get('autocomplete', [])[:12],
        'ai_expanded':     kw.get('ai_expanded', [])[:10],
    }

    # ── 9. AI Verdict (Gemini) ────────────────────────────────────────────
    pa = result['price_analysis']
    mo = result['market_overview']
    sd = result['sales_data']
    trending = result['trends'].get('trending_topics', [])[:5]
    monthly_txt = sd.get('monthly_sold_estimate')
    if monthly_txt is None: monthly_txt = 'unknown (sold data unavailable)'
    prompt = (
        'You are a professional e-commerce product researcher with 10+ years of experience.\n'
        'Analyze this data and give a sharp, actionable 4-sentence verdict.\n\n'
        'Product: %s\nMarket: %s (%s)\n\n'
        'PRICE DATA:\n  Min: %s | Max: %s | Avg: %s | Median: %s\n  Sweet spot: %s | Sample: %s products\n\n'
        'MARKET DATA:\n  Competition: %s | Active eBay listings: %s\n  Monthly sales estimate: %s units\n  eBay sold avg price: %s\n\n'
        'TRENDING NOW: %s\n\n'
        'Verdict must cover:\n'
        '1. Is this a good product opportunity right now? (yes/no + why)\n'
        '2. Best entry price point to be competitive\n'
        '3. Competition difficulty and how to differentiate\n'
        '4. Trend direction (growing/stable/declining) and best timing to enter'
        % (
            query, cfg['name'], cfg['currency'],
            pa.get('min', 'N/A'), pa.get('max', 'N/A'), pa.get('avg', 'N/A'), pa.get('median', 'N/A'),
            pa.get('sweet_spot', 'N/A'), pa.get('sample_size', 0),
            mo.get('competition_level', 'N/A'), mo.get('ebay_active_listings', 'N/A'),
            monthly_txt, sd.get('ebay_sold_avg_price', 'N/A'),
            ', '.join(trending) or 'N/A',
        )
    )
    verdict = gemini_call(prompt, 600)
    result['ai_verdict'] = verdict or 'Research complete. Review the data above for insights.'

    return result

# ──────────────────────────────────────────────────────────────
#  PRODUCT HUNTER — discovery mode
#  ecommerce_research() analyses ONE product you already have in mind.
#  product_hunt() does the opposite: give it a niche and it finds and
#  ranks the best specific products to sell right now on eBay/Amazon.
#  Credit budget: 3 Serper credits + free Gemini + free eBay Browse API
#  (up to 4 extra Serper credits only if the Browse API isn't configured).
# ──────────────────────────────────────────────────────────────

def _hunt_heuristic_scores(cand):
    """Fallback subscores when Gemini is unavailable."""
    comp_map = {'Low': 22, 'Medium': 16, 'High': 8, 'Very High': 3}
    competition = comp_map.get(cand.get('competition_level'), 12)
    median = (cand.get('price_stats') or {}).get('median') or 0
    margin = 20 if 15 <= median <= 80 else 12 if median else 6
    return {'demand': 15, 'competition': competition, 'margin': margin, 'trend': 10}

def _fuzzy_match(name, items):
    """Find the best-matching live listing for a candidate product name.
    Requires at least half the significant words in the name to appear in
    the listing title, so a name like 'Resistance Bands Set (with door
    anchor)' won't false-match an unrelated 'Door Anchor Hook' listing."""
    words = [w for w in re.findall(r'[a-z0-9]+', name.lower()) if len(w) > 2]
    if not words: return None
    best, best_hits = None, 0
    for it in items or []:
        t = (it.get('title') or '').lower()
        hits = sum(1 for w in words if w in t)
        if hits > best_hits:
            best, best_hits = it, hits
    return best if best_hits >= max(1, len(words) // 2) else None

def _verify_candidate(name, country, cfg, free_pools):
    """
    Cross-validate one candidate product against real, live sources before
    it's allowed into the results. Tries free/already-fetched data first,
    only spends Serper credits as a last resort (Serper/Oxylabs are
    fallbacks, never the primary source of truth).

    Returns (verified: bool, sources_checked: list[str], prices: list[float],
             active_listings: int, credits_spent: int, browse_items: list).
    Tier order:
      0. Reuse already-fetched broad niche pools (free, no extra API calls)
      1. eBay Browse API for this exact product name (free, official)
      2. Serper Google Shopping for this exact product name (paid fallback)
      3. Serper Amazon site-search for this exact product name (paid fallback)
    """
    sources, prices, active_listings, credits_spent = [], [], 0, 0
    browse_items = []

    # Tier 0: free reuse of broad pools already fetched for the whole niche
    for pool_name, pool in free_pools:
        m = _fuzzy_match(name, pool)
        if m and m.get('price_value', 0) > 0:
            prices.append(m['price_value'])
            sources.append(f'{pool_name}: matched listing at {m.get("price_str") or m["price_value"]}')

    # Tier 1: eBay Browse API — free, official, exact active-listing count
    browse = ebay_browse_search(name, country, limit=30)
    if browse:
        browse_items = browse.get('items', [])
        active_listings = browse.get('total', 0)
        ebay_prices = [i['price_value'] for i in browse_items if i.get('price_value', 0) > 0]
        prices.extend(ebay_prices)
        if browse_items:
            sources.append(f'eBay Browse API: {active_listings:,} active listings, '
                           f'price range {cfg["symbol"]}{min(ebay_prices):.2f}-{cfg["symbol"]}{max(ebay_prices):.2f}'
                           if ebay_prices else f'eBay Browse API: {active_listings:,} active listings')

    verified_so_far = bool(prices)

    # Tier 2: Serper Google Shopping — paid fallback, only if still unverified
    if not verified_so_far:
        shop = serper_shopping_search(name, country, 10)
        credits_spent += 1
        shop_prices = [p for p in (_parse_price(i.get('price', '')) for i in shop.get('shopping', [])) if p > 0]
        if shop_prices:
            prices.extend(shop_prices)
            sources.append(f'Google Shopping: {len(shop_prices)} listing(s) found, avg {cfg["symbol"]}{sum(shop_prices)/len(shop_prices):.2f}')
            verified_so_far = True

    # Tier 3: Serper Amazon site-search — paid fallback, last resort
    if not verified_so_far:
        amz = serper_search('site:%s %s' % (cfg['amazon'], name), 5)
        credits_spent += 1
        amz_hits = amz.get('organic', [])[:5]
        amz_prices = []
        for it in amz_hits:
            pm = re.search(r'[\$£€]\s*(\d[\d,]*\.?\d{0,2})', it.get('snippet', ''))
            if pm:
                try: amz_prices.append(float(pm.group(1).replace(',', '')))
                except Exception: pass
        if amz_hits:
            prices.extend(amz_prices)
            sources.append(f'Amazon: {len(amz_hits)} listing(s) found' +
                           (f', avg {cfg["symbol"]}{sum(amz_prices)/len(amz_prices):.2f}' if amz_prices else ''))
            verified_so_far = True

    if not sources:
        sources.append('Not found on eBay, Amazon, or Google Shopping — could not verify this product exists')

    return verified_so_far, sources, prices, active_listings, credits_spent, browse_items

def product_hunt(category, country='us', count=8):
    """
    Professional product discovery. Hunts a niche across Google Shopping,
    Amazon, best-seller articles, Google Trends and live eBay listings, then
    has Gemini act as a veteran product hunter: pick candidate products,
    cross-validate every single one against real live listings on at least
    one independent source (dropping any that can't be verified), and score
    each verified product 0-100 with live market metrics.
    """
    count = max(3, min(int(count or 8), 10))
    cfg = MARKET_CONFIG.get(country, MARKET_CONFIG['us'])
    year = time.strftime('%Y')
    result = {
        'category': category, 'country': country,
        'country_name': cfg['name'], 'currency': cfg['currency'], 'symbol': cfg['symbol'],
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'products': [], 'data_sources': [], 'credits_used': 0, 'dropped_unverified': 0,
    }

    # ── Stage 1: gather broad market signals, reused for free verification ─
    shopping = serper_shopping_search(f'best {category}', country, 20)
    result['credits_used'] += 1
    shop_items = []
    for it in shopping.get('shopping', []):
        shop_items.append({
            'title': it.get('title', ''), 'source': it.get('source', ''),
            'link': it.get('link', ''), 'price_str': it.get('price', ''),
            'price_value': _parse_price(it.get('price', '')),
            'rating': it.get('rating') or 0, 'rating_count': it.get('ratingCount') or 0,
            'image_url': it.get('imageUrl', ''),
        })
    if shop_items: result['data_sources'].append('google_shopping')

    amz_data = serper_search('site:%s best %s' % (cfg['amazon'], category), 15)
    result['credits_used'] += 1
    amazon_items = []
    for it in amz_data.get('organic', [])[:15]:
        pm = re.search(r'[\$£€]\s*(\d[\d,]*\.?\d{0,2})', it.get('snippet', ''))
        amazon_items.append({
            'title': it.get('title', ''), 'link': it.get('link', ''),
            'price_value': float(pm.group(1).replace(',', '')) if pm else 0,
            'price_str': pm.group(0) if pm else '',
        })
    if amazon_items: result['data_sources'].append('amazon_serper')

    organic = serper_search(f'best selling {category} products {year}', 10)
    result['credits_used'] += 1
    articles = [{'title': o.get('title', ''), 'snippet': o.get('snippet', '')}
                for o in organic.get('organic', [])[:10]]
    if articles: result['data_sources'].append('bestseller_articles')

    trends = google_trends(category, cfg['gl'].upper())
    result['credits_used'] += 1
    trend_terms = (trends.get('trending_topics', []) + trends.get('related_queries', []))[:12]
    if trend_terms: result['data_sources'].append('google_trends')

    browse_niche = ebay_browse_search(category, country, limit=40)
    niche_items = browse_niche.get('items', []) if browse_niche else []
    if niche_items: result['data_sources'].append('ebay_browse_api')

    # ── Stage 2: Gemini extracts candidate products (buffer = count+4, since
    # some will be dropped in Stage 3 if they can't be verified as real) ──
    buffer_count = min(count + 4, 14)
    sig = []
    if shop_items:
        sig.append('GOOGLE SHOPPING (best %s):\n%s' % (category, '\n'.join(
            '- %s | %s | rating %s (%s reviews)' % (i['title'][:90], i['price_str'], i['rating'], i['rating_count'])
            for i in shop_items[:15])))
    if amazon_items:
        sig.append('AMAZON (best %s):\n%s' % (category, '\n'.join(
            '- %s | %s' % (i['title'][:90], i['price_str'] or '?') for i in amazon_items[:15])))
    if articles:
        sig.append('BEST-SELLER ARTICLES:\n%s' % '\n'.join(
            '- %s — %s' % (a['title'][:90], a['snippet'][:120]) for a in articles[:8]))
    if trend_terms:
        sig.append('TRENDING/RELATED SEARCHES: %s' % ', '.join(trend_terms))
    if niche_items:
        sig.append('LIVE EBAY LISTINGS (%s):\n%s' % (category, '\n'.join(
            '- %s | %s' % (i['title'][:90], i['price_str']) for i in niche_items[:15])))

    prompt = (
        'You are a professional e-commerce product hunter with 10+ years of experience '
        'sourcing products for eBay and Amazon resellers.\n\n'
        'MARKET SIGNALS for the niche "%s" (%s market):\n\n%s\n\n'
        'From these signals, identify %d specific product opportunities to resell right now, '
        'ranked best-first (some will be dropped later if they can\'t be verified as real, so give '
        'more than the minimum needed).\n'
        'Rules:\n'
        '- Specific product types or models, not vague categories ("resistance band set with door anchor", not "fitness gear").\n'
        '- Practical for an individual reseller: shippable, sane sourcing, resale price roughly %s10-%s300.\n'
        '- Skip counterfeit-risk brands (Apple, Nike, LEGO...) unless clearly legitimate to resell.\n'
        '- Prefer products with visible demand evidence in the signals.\n\n'
        'Return ONLY a JSON array, no markdown:\n'
        '[{"name":"<specific product>","why":"<one-line demand evidence from the signals>","angle":"<differentiation angle for a new seller>"}]'
        % (category, cfg['name'], '\n\n'.join(sig), buffer_count, cfg['symbol'], cfg['symbol'])
    )
    candidates = []
    resp = gemini_call(prompt, 3500)
    if resp:
        try:
            m = re.search(r'\[[\s\S]*\]', resp)
            if not m:
                raise ValueError(f'no JSON array in response (len={len(resp)}): {resp[:200]!r}')
            for c in json.loads(m.group())[:buffer_count]:
                if c.get('name'):
                    candidates.append({'name': str(c['name'])[:120],
                                       'why': str(c.get('why', ''))[:300],
                                       'angle': str(c.get('angle', ''))[:300]})
        except Exception as e:
            print(f'product_hunt candidate parse error: {e}')
    if not candidates:
        # Fallback: highest-review products straight from Google Shopping
        seen = set()
        for i in sorted(shop_items, key=lambda x: -(x['rating_count'] or 0)):
            key = i['title'][:40].lower()
            if not key or key in seen: continue
            seen.add(key)
            candidates.append({'name': i['title'][:120],
                               'why': 'High review count on Google Shopping', 'angle': ''})
            if len(candidates) >= buffer_count: break
    if not candidates:
        result['error'] = 'No candidates found — try a broader niche.'
        return result

    # ── Stage 3: cross-validate every candidate against real live sources.
    # Any candidate that can't be confirmed on eBay, Amazon, or Google
    # Shopping is DROPPED — we never show a possibly-hallucinated product
    # as if it were a verified opportunity. Stop once `count` verified
    # products are found, so credits aren't wasted checking a full buffer
    # when the first few candidates already verify cleanly.
    free_pools = [('Google Shopping (niche scan)', shop_items),
                  ('Amazon (niche scan)', amazon_items),
                  ('eBay Browse API (niche scan)', niche_items)]
    verified_candidates = []
    for cand in candidates:
        if len(verified_candidates) >= count:
            break
        ok, sources_checked, prices, active_total, credits_spent, browse_items = _verify_candidate(
            cand['name'], country, cfg, free_pools)
        result['credits_used'] += credits_spent
        if not ok:
            result['dropped_unverified'] += 1
            print(f'product_hunt: dropped unverifiable candidate "{cand["name"]}"')
            continue
        cand['sources_checked'] = sources_checked
        cand['price_stats'] = _price_stats(prices)
        cand['active_listings'] = active_total
        cand['competition_level'] = _competition_label(active_total) if active_total else 'Unknown'
        cand['_browse_items'] = browse_items
        verified_candidates.append(cand)
    candidates = verified_candidates
    if not candidates:
        result['error'] = ('None of the suggested products could be verified against live eBay, '
                           'Amazon, or Google Shopping data. Try a broader or more common niche.')
        return result

    # ── Stage 4: one Gemini batch call scores everything ─────────────────
    metrics_text = '\n'.join(
        '%d. %s\n   verified via: %s\n   active eBay listings: %s | competition: %s | price min/median/max: %s/%s/%s (n=%s)\n   why: %s' % (
            i + 1, c['name'], '; '.join(c['sources_checked']),
            c['active_listings'] or 'unknown', c['competition_level'],
            c['price_stats'].get('min', '?'), c['price_stats'].get('median', '?'),
            c['price_stats'].get('max', '?'), c['price_stats'].get('sample_size', 0), c['why'])
        for i, c in enumerate(candidates))
    score_prompt = (
        'You are scoring product opportunities for a reseller entering the %s market on eBay/Amazon.\n'
        'Niche: %s. Trending searches: %s\n\n'
        'CANDIDATES WITH LIVE METRICS:\n%s\n\n'
        'Score each candidate. Subscores: demand 0-30, competition 0-25 (higher = easier to compete), '
        'margin 0-25, trend 0-20. Also give a realistic entry price (number, %s), an estimated monthly '
        'sales range for a new seller, a one-line entry strategy, and a verdict: BUY (strong opportunity), '
        'TEST (try a small batch) or AVOID.\n\n'
        'Return ONLY a JSON array in the same order, no markdown:\n'
        '[{"i":1,"demand":25,"competition":18,"margin":20,"trend":15,"entry_price":24.99,'
        '"est_monthly_sales":"30-60 units","strategy":"<one line>","verdict":"TEST"}]'
        % (cfg['name'], category, ', '.join(trend_terms[:8]) or 'n/a', metrics_text, cfg['currency'])
    )
    scores = []
    resp = gemini_call(score_prompt, 3000)
    if resp:
        try:
            m = re.search(r'\[[\s\S]*\]', resp)
            if not m:
                raise ValueError(f'no JSON array in response (len={len(resp)}): {resp[:200]!r}')
            scores = json.loads(m.group())
        except Exception as e:
            print(f'product_hunt score parse error: {e}')

    products = []
    for i, cand in enumerate(candidates):
        sc = next((s for s in scores if int(s.get('i', -1)) == i + 1), None)
        scoring_method = 'gemini'
        if sc:
            subs = {k: max(0, min(int(sc.get(k) or 0), cap)) for k, cap in
                    (('demand', 30), ('competition', 25), ('margin', 25), ('trend', 20))}
            entry_price = sc.get('entry_price') or cand['price_stats'].get('median') or 0
            est_sales = str(sc.get('est_monthly_sales', ''))[:60]
            strategy = str(sc.get('strategy', ''))[:300]
            verdict = str(sc.get('verdict', 'TEST')).upper()
            if verdict not in ('BUY', 'TEST', 'AVOID'): verdict = 'TEST'
        else:
            subs = _hunt_heuristic_scores(cand)
            entry_price = cand['price_stats'].get('median') or 0
            est_sales, strategy, verdict = '', '', 'TEST'
            scoring_method = 'heuristic_fallback'
        example = _fuzzy_match(cand['name'], cand.get('_browse_items')) or _fuzzy_match(cand['name'], shop_items)
        products.append({
            'name': cand['name'], 'why': cand['why'], 'angle': cand['angle'],
            'hunter_score': sum(subs.values()), 'scores': subs, 'verdict': verdict,
            'verified': True, 'sources_checked': cand['sources_checked'], 'scoring_method': scoring_method,
            'entry_price': entry_price, 'est_monthly_sales': est_sales, 'strategy': strategy,
            'active_listings': cand['active_listings'], 'competition_level': cand['competition_level'],
            'price_stats': cand['price_stats'],
            'example': {'title': example.get('title', ''), 'link': example.get('link', ''),
                        'image_url': example.get('image_url', ''),
                        'price_str': example.get('price_str', '')} if example else None,
        })
    products.sort(key=lambda p: -p['hunter_score'])
    for rank, p in enumerate(products, 1):
        p['rank'] = rank
    result['products'] = products
    return result

# ──────────────────────────────────────────────────────────────
#  IMAGE GENERATION (Optional + Toggleable)
# ──────────────────────────────────────────────────────────────
def generate_mockup_replicate(business_name, niche, city, custom_prompt=None):
    log_api_usage('replicate', 'mockup')
    """Use Replicate FLUX (existing)."""
    prompt = custom_prompt or f"Professional modern website homepage screenshot mockup for '{business_name}', a {niche} business in {city}. Clean hero section, white navigation bar, green CTA button, photorealistic UI mockup, desktop browser viewport"
    try:
        body = json.dumps({
            'input': {'prompt': prompt, 'num_outputs': 1, 'aspect_ratio': '16:9',
                     'output_format': 'webp', 'output_quality': 85, 'num_inference_steps': 4}
        }).encode()
        req = urllib.request.Request(
            'https://api.replicate.com/v1/models/black-forest-labs/flux-schnell/predictions',
            data=body, method='POST',
            headers={'Authorization': f'Bearer {REPLICATE_TOKEN}',
                    'Content-Type': 'application/json', 'Prefer': 'wait'}
        )
        resp = urllib.request.urlopen(req, timeout=90)
        data = json.loads(resp.read().decode())
        output = data.get('output', [])
        return output[0] if isinstance(output, list) and output else output
    except Exception as e:
        print(f'Replicate error: {e}')
    return None

def generate_mockup_imagine_art(business_name, niche, city, custom_prompt=None):
    log_api_usage('imagine_art', 'mockup')
    """Use imagine.art API. Returns URL of generated image."""
    if not IMAGINE_ART_KEY:
        return None
    prompt = custom_prompt or f"Professional modern website homepage mockup for {business_name}, a {niche} business in {city}. Clean hero section, elegant typography, modern UI design, photorealistic browser screenshot, premium feel"
    try:
        # imagine.art API uses multipart/form-data
        boundary = '----LeadGenBoundary' + hashlib.md5(str(time.time()).encode()).hexdigest()[:16]
        parts = []
        for field_name, field_val in [('prompt', prompt), ('style', 'realistic'), ('aspect_ratio', '16:9')]:
            parts.append('--' + boundary)
            parts.append(f'Content-Disposition: form-data; name="{field_name}"')
            parts.append('')
            parts.append(field_val)
        parts.append('--' + boundary + '--')
        body = '\r\n'.join(parts).encode('utf-8')

        req = urllib.request.Request(
            'https://api.vyro.ai/v2/image/generations',
            data=body, method='POST',
            headers={
                'Authorization': f'Bearer {IMAGINE_ART_KEY}',
                'Content-Type': f'multipart/form-data; boundary={boundary}',
            }
        )
        resp = urllib.request.urlopen(req, timeout=90)
        content_type = resp.headers.get('Content-Type', '')

        if 'image/' in content_type:
            # Save image to disk and return URL
            image_bytes = resp.read()
            timestamp = int(time.time())
            random_id = hashlib.md5(str(timestamp).encode() + business_name.encode()).hexdigest()[:12]
            ext = 'jpg' if 'jpeg' in content_type or 'jpg' in content_type else 'png'
            filename = f'mockup_{timestamp}_{random_id}.{ext}'
            filepath = os.path.join(LEADGEN_HOME, 'mockups', filename)
            os.makedirs(os.path.join(LEADGEN_HOME, 'mockups'), exist_ok=True)
            with open(filepath, 'wb') as f:
                f.write(image_bytes)
            # Return URL that the API can serve
            return f'/mockups/{filename}'
        else:
            # JSON response with URL
            data = json.loads(resp.read().decode())
            if isinstance(data, dict):
                return data.get('url') or data.get('image_url') or data.get('output', [None])[0] if isinstance(data.get('output'), list) else None
            return None
    except urllib.error.HTTPError as e:
        err = e.read().decode()[:200]
        print(f'imagine.art HTTP {e.code}: {err}')
    except Exception as e:
        print(f'imagine.art error: {e}')
    return None

def generate_image(business_name, niche, city, provider=None, custom_prompt=None):
    """Generate mockup using configured provider (or specified one)."""
    provider = provider or CONFIG['image_provider']
    if provider == 'replicate':
        return generate_mockup_replicate(business_name, niche, city, custom_prompt=custom_prompt)
    elif provider == 'imagine_art':
        return generate_mockup_imagine_art(business_name, niche, city, custom_prompt=custom_prompt)
    return None

def generate_mockup_for_lead(lead_id, custom_prompt=None):
    """Generate and save a mockup image for a single lead."""
    conn = db_conn(); cur = conn.cursor()
    cur.execute("SELECT business_name, niche, city, country FROM leads WHERE id=%s", (lead_id,))
    row = cur.fetchone(); cur.close(); conn.close()
    if not row:
        return {'error': 'Lead not found'}
    bname, niche, city, country = row
    provider = CONFIG.get('image_provider', 'none')
    if provider == 'none':
        return {'error': 'No image provider configured — set one in Settings (Replicate or imagine.art)'}
    mockup_url = generate_image(bname, niche or '', city or '', custom_prompt=custom_prompt)
    if not mockup_url:
        return {'error': 'Image generation failed — check your API key and provider settings'}
    conn = db_conn(); cur = conn.cursor()
    cur.execute("DELETE FROM assets WHERE lead_id=%s AND asset_type='mockup_image'", (lead_id,))
    cur.execute("INSERT INTO assets(lead_id,asset_type,content,model_used) VALUES(%s,'mockup_image',%s,%s)",
               (lead_id, mockup_url, provider))
    conn.commit(); cur.close(); conn.close()
    return {'success': True, 'mockup_url': mockup_url}

def get_search_batches():
    """Return a summary of each search batch (job) that created leads."""
    conn = db_conn(); cur = conn.cursor()
    cur.execute("""
        SELECT search_batch_id,
               MIN(niche) as niche, MIN(city) as city, MIN(country) as country,
               COUNT(*) as count,
               to_char(MIN(created_at), 'YYYY-MM-DD HH24:MI') as batch_date
        FROM leads
        WHERE search_batch_id IS NOT NULL AND search_batch_id != ''
        GROUP BY search_batch_id
        ORDER BY MIN(created_at) DESC
        LIMIT 100
    """)
    rows = [{'batch_id': r[0], 'niche': r[1], 'city': r[2], 'country': r[3],
             'count': r[4], 'date': r[5]} for r in cur.fetchall()]
    cur.close(); conn.close()
    return rows

def delete_search_batch(batch_id):
    """Delete all leads that were first found in a specific search batch."""
    conn = db_conn(); cur = conn.cursor()
    cur.execute("DELETE FROM leads WHERE search_batch_id=%s RETURNING id", (batch_id,))
    deleted = cur.rowcount
    conn.commit(); cur.close(); conn.close()
    return deleted

def delete_leads_bulk(lead_ids):
    """Delete arbitrary business leads by id (Leads page multi-select delete).
    Scoped to lead_type IS NULL so this can never remove Intent Search leads —
    those have their own delete endpoint (/intent-leads/<id>/delete)."""
    if not lead_ids:
        return 0
    conn = db_conn(); cur = conn.cursor()
    cur.execute("""DELETE FROM leads WHERE id = ANY(%s::uuid[]) AND lead_type IS NULL RETURNING id""",
                (lead_ids,))
    deleted = cur.rowcount
    conn.commit(); cur.close(); conn.close()
    return deleted

# ──────────────────────────────────────────────────────────────
#  CLAUDE EMAIL COPYWRITING
# ──────────────────────────────────────────────────────────────
def generate_email_copy(business_name, niche, city, owner_name=None):
    if not CONFIG.get('auto_email_copy', True):
        print('[claude] skipped: auto_email_copy disabled in settings')
        return None
    if not CLAUDE_KEY:
        print('[claude] skipped: no CLAUDE_KEY configured')
        return None
    name_part = owner_name if owner_name else 'there'
    prompt = f"""Write a 120-word personalized cold outreach message for a small business owner.

Business: {business_name}
Type: {niche}
City: {city}
Owner: {name_part}
Context: They have NO WEBSITE. I want to offer to build them a free mockup.

Requirements:
- Subject line: max 7 words, curiosity-driven
- Body: 100-130 words
- Mention we built a free website mockup for them
- Reference their specific niche
- Direct, friendly tone (NOT salesy)
- End with ONE clear question
- DON'T use: "I hope this finds you well", "reaching out", "synergy"

Respond ONLY with valid JSON:
{{"subject": "<subject>", "body": "<body with \\\\n for line breaks>"}}"""
    try:
        body = json.dumps({
            'model': 'claude-opus-4-5',
            'max_tokens': 500,
            'messages': [{'role': 'user', 'content': prompt}]
        }).encode()
        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=body, method='POST',
            headers={'x-api-key': CLAUDE_KEY, 'anthropic-version': '2023-06-01',
                    'Content-Type': 'application/json'}
        )
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read().decode())
        text = data['content'][0]['text']
        m = re.search(r'\{[\s\S]*\}', text)
        if m:
            log_api_usage('claude', 'email_copy')
            return json.loads(m.group())
    except Exception as e:
        print(f'Claude error: {e}')
    return None

# ──────────────────────────────────────────────────────────────
#  GEMINI SCORING
# ──────────────────────────────────────────────────────────────
def gemini_score(business_name, niche, city, phone, has_email, has_linkedin):
    prompt = f"""Score this B2B lead 1-10 for cold outreach.

Business: {business_name}
Type: {niche}
City: {city}
Phone: {'Yes' if phone else 'No'}
Email: {'Yes' if has_email else 'No'}
LinkedIn: {'Yes' if has_linkedin else 'No'}

Note: This business has NO WEBSITE.

Score: 9-10 (excellent), 7-8 (good), 5-6 (medium), 1-4 (low)
Respond ONLY with JSON: {{"score":<1-10>,"reason":"<1 sentence>","best_channel":"<WhatsApp|Email|Phone>"}}"""
    text = gemini_call(prompt, 150)
    if text:
        try:
            m = re.search(r'\{[\s\S]*\}', text)
            if m:
                log_api_usage('claude', 'score_fallback')
                return json.loads(m.group())
        except: pass
    return {'score': 5, 'reason': 'Default', 'best_channel': 'Phone'}

def score_all_enriched():
    conn = db_conn(); cur = conn.cursor()
    cur.execute("""SELECT l.id, l.business_name, l.niche, l.city, l.phone, c.email, c.linkedin_url
        FROM leads l LEFT JOIN contacts c ON c.lead_id = l.id
        WHERE l.status = 'enriched' AND l.ai_score IS NULL AND l.lead_type IS NULL
        ORDER BY l.created_at DESC""")
    leads = cur.fetchall()
    results = []
    for ld in leads:
        lead_id, bname, niche, city, phone, email, linkedin = ld
        try:
            s = gemini_score(bname, niche, city, phone, bool(email), bool(linkedin))
            score = int(s.get('score', 5))
            cur.execute("UPDATE leads SET ai_score=%s, score_reason=%s WHERE id=%s",
                       (score, str(s.get('reason', ''))[:500], lead_id))
            conn.commit()
            results.append({'business_name': bname, 'score': score})
            time.sleep(0.3)
        except Exception as e:
            print(f'Score error: {e}')
    cur.close(); conn.close()
    return results

def generate_assets_for_top_leads(min_score=5):
    """Only run if image_provider is set."""
    if CONFIG['image_provider'] == 'none' and not CONFIG['auto_email_copy']:
        return []
    conn = db_conn(); cur = conn.cursor()
    cur.execute("""SELECT l.id, l.business_name, l.niche, l.city, c.full_name
        FROM leads l LEFT JOIN contacts c ON c.lead_id = l.id
        WHERE l.status = 'enriched' AND l.ai_score >= %s AND l.lead_type IS NULL
        AND NOT EXISTS (SELECT 1 FROM assets WHERE lead_id = l.id AND asset_type = 'email_body')
        ORDER BY l.ai_score DESC""", (min_score,))
    leads = cur.fetchall(); results = []
    for ld in leads:
        lead_id, bname, niche, city, owner = ld
        try:
            mockup_url = None
            if CONFIG['image_provider'] != 'none':
                mockup_url = generate_image(bname, niche, city)
                if mockup_url:
                    cur.execute("INSERT INTO assets(lead_id,asset_type,content,model_used) VALUES(%s,'mockup_image',%s,%s)",
                               (lead_id, mockup_url, CONFIG['image_provider']))
            if CONFIG['auto_email_copy']:
                email = generate_email_copy(bname, niche, city, owner)
                if email:
                    cur.execute("INSERT INTO assets(lead_id,asset_type,content,model_used) VALUES(%s,'email_subject',%s,'claude')",
                               (lead_id, email.get('subject', '')))
                    cur.execute("INSERT INTO assets(lead_id,asset_type,content,model_used) VALUES(%s,'email_body',%s,'claude')",
                               (lead_id, email.get('body', '')))
            cur.execute("UPDATE leads SET status='ready' WHERE id=%s", (lead_id,))
            conn.commit()
            results.append({'business_name': bname, 'mockup': bool(mockup_url),
                          'email_subject': (email or {}).get('subject') if 'email' in locals() else None})
            time.sleep(0.5)
        except Exception as e:
            print(f'Assets error: {e}')
    cur.close(); conn.close()
    return results


# ──────────────────────────────────────────────────────────────
#  M2: FREE HUNTER.IO ALTERNATIVE
# ──────────────────────────────────────────────────────────────
def guess_domain_from_business(business_name):
    """Try to find the domain associated with a business name."""
    # Strategy 1: Search Google for official site
    data = serper_search(f'"{business_name}" official site', 5)
    for item in data.get('organic', []):
        link = item.get('link', '')
        if any(skip in link for skip in ['facebook.com', 'linkedin.com', 'instagram.com',
                                          'twitter.com', 'yellowpages', 'yelp', 'tripadvisor',
                                          'google.com', 'wikipedia']):
            continue
        if '/' in link:
            domain = link.split('/')[2].replace('www.', '')
            return domain
    # Strategy 2: Heuristic guess (common patterns)
    clean = re.sub(r'\\W+', '', business_name.lower())[:30]
    return f"{clean}.com"

def check_domain_has_mx(domain):
    """Check if a domain has MX records (can receive email)."""
    import socket
    try:
        # Try to resolve - quick check
        socket.gethostbyname(domain)
        # Try DNS MX lookup using subprocess (most systems have dig/host)
        import subprocess
        try:
            result = subprocess.run(['dig', '+short', 'MX', domain],
                                  capture_output=True, text=True, timeout=5)
            return bool(result.stdout.strip())
        except:
            pass
        return True  # Domain resolves at least
    except:
        return False

def generate_email_patterns(domain, first_name='', last_name=''):
    """Generate likely email addresses for a domain."""
    patterns = []
    # Generic role-based emails
    for role in ['info', 'contact', 'hello', 'support', 'sales', 'admin', 'office']:
        patterns.append({'email': f'{role}@{domain}', 'type': 'role', 'confidence': 60})

    if first_name:
        fn = first_name.lower()
        ln = last_name.lower() if last_name else ''
        # Person-based patterns
        patterns.append({'email': f'{fn}@{domain}', 'type': 'first', 'confidence': 70})
        if ln:
            patterns.extend([
                {'email': f'{fn}.{ln}@{domain}', 'type': 'first.last', 'confidence': 85},
                {'email': f'{fn}{ln}@{domain}', 'type': 'firstlast', 'confidence': 65},
                {'email': f'{fn[0]}{ln}@{domain}', 'type': 'flast', 'confidence': 60},
                {'email': f'{fn}_{ln}@{domain}', 'type': 'first_last', 'confidence': 50},
                {'email': f'{ln}@{domain}', 'type': 'last', 'confidence': 40},
                {'email': f'{ln}.{fn}@{domain}', 'type': 'last.first', 'confidence': 30},
            ])
    return patterns

def scrape_about_page_for_emails(domain):
    """Use Crawl4AI to scrape the About/Contact page for real emails."""
    emails_found = set()
    paths = ['/about', '/contact', '/about-us', '/contact-us', '/team', '/']
    for path in paths:
        url = f'https://{domain}{path}'
        try:
            body = json.dumps({
                'urls': url,
                'priority': 5,
                'crawler_params': {'headless': True}
            }).encode()
            req = urllib.request.Request(
                f'{CRAWL4AI_URL}/crawl',
                data=body, method='POST',
                headers={'Authorization': f'Bearer {CRAWL4AI_TOKEN}',
                        'Content-Type': 'application/json'}
            )
            resp = urllib.request.urlopen(req, timeout=30)
            result = json.loads(resp.read().decode())
            text = ''
            if 'markdown' in result: text += result['markdown']
            if 'html' in result: text += result['html'][:10000]
            elif 'results' in result and result['results']:
                first = result['results'][0]
                if isinstance(first, dict):
                    text += first.get('markdown', '') + first.get('cleaned_html', '')[:10000]

            for email in extract_emails(text):
                if domain in email or domain.split('.')[0] in email:
                    emails_found.add(email)
            if emails_found: break  # found some, no need to try more pages
        except: pass
    return list(emails_found)

def find_emails(business_name='', domain='', first_name='', last_name=''):
    """Free Hunter.io alternative: find real emails for a business."""
    result = {
        'business': business_name,
        'domain': domain,
        'verified_emails': [],
        'pattern_guesses': [],
        'mx_valid': False
    }

    if not domain and business_name:
        domain = guess_domain_from_business(business_name)
        result['domain'] = domain

    if domain:
        result['mx_valid'] = check_domain_has_mx(domain)

        # Strategy 1: Scrape About/Contact pages (real emails) — verify up to
        # 3; each SMTP probe takes a few seconds so we keep the tool responsive
        real_emails = scrape_about_page_for_emails(domain)
        for email in real_emails[:3]:
            # Verify each found address so the UI shows real deliverability
            vr = verify_email(email)
            result['verified_emails'].append({
                'email': email,
                'source': 'about_page',
                'confidence': 90 if vr['status'] == 'deliverable'
                              else 75 if vr['status'] == 'risky' else 30,
                'status': vr['status'],
                'details': vr['details'][:2]
            })

        # Strategy 2: Pattern generation (unverified guesses — clearly labeled)
        if result['mx_valid']:
            patterns = generate_email_patterns(domain, first_name, last_name)
            result['pattern_guesses'] = [
                {'email': p, 'note': 'unverified pattern — verify before sending'}
                if isinstance(p, str) else p for p in patterns
            ]

    return result

# ──────────────────────────────────────────────────────────────
#  M2: FREE APOLLO.IO ALTERNATIVE
# ──────────────────────────────────────────────────────────────
def find_people(company_name, titles=None, location=''):
    """Free Apollo.io alternative: find decision makers at a company."""
    titles = titles or ['CEO', 'Founder', 'Owner', 'Director', 'Manager',
                       'CTO', 'CFO', 'COO', 'Head of', 'VP']
    result = {
        'company': company_name,
        'location': location,
        'people': [],
        'total_found': 0
    }

    seen_urls = set()

    # Strategy 1: LinkedIn dorks for each title
    for title in titles[:5]:  # Limit to top 5 titles to save Serper credits
        query = f'site:linkedin.com/in "{company_name}" "{title}"'
        if location: query += f' "{location}"'
        data = serper_search(query, 5)

        for item in data.get('organic', []):
            link = item.get('link', '')
            if 'linkedin.com/in/' not in link: continue
            link = link.split('?')[0]
            if link in seen_urls: continue
            seen_urls.add(link)

            t = item.get('title', '')
            snippet = item.get('snippet', '')

            # Extract name (before ' - ' or ' | ')
            name_match = re.match(r'^([^\\-|]+?)\\s*[\\-|]', t)
            name = name_match.group(1).strip() if name_match else t

            # Extract job title from title text
            title_match = re.search(r'[\\-|]\\s*([^\\-|@]+?)(?:\\s+at\\s+|\\s*$)', t, re.IGNORECASE)
            job_title = title_match.group(1).strip() if title_match else title

            result['people'].append({
                'name': name,
                'title': job_title,
                'linkedin_url': link,
                'snippet': snippet[:200],
                'source': f'linkedin_dork:{title}'
            })

    # Strategy 2: About/Team page scraping
    if len(result['people']) < 3:
        domain = guess_domain_from_business(company_name)
        if domain:
            for path in ['/team', '/about', '/staff', '/people']:
                url = f'https://{domain}{path}'
                try:
                    text = oxylabs_scrape(url, 'markdown') if OXYLABS else None
                    if text:
                        # Look for "Name - Title" patterns
                        pattern_matches = re.findall(r'([A-Z][a-z]+\\s+[A-Z][a-z]+)\\s*[-\\u2013]\\s*([A-Z][a-zA-Z\\s]+)', text)
                        for name, title in pattern_matches[:5]:
                            result['people'].append({
                                'name': name.strip(),
                                'title': title.strip(),
                                'linkedin_url': '',
                                'snippet': f'Found on {path}',
                                'source': f'team_page_scrape'
                            })
                        if pattern_matches: break
                except: pass

    result['total_found'] = len(result['people'])
    return result

# ──────────────────────────────────────────────────────────────
#  M2: WAYBACK MACHINE INTEGRATION (free)
# ──────────────────────────────────────────────────────────────
def wayback_snapshots(url, limit=5):
    """Get historical snapshots of a URL from Wayback Machine."""
    try:
        # Get availability info first
        api_url = f'http://archive.org/wayback/available?url={urllib.parse.quote(url)}'
        resp = urllib.request.urlopen(api_url, timeout=15)
        avail = json.loads(resp.read().decode())

        result = {
            'url': url,
            'first_snapshot': None,
            'latest_snapshot': None,
            'snapshots': []
        }

        if 'archived_snapshots' in avail and 'closest' in avail['archived_snapshots']:
            closest = avail['archived_snapshots']['closest']
            result['latest_snapshot'] = {
                'timestamp': closest.get('timestamp', ''),
                'url': closest.get('url', ''),
                'status': closest.get('status', '')
            }

        # Get CDX API for multiple snapshots over time
        cdx_url = f'http://web.archive.org/cdx/search/cdx?url={urllib.parse.quote(url)}&output=json&limit={limit*2}&fl=timestamp,original,statuscode'
        resp2 = urllib.request.urlopen(cdx_url, timeout=15)
        cdx = json.loads(resp2.read().decode())
        if len(cdx) > 1:
            for row in cdx[1:limit+1]:
                if len(row) >= 3:
                    ts = row[0]
                    formatted = f'{ts[:4]}-{ts[4:6]}-{ts[6:8]}'
                    result['snapshots'].append({
                        'date': formatted,
                        'snapshot_url': f'https://web.archive.org/web/{ts}/{row[1]}',
                        'status': row[2]
                    })
            if cdx[1]:
                result['first_snapshot'] = {
                    'timestamp': cdx[1][0],
                    'date': f'{cdx[1][0][:4]}-{cdx[1][0][4:6]}-{cdx[1][0][6:8]}'
                }
        return result
    except Exception as e:
        return {'error': str(e), 'url': url}

# ──────────────────────────────────────────────────────────────
#  M2: GOOGLE TRENDS (free, via Serper + scraping)
# ──────────────────────────────────────────────────────────────
def google_trends(keyword, geo=''):
    """Get trend data for a keyword using free approach."""
    result = {
        'keyword': keyword,
        'geo': geo,
        'rising_queries': [],
        'related_queries': [],
        'trending_topics': []
    }

    # Strategy 1: Serper related queries (already returns trend signal)
    search_q = f'{keyword} trend rising popular'
    if geo: search_q += f' {geo}'
    data = serper_search(search_q, 10)

    for rel in data.get('relatedSearches', []):
        result['related_queries'].append(rel.get('query', ''))

    for paa in data.get('peopleAlsoAsk', []):
        result['rising_queries'].append({
            'query': paa.get('question', ''),
            'snippet': paa.get('snippet', '')[:150]
        })

    # Strategy 2: Google autocomplete (proxy for popularity)
    try:
        url = f'http://suggestqueries.google.com/complete/search?client=firefox&q={urllib.parse.quote(keyword)}'
        resp = urllib.request.urlopen(url, timeout=10)
        suggestions = json.loads(resp.read().decode())
        if isinstance(suggestions, list) and len(suggestions) > 1:
            result['trending_topics'] = suggestions[1][:15]
    except: pass

    return result

# ──────────────────────────────────────────────────────────────
#  M2: SOCIAL MEDIA SCOUT
# ──────────────────────────────────────────────────────────────
def social_scout(niche, location='', platforms=None):
    """Find top accounts in a niche across social platforms."""
    platforms = platforms or ['instagram', 'tiktok', 'youtube', 'twitter', 'linkedin']
    result = {
        'niche': niche,
        'location': location,
        'profiles': {}
    }

    platform_sites = {
        'instagram': 'instagram.com',
        'tiktok': 'tiktok.com',
        'youtube': 'youtube.com',
        'twitter': 'twitter.com',
        'linkedin': 'linkedin.com/company',
        'facebook': 'facebook.com'
    }

    for plat in platforms:
        if plat not in platform_sites: continue
        site = platform_sites[plat]
        query = f'site:{site} "{niche}"'
        if location: query += f' "{location}"'
        data = serper_search(query, 8)

        profiles = []
        seen = set()
        for item in data.get('organic', []):
            link = item.get('link', '')
            if site not in link or link in seen: continue
            seen.add(link)
            profiles.append({
                'url': link.split('?')[0],
                'title': item.get('title', ''),
                'snippet': item.get('snippet', '')[:200]
            })
            if len(profiles) >= 5: break
        result['profiles'][plat] = profiles
    return result

# ──────────────────────────────────────────────────────────────
#  M2: DOMAIN INTELLIGENCE (DNS, tech stack, age)
# ──────────────────────────────────────────────────────────────
def domain_intel(domain):
    """Get DNS info, tech stack hints, and basic intelligence about a domain."""
    result = {
        'domain': domain,
        'dns': {},
        'has_https': False,
        'tech_hints': [],
        'title': '',
        'description': '',
        'ssl_valid': False
    }

    import socket
    # DNS A record
    try:
        ip = socket.gethostbyname(domain)
        result['dns']['ip'] = ip
        result['dns']['resolves'] = True
    except:
        result['dns']['resolves'] = False
        return result

    # Try MX
    try:
        import subprocess
        mx = subprocess.run(['dig', '+short', 'MX', domain], capture_output=True, text=True, timeout=5)
        if mx.stdout.strip():
            result['dns']['mx_records'] = mx.stdout.strip().split('\\n')
    except: pass

    # Fetch homepage for tech hints
    try:
        req = urllib.request.Request(f'https://{domain}', headers={'User-Agent': 'Mozilla/5.0 LeadGenBot'})
        resp = urllib.request.urlopen(req, timeout=10)
        html = resp.read(50000).decode('utf-8', errors='replace')
        result['has_https'] = True
        result['ssl_valid'] = True

        # Title
        tm = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
        if tm: result['title'] = tm.group(1).strip()[:200]

        # Description
        dm = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)', html, re.IGNORECASE)
        if dm: result['description'] = dm.group(1).strip()[:300]

        # Tech hints
        tech_patterns = {
            'WordPress': ['wp-content', 'wp-includes', 'wp-json'],
            'Shopify': ['cdn.shopify.com', 'shopify.com/s/', 'Shopify.theme'],
            'Wix': ['wix.com', 'wixstatic.com', '_wix'],
            'Squarespace': ['squarespace.com', 'sqsp.com'],
            'Webflow': ['webflow.com', 'wf-design-system'],
            'React': ['react', '_next/', '__NEXT_DATA__'],
            'Vue': ['vue.js', 'v-bind', 'data-v-'],
            'Angular': ['ng-app', 'angular.js'],
            'jQuery': ['jquery'],
            'Bootstrap': ['bootstrap.min.css', 'bootstrap-'],
            'Tailwind': ['tailwindcss', 'tw-'],
            'Google Analytics': ['google-analytics.com', 'gtag('],
            'Facebook Pixel': ['fbq(', 'fbevents.js'],
            'Cloudflare': ['cloudflare', '__cf_bm'],
            'Stripe': ['stripe.com/v3'],
            'PayPal': ['paypal.com']
        }
        for tech, keywords in tech_patterns.items():
            if any(k.lower() in html.lower() for k in keywords):
                result['tech_hints'].append(tech)
    except Exception as e:
        result['error'] = str(e)

    return result

# ──────────────────────────────────────────────────────────────
#  EMAIL VERIFICATION ENGINE (dnspython + SMTP RCPT probes)
#  Status values stored on contacts.email_status:
#    deliverable  — SMTP server confirmed the mailbox exists (not catch-all)
#    risky        — catch-all domain, role account, or inconclusive server
#    undeliverable— hard rejection: bad syntax/domain/MX or SMTP 550-class
#    unknown      — could not check (network error, timeout, no dnspython)
# ──────────────────────────────────────────────────────────────
try:
    import dns.resolver
    _DNSPY_OK = True
except ImportError:
    _DNSPY_OK = False
    print('WARNING: dnspython not installed — email verification is limited. Fix: pip install dnspython')

VERIFY_HELO_DOMAIN = os.environ.get('VERIFY_HELO_DOMAIN', 'controvallc.com')
VERIFY_MAIL_FROM   = os.environ.get('VERIFY_MAIL_FROM', f'verify@{VERIFY_HELO_DOMAIN}')
EMAIL_STALE_DAYS   = 60   # re-verify stored emails older than this

ROLE_LOCALS = {
    'info', 'contact', 'hello', 'admin', 'sales', 'support', 'team', 'mail',
    'office', 'help', 'enquiry', 'enquiries', 'inquiry', 'reception', 'booking',
    'bookings', 'welcome', 'noreply', 'no-reply', 'service', 'accounts', 'billing',
}
DISPOSABLE_DOMAINS = {
    'mailinator.com', 'tempmail.com', 'temp-mail.org', '10minutemail.com',
    'guerrillamail.com', 'yopmail.com', 'throwawaymail.com', 'sharklasers.com',
    'getnada.com', 'dispostable.com', 'trashmail.com', 'fakeinbox.com',
    'maildrop.cc', 'mailnesia.com', 'mytemp.email', 'tempinbox.com',
}
FREE_EMAIL_PROVIDERS = {
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'icloud.com',
    'aol.com', 'protonmail.com', 'proton.me', 'mail.com', 'gmx.com',
    'live.com', 'msn.com', 'zoho.com', 'yandex.com', 'hey.com', 'fastmail.com',
}

def _mx_hosts(domain):
    """Return [(priority, host)] via dnspython, falling back to [] on failure."""
    if not _DNSPY_OK:
        return []
    try:
        answers = dns.resolver.resolve(domain, 'MX', lifetime=5)
        hosts = [(a.preference, str(a.exchange).rstrip('.')) for a in answers if str(a.exchange) != '.']
        hosts.sort()
        return hosts
    except Exception:
        return []

def _smtp_probe(mx_host, emails):
    """Open one SMTP conversation and RCPT-probe each address.
    Returns a dict {email: (code, message)} — code None means the conversation
    broke down (treat as inconclusive)."""
    import smtplib
    out = {}
    smtp = smtplib.SMTP(timeout=10)
    try:
        smtp.connect(mx_host, 25)
    except Exception as e:
        return {a: (None, f'connect failed: {str(e)[:80]}') for a in emails}

    try:
        # Upgrade to TLS when offered; some builds need _host set explicitly
        # for certificate validation, and a failed upgrade leaves the socket
        # closed — reconnect plain in that case (the RCPT probe still works).
        try:
            smtp._host = mx_host
            smtp.starttls()
            smtp.ehlo(VERIFY_HELO_DOMAIN)
        except Exception:
            try: smtp.quit()
            except Exception: pass
            try: smtp.close()
            except Exception: pass
            try:
                smtp = smtplib.SMTP(timeout=10)
                smtp.connect(mx_host, 25)
            except Exception as e:
                return {a: (None, f'reconnect failed: {str(e)[:80]}') for a in emails}

        smtp.helo(VERIFY_HELO_DOMAIN)
        smtp.mail(VERIFY_MAIL_FROM)
        for addr in emails:
            try:
                code, msg = smtp.rcpt(addr)
                out[addr] = (code, msg.decode() if isinstance(msg, bytes) else str(msg))
            except smtplib.SMTPServerDisconnected:
                out[addr] = (None, 'server disconnected during RCPT')
                break
            except Exception as e:
                out[addr] = (None, str(e)[:120])
    finally:
        try: smtp.quit()
        except Exception: pass
    return out

def verify_email(email, probe_catch_all=True):
    """Verify an email address: syntax → disposable → DNS/MX → SMTP RCPT → catch-all.
    Never raises; always returns a result dict."""
    result = {
        'email': email,
        'syntax_valid': bool(EMAIL_RE.match(email or '')),
        'domain_resolves': False,
        'has_mx': False,
        'mailbox_exists': None,      # None=not checked, True/False=checked
        'catch_all': None,
        'is_role': False,
        'is_free': False,
        'is_disposable': False,
        'status': 'unknown',         # deliverable | risky | undeliverable | unknown
        'risk_level': 'unknown',     # low | medium | high (legacy field used by UI)
        'details': [],
        'checked_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }
    if not result['syntax_valid']:
        result['status'] = 'undeliverable'
        result['risk_level'] = 'high'
        result['details'].append('Invalid email syntax')
        return result

    local, domain = email.rsplit('@', 1)
    local, domain = local.lower(), domain.lower()
    result['is_role'] = local in ROLE_LOCALS or local.split('+')[0] in ROLE_LOCALS
    result['is_free'] = domain in FREE_EMAIL_PROVIDERS
    result['is_disposable'] = domain in DISPOSABLE_DOMAINS
    if result['is_disposable']:
        result['status'] = 'undeliverable'
        result['risk_level'] = 'high'
        result['details'].append('Disposable/temporary email domain')
        return result

    # Step 1: domain resolves (A or MX)
    try:
        socket.gethostbyname(domain)
        result['domain_resolves'] = True
    except Exception:
        # no A record — maybe MX-only domain
        if _mx_hosts(domain):
            result['domain_resolves'] = True
        else:
            result['status'] = 'undeliverable'
            result['risk_level'] = 'high'
            result['details'].append('Domain does not resolve')
            return result

    # Step 2: MX records
    mx_hosts = _mx_hosts(domain)
    if mx_hosts:
        result['has_mx'] = True
    elif result['is_free']:
        result['status'] = 'risky'
        result['risk_level'] = 'medium'
        result['details'].append('Free provider with no reachable MX — cannot verify')
        return result
    else:
        # No MX: some small hosts accept mail on their A record
        try:
            mx_hosts = [(10, domain)]
            result['details'].append('No MX record — probing A record as fallback')
        except Exception:
            pass

    # Step 3: SMTP mailbox probe
    probed = _smtp_probe(mx_hosts[0][1], [email])
    code, msg = probed.get(email, (None, 'no response'))

    if code == 250:
        result['mailbox_exists'] = True
        # Step 4: catch-all detection — does the server also accept random mailboxes?
        if probe_catch_all:
            rand_local = 'zz-probe-' + _h_secrets.token_hex(4)
            rand_addr = f'{rand_local}@{domain}'
            r2 = _smtp_probe(mx_hosts[0][1], [rand_addr]).get(rand_addr, (None, ''))
            if r2[0] == 250:
                result['catch_all'] = True
                result['status'] = 'risky'
                result['risk_level'] = 'medium'
                result['details'].append('Catch-all domain — server accepts any address; mailbox not confirmed')
            else:
                result['catch_all'] = False
                result['status'] = 'deliverable'
                result['risk_level'] = 'low'
                result['details'].append(f'SMTP {mx_hosts[0][1]} confirmed mailbox (250)')
        else:
            result['catch_all'] = False
            result['status'] = 'deliverable'
            result['risk_level'] = 'low'
            result['details'].append(f'SMTP {mx_hosts[0][1]} accepted recipient (250)')
        if result['is_role']:
            result['details'].append('Role account (info@/contact@…) — not a specific person')
    elif code in (550, 551, 553):
        result['mailbox_exists'] = False
        result['status'] = 'undeliverable'
        result['risk_level'] = 'high'
        result['details'].append(f'SMTP rejected recipient (code {code}): {msg[:100]}')
    elif code is not None:
        # 4xx temporary failures, 251/252 forward/verify responses → inconclusive
        result['details'].append(f'SMTP returned code {code} (inconclusive): {msg[:100]}')
        result['status'] = 'risky' if code in (251, 252) else 'unknown'
        result['risk_level'] = 'medium'
    else:
        result['details'].append(f'SMTP check failed: {msg[:100]}')
        result['status'] = 'unknown'
        result['risk_level'] = 'medium'

    if result['is_free'] and result['status'] == 'unknown':
        result['details'].append('Free providers often hide mailbox existence')

    # Fallback: when our own SMTP probe is inconclusive and an external
    # verifier is configured, let it settle the question (their servers
    # aren't port-25-blocked and they handle greylisting).
    if result['status'] == 'unknown':
        mv = _millionverifier_check(email)
        if mv:
            result['status'] = mv['status']
            result['risk_level'] = {'deliverable': 'low', 'risky': 'medium',
                                    'undeliverable': 'high', 'unknown': 'medium'}[mv['status']]
            result['details'].append(f"MillionVerifier: {mv['raw']}")
            if mv['status'] == 'deliverable':
                result['mailbox_exists'] = True
            elif mv['status'] == 'undeliverable':
                result['mailbox_exists'] = False
    return result

def _millionverifier_check(email):
    log_api_usage('millionverifier', 'verify', meta=email[:200])
    """Optional external verification via MillionVerifier (~$1/1000 checks).
    Returns {'status': deliverable|risky|undeliverable|unknown, 'raw': code}
    or None when unconfigured/unreachable. API result codes:
    good / bad / catchall / disposable / unknown / invalid."""
    if not MILLIONVERIFIER_KEY:
        return None
    try:
        url = (f'https://api.millionverifier.com/api/v3/?api={MILLIONVERIFIER_KEY}'
               f'&email={urllib.parse.quote_plus(email)}')
        req = urllib.request.Request(url, headers={'User-Agent': 'controva-leadgen/1.0'})
        data = json.loads(urllib.request.urlopen(req, timeout=20).read().decode())
        raw = str(data.get('result', '')).lower()
        mapping = {
            'good':      'deliverable',
            'bad':       'undeliverable',
            'invalid':   'undeliverable',
            'disposable':'undeliverable',
            'catchall':  'risky',
            'unknown':   'unknown',
        }
        status = mapping.get(raw, 'unknown')
        return {'status': status, 'raw': raw}
    except Exception as e:
        print(f'[millionverifier] {email}: {e}')
        return None

# ──────────────────────────────────────────────────────────────
#  M2b: CONTACT EMAIL GATING — no send without verification
# ──────────────────────────────────────────────────────────────
def ensure_email_verification_columns():
    """Add email verification columns to contacts if missing (idempotent)."""
    conn = db_conn(); cur = conn.cursor()
    cur.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS email_status VARCHAR(20)")
    cur.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS email_checked_at TIMESTAMPTZ")
    cur.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS email_method VARCHAR(60)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_contacts_email_status ON contacts(email_status)")
    conn.commit(); cur.close(); conn.close()

def verify_and_store_contact_email(lead_id, email, source=''):
    """Verify an email and write the outcome onto the lead's best contact row.
    Returns the verification result dict."""
    vr = verify_email(email)
    try:
        conn = db_conn(); cur = conn.cursor()
        cur.execute("""
            UPDATE contacts SET email_status = %s, email_checked_at = NOW()
            WHERE lead_id = %s AND LOWER(email) = LOWER(%s)
        """, (vr['status'], lead_id, email))
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        print(f'[verify] could not store status for {email}: {e}')
    return vr

def contact_email_for_sending(lead_id):
    """Return (email, status) for the lead's best contact, re-verifying when
    the stored status is missing or stale (older than EMAIL_STALE_DAYS).
    Emails marked undeliverable are never returned."""
    conn = db_conn(); cur = conn.cursor()
    cur.execute("""
        SELECT email, email_status, email_checked_at FROM contacts
        WHERE lead_id = %s AND COALESCE(email,'') != ''
        ORDER BY (email_status = 'deliverable') DESC, confidence DESC NULLS LAST, created_at DESC
        LIMIT 1
    """, (lead_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row:
        return None, 'no_contact'

    email, status, checked_at = row
    if status == 'undeliverable':
        return email, 'undeliverable'

    stale = True
    if status in ('deliverable', 'risky') and checked_at is not None:
        age_days = (datetime_now() - checked_at.replace(tzinfo=None)).days
        stale = age_days > EMAIL_STALE_DAYS

    if status not in ('deliverable', 'risky') or stale:
        vr = verify_and_store_contact_email(lead_id, email)
        status = vr['status']
    return email, status

def datetime_now():
    from datetime import datetime as _dt
    return _dt.utcnow()

# ──────────────────────────────────────────────────────────────
#  M2: BACKLINK DISCOVERY (free via Serper)
# ──────────────────────────────────────────────────────────────
def find_backlinks(target_url):
    """Find sites linking to a target URL (using inurl: operator)."""
    domain = target_url.replace('https://', '').replace('http://', '').split('/')[0]
    result = {
        'target': target_url,
        'domain': domain,
        'backlinks': []
    }
    queries = [
        f'"{domain}" -site:{domain}',
        f'link:{domain} -site:{domain}',
    ]
    seen = set()
    for q in queries:
        data = serper_search(q, 10)
        for item in data.get('organic', []):
            link = item.get('link', '')
            if domain in link or link in seen: continue
            seen.add(link)
            result['backlinks'].append({
                'source_url': link,
                'title': item.get('title', ''),
                'snippet': item.get('snippet', '')[:200]
            })
            if len(result['backlinks']) >= 20: break
        if len(result['backlinks']) >= 20: break
    return result


# ──────────────────────────────────────────────────────────────
#  INTENT ENGINE — bidirectional search
#  DEMAND  = find who needs the service (buyer intent)
#  SUPPLY  = find who provides the service (seller intent)
# ──────────────────────────────────────────────────────────────
INTENT_SOURCE_LABELS = {
    'linkedin_jobs': 'LinkedIn Jobs', 'reddit_forhire': 'Reddit /r/forhire',
    'reddit_general': 'Reddit (hiring)', 'hn_hiring': 'HN Who Is Hiring',
    'twitter_x': 'Twitter / X', 'indeed': 'Indeed', 'wellfound': 'Wellfound',
    'generic_hiring': 'Generic web (hiring)', 'generic_looking': 'Generic web (looking)',
    'craigslist_gigs': 'Craigslist Gigs', 'upwork_jobs': 'Upwork job posts',
    'craigslist_live': 'Craigslist (live)', 'reddit_live': 'Reddit (live)',
    'freelancer_live': 'Freelancer.com (live)', 'guru_jobs': 'Guru.com jobs',
    'remoteok': 'RemoteOK jobs',
    'fiverr_requests': 'Fiverr buyer requests', 'facebook_groups': 'Facebook Groups',
    'linkedin_profile': 'LinkedIn /in/', 'github': 'GitHub',
    'stackoverflow': 'Stack Overflow', 'upwork_profiles': 'Upwork freelancers',
    'behance': 'Behance', 'dribbble': 'Dribbble',
    'open_to_work': '"Open to work"', 'generic_provide': 'Generic web (for hire)',
    'fiverr_sellers': 'Fiverr sellers', 'contra': 'Contra freelancers',
    'toptal': 'Toptal', 'personal_portfolio': 'Personal portfolio site',
}

# Confidence bands — same plain-language pattern used across professional
# intent platforms (Apollo: Low/Mid/High, Bombora/ZoomInfo: threshold bands)
# instead of showing a bare percentage with no context.
def confidence_band(pct):
    if pct >= 75: return 'High'
    if pct >= 55: return 'Medium'
    return 'Low'

def intent_search_dorks(query, direction, location=''):
    q = query.strip()
    loc = f' "{location}"' if location else ''
    if direction == 'demand':
        return [
            ('linkedin_jobs',    f'site:linkedin.com/jobs "{q}"{loc}'),
            ('reddit_forhire',   f'site:reddit.com/r/forhire "{q}"'),
            ('reddit_general',   f'site:reddit.com "hiring {q}"'),
            ('hn_hiring',        f'site:news.ycombinator.com "{q}" hiring'),
            ('twitter_x',        f'(site:twitter.com OR site:x.com) "hiring {q}"'),
            ('indeed',           f'site:indeed.com "{q}"{loc}'),
            ('wellfound',        f'(site:wellfound.com OR site:angel.co) "{q}"'),
            ('craigslist_gigs',  f'site:craigslist.org "{q}" gigs{loc}'),
            ('upwork_jobs',      f'site:upwork.com/jobs "{q}"'),
            ('guru_jobs',        f'site:guru.com "{q}"'),
            ('remoteok',         f'site:remoteok.com "{q}"'),
            ('fiverr_requests',  f'site:fiverr.com "buyer request" "{q}"'),
            ('facebook_groups',  f'site:facebook.com/groups "looking for {q}"{loc}'),
            ('generic_hiring',   f'"we are hiring" "{q}"{loc}'),
            ('generic_looking',  f'"looking for {q}"{loc}'),
        ]
    elif direction == 'supply':
        return [
            ('linkedin_profile', f'site:linkedin.com/in/ "{q}"{loc}'),
            ('github',           f'site:github.com "{q}"{loc}'),
            ('stackoverflow',    f'site:stackoverflow.com/users "{q}"'),
            ('upwork_profiles',  f'site:upwork.com/freelancers "{q}"'),
            ('fiverr_sellers',   f'site:fiverr.com "{q}"'),
            ('contra',           f'site:contra.com "{q}"'),
            ('toptal',           f'site:toptal.com "{q}"'),
            ('behance',          f'site:behance.net "{q}"'),
            ('dribbble',         f'site:dribbble.com "{q}"'),
            ('open_to_work',     f'"{q}" ("open to work" OR "available for hire")'),
            ('generic_provide',  f'"{q}" "for hire"{loc}'),
        ]
    return []

def serper_search_with_recency(query, num=10, recency_days=30):
    log_api_usage('serper', 'intent_search', meta=query[:200])
    """Serper search with Google date filter (qdr param)."""
    if   recency_days <= 1:   tbs = 'qdr:d'
    elif recency_days <= 7:   tbs = 'qdr:w'
    elif recency_days <= 31:  tbs = 'qdr:m'
    elif recency_days <= 365: tbs = 'qdr:y'
    else: tbs = None
    body_dict = {'q': query, 'num': num}
    if tbs: body_dict['tbs'] = tbs
    body = json.dumps(body_dict).encode()
    return _serper_request('https://google.serper.dev/search', body, 15, 'Serper intent')

def _intent_heuristic_classify(item, query, direction):
    """Keyword-based fallback when Gemini is rate-limited or fails."""
    title = (item.get('title') or '').lower()
    snippet = (item.get('snippet') or '').lower()
    url = (item.get('url') or item.get('link') or '').lower()
    source = (item.get('source') or '').lower()
    blob = title + ' ' + snippet
    q = query.lower()
    if q not in blob and not any(w in blob for w in q.split() if len(w) > 3):
        return None
    if direction == 'demand':
        demand_signals = ['hiring', 'we need', 'looking for', 'we are looking',
                         '[for hire]', '[hiring]', 'job opening', 'wanted',
                         'recruiting', 'apply now', 'job description', 'employment',
                         'join our team', 'open position', 'now hiring']
        match_count = sum(1 for s in demand_signals if s in blob)
        is_active = (match_count > 0 or '/jobs/' in url or '/r/forhire' in url
                     or 'indeed.com' in url or 'wellfound' in url
                     or 'linkedin.com/jobs' in url or 'hn_hiring' in source)
        confidence = min(45 + match_count * 12, 78)
        who_field = 'poster_or_company'
    else:
        supply_signals = ['portfolio', 'for hire', 'available', 'freelance', 'consultant',
                         'open to work', 'years experience', 'expert in', 'specialist',
                         'i build', 'i create', 'i develop', 'my work']
        match_count = sum(1 for s in supply_signals if s in blob)
        is_active = (match_count > 0 or '/in/' in url or 'github.com' in url
                     or 'stackoverflow.com/users' in url or 'behance.net' in url
                     or 'dribbble.com' in url)
        confidence = min(45 + match_count * 12, 78)
        who_field = 'provider_name'
    if not is_active: return None
    name = (item.get('title') or '').split(' - ')[0].split(' | ')[0].strip()[:200] or 'Unknown'
    return {
        'is_active_intent': True, 'confidence': confidence,
        'role_or_service': query, 'location_hint': '', 'contact_hint': '',
        who_field: name, 'reasoning': f'Heuristic match ({match_count} signals)',
        'posted_recency': 'unknown', '_source': 'heuristic'
    }

def classify_intent_batch(items, query, direction):
    """One Gemini call for up to ~15 items. Falls back to heuristic per item on failure."""
    if not items: return []
    batch = items[:15]
    items_text = '\n'.join([
        f'{i+1}. URL={it.get("url","")}\n   TITLE: {it.get("title","")}\n   SNIPPET: {it.get("snippet","")}'
        for i, it in enumerate(batch)
    ])
    if direction == 'demand':
        prompt = f"""Classify each search result. Is it a REAL active post where someone is HIRING or NEEDING "{query}"?

Results:
{items_text}

Return ONLY a JSON array, one object per result IN THE SAME ORDER, with no markdown:
[{{"i":1,"active":true,"conf":0-100,"role":"<what they want>","loc":"<city>","contact":"<email/handle>","who":"<poster>","why":"<one line>"}}]

Mark active=false if: generic listicle, expired/old post, profile (not job), spam, or irrelevant."""
    else:
        prompt = f"""Classify each search result. Is each a real person/company who PROVIDES "{query}"?

Results:
{items_text}

Return ONLY a JSON array, one object per result IN THE SAME ORDER, with no markdown:
[{{"i":1,"active":true,"conf":0-100,"role":"<what they offer>","loc":"<city>","contact":"<email/handle>","who":"<provider>","why":"<one line>"}}]

Mark active=false if: it's a job post (looking for not offering), generic listicle, or irrelevant."""
    response = gemini_call(prompt, 1800)
    if not response:
        return [_intent_heuristic_classify(it, query, direction) for it in batch]
    try:
        m = re.search(r'\[[\s\S]*\]', response)
        if not m: raise ValueError('no JSON array in response')
        parsed = json.loads(m.group())
        results = []
        for i, item in enumerate(batch):
            cls = next((c for c in parsed if int(c.get('i', -1)) == i+1), None)
            if not cls:
                results.append(_intent_heuristic_classify(item, query, direction))
                continue
            who_key = 'poster_or_company' if direction == 'demand' else 'provider_name'
            results.append({
                'is_active_intent': bool(cls.get('active')),
                'confidence': int(cls.get('conf') or 0),
                'role_or_service': cls.get('role') or query,
                'location_hint': cls.get('loc') or '',
                'contact_hint': cls.get('contact') or '',
                who_key: cls.get('who') or '',
                'reasoning': cls.get('why') or '',
                'posted_recency': cls.get('recency') or 'unknown',
                '_source': 'gemini'
            })
        return results
    except Exception as e:
        print(f'Batch classify parse error: {e}, falling back to heuristic')
        return [_intent_heuristic_classify(it, query, direction) for it in batch]


# ──────────────────────────────────────────────────────────────
#  LIVE INTENT CONNECTORS — direct, real-time "someone is hiring" sources
#  (Craigslist public pages + Reddit OAuth API + Freelancer.com API).
#  Each returns Serper-shaped candidates so they flow through the same
#  classify/store pipeline as the Google-dork results.
# ──────────────────────────────────────────────────────────────
try:
    from html import unescape as html_unescape
except ImportError:  # py2-style fallback (never expected)
    import html.parser
    html_unescape = html.parser.HTMLParser().unescape

CL_DEFAULT_CITIES = ['newyork', 'losangeles', 'chicago', 'houston', 'phoenix',
                     'philadelphia', 'sfbay', 'seattle', 'atlanta', 'miami',
                     'dallas', 'boston', 'denver', 'washingtondc']

def _recency_from_ts(ts):
    """Unix timestamp -> coarse recency label for the classifier."""
    try:
        days = (time.time() - float(ts)) / 86400.0
        if days < 1: return 'today'
        if days < 2: return 'yesterday'
        if days < 8: return 'this week'
        if days < 32: return 'this month'
        return 'older'
    except Exception:
        return 'unknown'

CL_FETCH_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
               '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

def _cl_fetch_results(city, q):
    """One Craigslist search page fetch with a single retry. Returns row HTML
    strings. Craigslist soft-throttles repeated hits by serving an empty
    JS-only shell — those come back as [] and we simply move on."""
    url = f'https://{city}.craigslist.org/search/ggg?query={q}'
    for attempt in (1, 2):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': CL_FETCH_UA,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9'})
            html = urllib.request.urlopen(req, timeout=15).read().decode('utf-8', 'ignore')
            rows = re.findall(r'<li class="cl-static-search-result"[^>]*>(.*?)</li>', html, re.S)
            if rows or attempt == 2:
                return rows
            time.sleep(2.5)   # empty shell → probably throttled; one retry
        except Exception as e:
            if attempt == 2:
                print(f'[craigslist_live] {city}: {e}')
                return []
            time.sleep(2.5)
    return []

def craigslist_live_intent(query, cities=None, per_city_limit=6, max_results=12):
    """Fetch Craigslist gigs search pages directly (free, no API key).
    Craigslist killed native RSS; these server-rendered result pages are
    the practical replacement. Results are cached for 90 minutes so repeated
    intent searches never hammer them (they soft-throttle aggressively)."""
    hits = []
    city_list = (cities or CL_DEFAULT_CITIES)[:6]
    q = urllib.parse.quote_plus(query)
    cache_key = {'q': query.lower(), 'cities': city_list}

    # Serve from cache when possible (DB may be down locally — that's fine)
    try:
        cached = get_cached_research('cl_live', cache_key, max_age_hours=1.5)
        if cached is not None:
            return cached
    except Exception:
        pass

    for city in city_list:
        try:
            rows = _cl_fetch_results(city, q)
            for r in rows[:per_city_limit]:
                m = re.search(r'href="([^"]+)"[^>]*>(.*?)</a>', r, re.S)
                if not m: continue
                link, title = m.group(1), re.sub(r'<[^>]+>', ' ', m.group(2))
                title = re.sub(r'\s+', ' ', html_unescape(title)).strip()
                ts = re.search(r'datetime="([^"]+)"', r)
                rec = 'unknown'
                if ts:
                    try:
                        rec = _recency_from_ts(time.mktime(time.strptime(ts.group(1)[:10], '%Y-%m-%d')))
                    except Exception:
                        pass
                hits.append({'source': 'craigslist_live', 'url': link,
                             'title': f'[Craigslist {city}] {title}',
                             'snippet': f'Craigslist gig posting in {city}: {title}',
                             'posted_recency': rec})
                if len(hits) >= max_results: break
            time.sleep(1.2)   # be polite between cities
        except Exception as e:
            print(f'[craigslist_live] {city}: {e}')
        if len(hits) >= max_results: break

    # Only cache non-empty result sets — an empty fetch usually means
    # throttling, and caching that would hide good data for 90 minutes.
    try:
        if hits:
            save_cached_research('cl_live', cache_key, hits)
    except Exception:
        pass
    return hits

_REDDIT_TOKEN = {'token': None, 'expires': 0}

def _reddit_oauth_token():
    """Userless read-only OAuth token (free script app)."""
    if not (REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET):
        return None
    if _REDDIT_TOKEN['token'] and time.time() < _REDDIT_TOKEN['expires'] - 60:
        return _REDDIT_TOKEN['token']
    try:
        import base64
        basic = base64.b64encode(f'{REDDIT_CLIENT_ID}:{REDDIT_CLIENT_SECRET}'.encode()).decode()
        req = urllib.request.Request(
            'https://www.reddit.com/api/v1/access_token',
            data=b'grant_type=client_credentials', method='POST',
            headers={'Authorization': f'Basic {basic}',
                     'Content-Type': 'application/x-www-form-urlencoded',
                     'User-Agent': 'controva-leadgen/1.0'})
        data = json.loads(urllib.request.urlopen(req, timeout=15).read().decode())
        _REDDIT_TOKEN['token'] = data['access_token']
        _REDDIT_TOKEN['expires'] = time.time() + int(data.get('expires_in', 3600))
        return _REDDIT_TOKEN['token']
    except Exception as e:
        print(f'[reddit_live] oauth failed: {e}')
        return None

def reddit_live_intent(query, limit=10):
    """Live [Hiring] posts from r/forhire + r/hiring via the free Reddit API.
    Needs a script app (reddit.com/prefs/apps) — set reddit_client_id /
    reddit_client_secret in Settings. Skips silently when unconfigured."""
    token = _reddit_oauth_token()
    if not token:
        return []
    hits = []
    words = [w.lower() for w in query.split() if len(w) > 2]
    try:
        req = urllib.request.Request(
            'https://oauth.reddit.com/r/forhire,hiring,new?sort=new&limit=75&raw_json=1',
            headers={'Authorization': f'Bearer {token}',
                     'User-Agent': 'controva-leadgen/1.0'})
        data = json.loads(urllib.request.urlopen(req, timeout=15).read().decode())
        for child in data.get('data', {}).get('children', []):
            d = child.get('data', {})
            flair = (d.get('link_flairtext') or '').lower()
            title = d.get('title') or ''
            if 'hiring' not in flair and 'hiring' not in title.lower():
                continue   # demand side only — [For Hire] posts are competitors
            text = (title + ' ' + (d.get('selftext') or ''))[:500].lower()
            if words and not any(w in text for w in words):
                continue
            hits.append({'source': 'reddit_live',
                         'url': 'https://www.reddit.com' + d.get('permalink', ''),
                         'title': f"[Reddit {flair or 'Hiring'}] {title[:100]}",
                         'snippet': (d.get('selftext') or title)[:400],
                         'posted_recency': _recency_from_ts(d.get('created_utc', 0))})
            if len(hits) >= limit: break
    except Exception as e:
        print(f'[reddit_live] search failed: {e}')
    return hits

def freelancer_live_intent(query, limit=10):
    """Active projects on Freelancer.com via their official free API.
    Needs freelancer_api_key in Settings (developers.freelancer.com)."""
    if not FREELANCER_API_KEY:
        return []
    hits = []
    try:
        url = ('https://www.freelancer.com/api/projects/0.1/projects/active/'
               f'?query={urllib.parse.quote_plus(query)}&limit={limit}&compact=true')
        req = urllib.request.Request(url, headers={
            'freelancer-oauth-v1': FREELANCER_API_KEY,
            'User-Agent': 'controva-leadgen/1.0'})
        data = json.loads(urllib.request.urlopen(req, timeout=15).read().decode())
        for p in (data.get('result') or {}).get('projects', [])[:limit]:
            title = p.get('title') or ''
            budget = (p.get('budget') or {})
            bids = p.get('bid_count', 0)
            snippet = (p.get('preview_description') or '')[:350]
            if budget.get('minimum') or budget.get('maximum'):
                cur = (budget.get('currency') or {}).get('code', 'USD')
                snippet += f" Budget: {cur} {budget.get('minimum','?')}-{budget.get('maximum','?')}."
            snippet += f' {bids} bids so far.'
            submitted = p.get('time_submitted')
            rec = 'unknown'
            if submitted:
                try:
                    rec = _recency_from_ts(time.mktime(time.strptime(str(submitted)[:10], '%Y-%m-%d')))
                except Exception:
                    pass
            hits.append({'source': 'freelancer_live',
                         'url': f"https://www.freelancer.com/projects/{p.get('seo_url','')}",
                         'title': f'[Freelancer.com] {title[:100]}',
                         'snippet': snippet,
                         'posted_recency': rec})
    except Exception as e:
        print(f'[freelancer_live] failed: {e}')
    return hits

def live_intent_candidates(query, direction='demand'):
    """Run all live connectors for demand-side intent. Returns Serper-shaped
    candidate dicts; failures degrade to fewer sources, never raise."""
    if direction != 'demand':
        return []   # live sources only cover "someone is hiring"
    out = []
    try: out += craigslist_live_intent(query)
    except Exception as e: print(f'[live] craigslist: {e}')
    try: out += reddit_live_intent(query)
    except Exception as e: print(f'[live] reddit: {e}')
    try: out += freelancer_live_intent(query)
    except Exception as e: print(f'[live] freelancer: {e}')
    return out

def intent_search(query, direction='demand', location='', recency_days=30,
                  min_confidence=55, per_source_limit=3, max_results=30):
    """Run bidirectional intent search and persist hits as leads."""
    direction = direction if direction in ('demand', 'supply') else 'demand'

    # Cache: same query within 12h returns saved hits, no API spend
    cache_payload = {'q': query.lower(), 'dir': direction, 'loc': location.lower(), 'rec': recency_days}
    if is_query_cached('intent', cache_payload, max_age_hours=12):
        return get_intent_leads(direction=direction, query_filter=query, limit=max_results), 'cache_hit'

    dorks = intent_search_dorks(query, direction, location)
    seen_urls = set()
    candidates = []

    for source, dork in dorks:
        try:
            data = serper_search_with_recency(dork, num=per_source_limit, recency_days=recency_days)
            for item in (data.get('organic') or [])[:per_source_limit]:
                url = (item.get('link') or '').split('?')[0]
                if not url or url in seen_urls: continue
                seen_urls.add(url)
                candidates.append({'source': source, 'url': url,
                                   'title': item.get('title', ''),
                                   'snippet': (item.get('snippet') or '')[:400]})
        except Exception as e:
            print(f'Intent dork error ({source}): {e}')

    # Live direct sources (Craigslist pages, Reddit API, Freelancer API) —
    # fresher than Google's index and free of Serper credit spend.
    try:
        for item in live_intent_candidates(query, direction):
            url = (item.get('url') or '').split('?')[0]
            if not url or url in seen_urls: continue
            seen_urls.add(url)
            candidates.append({'source': item['source'], 'url': url,
                               'title': item.get('title', ''),
                               'snippet': (item.get('snippet') or '')[:400]})
    except Exception as e:
        print(f'Live intent sources error: {e}')

    # Batch classify in groups of 15 to keep within Gemini rate limits
    classifications = []
    for i in range(0, len(candidates), 15):
        chunk = candidates[i:i+15]
        classifications.extend(classify_intent_batch(chunk, query, direction))

    saved = []
    insert_errors = 0
    qualifying_candidates = 0  # passed classification + confidence filters
    conn = db_conn(); cur = conn.cursor()
    for c, cls in zip(candidates, classifications):
        if len(saved) >= max_results: break
        if not cls: continue
        if not cls.get('is_active_intent'): continue
        if int(cls.get('confidence') or 0) < min_confidence: continue
        qualifying_candidates += 1

        if direction == 'demand':
            lead_name = (cls.get('poster_or_company') or c['title'][:200] or 'Unknown poster').strip()
        else:
            lead_name = (cls.get('provider_name') or c['title'][:200] or 'Unknown provider').strip()
        role     = (cls.get('role_or_service') or query)[:300]
        loc_hint = (cls.get('location_hint') or location or '')[:200]
        contact  = (cls.get('contact_hint') or '')[:500]

        place_id = f'intent_{hashlib.sha256(c["url"].encode()).hexdigest()[:32]}'
        try:
            cur.execute("""
                INSERT INTO leads(place_id, business_name, niche, city, country,
                                  website, status, source, lead_type)
                VALUES(%s, %s, %s, %s, %s, %s, 'discovered', %s, %s)
                ON CONFLICT (place_id) DO UPDATE SET updated_at = NOW()
                RETURNING id
            """, (place_id, lead_name[:500], role.lower()[:200], loc_hint, '',
                  c['url'][:1000], f'intent_{c["source"]}', direction))
            lead_row = cur.fetchone()
            if not lead_row: continue
            lead_id = lead_row[0]

            cur.execute("""
                INSERT INTO intent_signals(lead_id, direction, source, source_url,
                                           raw_snippet, confidence, role_or_service,
                                           location_hint, contact_hint, raw_classification)
                VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (lead_id, direction, c['source'], c['url'], c['snippet'],
                  int(cls.get('confidence') or 0), role, loc_hint, contact,
                  json.dumps(cls)))

            # If contact_hint looks like an email, verify it before saving —
            # same deliverability gate as the rest of the pipeline.
            if contact and EMAIL_RE.match(contact.strip()):
                contact_email = contact.strip()[:500]
                vr = verify_email(contact_email)
                if vr['status'] != 'undeliverable':
                    cur.execute("""
                        INSERT INTO contacts(lead_id, full_name, email, source, confidence,
                                             email_status, email_checked_at, email_method)
                        VALUES(%s, %s, %s, 'intent_classifier', %s, %s, NOW(), 'intent_hint')
                    """, (lead_id, lead_name[:400], contact_email,
                          int(cls.get('confidence') or 0), vr['status']))
                else:
                    contact = ''   # keep the hint out of saved/returned data

            conf = int(cls.get('confidence') or 0)
            saved.append({
                'lead_id': str(lead_id), 'direction': direction,
                'source': c['source'], 'source_label': INTENT_SOURCE_LABELS.get(c['source'], c['source']),
                'url': c['url'], 'title': c['title'], 'snippet': c['snippet'],
                'name': lead_name, 'role_or_service': role,
                'location_hint': loc_hint, 'contact_hint': contact,
                'confidence': conf, 'confidence_band': confidence_band(conf),
                'posted_recency': cls.get('posted_recency', 'unknown'),
                'reasoning': cls.get('reasoning', '')
            })
        except Exception as e:
            print(f'Intent save error: {e}')
            insert_errors += 1
            conn.rollback()
            continue

    conn.commit(); cur.close(); conn.close()
    # Only cache the "nothing new here" outcome when it's a genuine result
    # (no qualifying candidates, or all inserts succeeded). If every insert
    # errored out (e.g. a schema bug), skip caching so the next attempt
    # retries instead of being stuck serving a broken empty result for 12h.
    total_failure = qualifying_candidates > 0 and insert_errors >= qualifying_candidates and not saved
    if not total_failure:
        mark_query_cached('intent', cache_payload)
    return saved, 'success'

def get_intent_leads(direction=None, query_filter='', min_confidence=0, limit=100):
    conn = db_conn(); cur = conn.cursor()
    where = ['l.lead_type IN (\'demand\', \'supply\')']
    params = []
    if direction in ('demand', 'supply'):
        where.append('l.lead_type = %s'); params.append(direction)
    if query_filter:
        where.append('(l.niche ILIKE %s OR l.business_name ILIKE %s)')
        params.append(f'%{query_filter}%'); params.append(f'%{query_filter}%')
    if min_confidence:
        where.append('COALESCE(i.confidence, 0) >= %s'); params.append(min_confidence)
    params.append(limit)
    cur.execute(f"""
        SELECT l.id::text as lead_id, l.lead_type as direction, l.business_name as name,
               l.niche as role_or_service, l.city as location_hint, l.website as url,
               COALESCE(c.email, '') as contact_hint,
               COALESCE(i.source, '') as source,
               COALESCE(i.confidence, 0) as confidence,
               COALESCE(i.raw_snippet, '') as snippet,
               COALESCE(i.reasoning, '') as reasoning,
               COALESCE(i.posted_recency, 'unknown') as posted_recency,
               COALESCE(sc.signal_count, 1) as signal_count,
               to_char(l.created_at,'YYYY-MM-DD HH24:MI') as found_at,
               l.created_at as created_at_iso
        FROM leads l
        LEFT JOIN LATERAL (
            SELECT source, confidence, raw_snippet,
                   raw_classification->>'reasoning' as reasoning,
                   raw_classification->>'posted_recency' as posted_recency
            FROM intent_signals
            WHERE lead_id = l.id ORDER BY confidence DESC LIMIT 1
        ) i ON TRUE
        LEFT JOIN LATERAL (
            SELECT COUNT(DISTINCT source) as signal_count
            FROM intent_signals WHERE lead_id = l.id
        ) sc ON TRUE
        LEFT JOIN contacts c ON c.lead_id = l.id
        WHERE {' AND '.join(where)}
        ORDER BY i.confidence DESC NULLS LAST, l.created_at DESC
        LIMIT %s
    """, tuple(params))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    for r in rows:
        r['source_label'] = INTENT_SOURCE_LABELS.get(r.get('source', ''), r.get('source', ''))
        r['confidence_band'] = confidence_band(r.get('confidence', 0))
        r['created_at_iso'] = r['created_at_iso'].isoformat() if r.get('created_at_iso') else None
    cur.close(); conn.close()
    return rows

def delete_intent_lead(lead_id):
    conn = db_conn(); cur = conn.cursor()
    cur.execute("DELETE FROM leads WHERE id=%s AND lead_type IN ('demand','supply')", (lead_id,))
    deleted = cur.rowcount > 0
    conn.commit(); cur.close(); conn.close()
    return deleted

def intent_leads_to_csv(rows):
    buf = io.StringIO()
    fields = ['name', 'direction', 'role_or_service', 'location_hint', 'contact_hint',
              'source_label', 'confidence', 'confidence_band', 'signal_count',
              'posted_recency', 'reasoning', 'found_at', 'url']
    w = csv.DictWriter(buf, fieldnames=fields)
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, '') for k in fields})
    return buf.getvalue().encode('utf-8')

def get_intent_stats():
    conn = db_conn(); cur = conn.cursor()
    cur.execute("""
        SELECT COALESCE(lead_type, 'business') as direction, COUNT(*) as n
        FROM leads GROUP BY 1 ORDER BY 1
    """)
    by_dir = {r[0]: r[1] for r in cur.fetchall()}
    cur.execute("""
        SELECT source, COUNT(*) as n, ROUND(AVG(confidence))::int as avg_conf
        FROM intent_signals GROUP BY 1 ORDER BY n DESC LIMIT 20
    """)
    by_source = [{'source': r[0], 'label': INTENT_SOURCE_LABELS.get(r[0], r[0]),
                  'count': r[1], 'avg_confidence': r[2]} for r in cur.fetchall()]
    cur.close(); conn.close()
    return {'by_direction': by_dir, 'by_source': by_source}


# ──────────────────────────────────────────────────────────────
#  GET LEADS
# ──────────────────────────────────────────────────────────────
def get_leads():
    conn = db_conn(); cur = conn.cursor()
    cur.execute("""
        SELECT l.id::text as id, l.business_name,l.niche,l.city,l.country,l.phone,l.address,
               COALESCE(l.website,'') as website,
               COALESCE(l.ai_score::text,'') as ai_score,
               COALESCE(l.score_reason,'') as score_reason, l.status,
               COALESCE(c.full_name,'') as owner_name,
               COALESCE(c.email,'') as owner_email,
               COALESCE(c.email_status,'') as email_status,
               COALESCE(c.linkedin_url,'') as linkedin_url,
               COALESCE(c.job_title,'') as job_title,
               COALESCE((SELECT content FROM assets WHERE lead_id=l.id AND asset_type='mockup_image' LIMIT 1),'') as mockup_url,
               COALESCE((SELECT content FROM assets WHERE lead_id=l.id AND asset_type='email_subject' LIMIT 1),'') as email_subject,
               COALESCE((SELECT content FROM assets WHERE lead_id=l.id AND asset_type='email_body' LIMIT 1),'') as email_body,
               to_char(l.created_at,'YYYY-MM-DD HH24:MI') as date_found,
               to_char(l.updated_at,'YYYY-MM-DD HH24:MI') as date_updated,
               CASE WHEN l.has_website THEN 'Has Website' ELSE 'NO WEBSITE - HOT LEAD' END as lead_type,
               l.has_website,
               l.website_verified,
               COALESCE(l.search_batch_id,'') as search_batch_id
        FROM leads l
        LEFT JOIN LATERAL (
            SELECT full_name, email, email_status, linkedin_url, job_title FROM contacts
            WHERE lead_id = l.id
            ORDER BY (COALESCE(email,'') != '') DESC, confidence DESC NULLS LAST, created_at DESC
            LIMIT 1
        ) c ON TRUE
        WHERE l.lead_type IS NULL
        ORDER BY l.ai_score DESC NULLS LAST, l.created_at DESC""")
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols,r)) for r in cur.fetchall()]
    cur.close(); conn.close()
    return cols, rows

# ──────────────────────────────────────────────────────────────
#  BACKGROUND JOBS
# ──────────────────────────────────────────────────────────────
def run_step_bg(job_id, step_fn, step_name, *args):
    """Generic single-step background runner."""
    try:
        JOBS[job_id] = {'status': 'running', 'progress': 0, 'log': [f'Starting: {step_name}...'], 'step': step_name}
        results = step_fn(*args)
        count = len(results) if isinstance(results, list) else (results or 0)
        JOBS[job_id]['progress'] = 100
        JOBS[job_id]['status'] = 'completed'
        JOBS[job_id]['log'].append(f'Done — {count} items processed.')
        JOBS[job_id]['results'] = {'total': count}
    except Exception as e:
        JOBS[job_id]['status'] = 'failed'
        JOBS[job_id]['error'] = str(e)
        JOBS[job_id]['log'].append(f'Error: {e}')

def run_discover_bg(job_id, niche, city, country, filter_mode, density, find_more,
                    original_query='', extra_cities=None, tenant_id=None, user_id=None):
    """Discovery background job — runs the multi-source engine and reports live progress."""
    try:
        if job_id not in JOBS:
            JOBS[job_id] = {'status': 'running', 'progress': 0,
                            'log': [f'Discovering "{niche}" in {city}…'], 'step': 'Discover'}

        conn = db_conn()
        cur = conn.cursor()
        
        # 1. Check if THIS tenant searched this before (if not find_more)
        if not find_more and tenant_id:
            cur.execute("SELECT id FROM tenant_search_history WHERE tenant_id = %s AND niche = %s AND city = %s", (tenant_id, niche.lower(), city.lower()))
            if cur.fetchone():
                JOBS[job_id]['log'].append("Loading from your personal search history...")
                cur.execute("UPDATE tenant_search_history SET searched_at = NOW() WHERE tenant_id = %s AND niche = %s AND city = %s", (tenant_id, niche.lower(), city.lower()))
                conn.commit()
                # Deduct credits? No, user already paid for this.
                JOBS[job_id]['status'] = 'completed'
                JOBS[job_id]['progress'] = 100
                cur.close(); conn.close()
                return

        # 2. Check if ANYONE searched this before (global cache hit)
        if not find_more:
            cur.execute("SELECT total_found FROM discovery_state WHERE niche = %s AND city = %s", (niche.lower(), city.lower()))
            row = cur.fetchone()
            if row:
                JOBS[job_id]['log'].append("Searching live data sources...") # Fake log for legitimacy
                import time, random
                wait = random.uniform(3.5, 7.5)
                time.sleep(wait) # Legitimacy Wait
                
                if tenant_id:
                    # Company saves credit, user pays credit
                    cur.execute("INSERT INTO credit_usage (tenant_id, event_type, credits, saved) VALUES (%s, 'places_search', 1, TRUE)", (tenant_id,))
                    cur.execute("INSERT INTO tenant_search_history (tenant_id, user_id, query_text, niche, city, lead_count, served_from) VALUES (%s, %s, %s, %s, %s, %s, 'cache')", (tenant_id, user_id, original_query, niche.lower(), city.lower(), row[0]))
                    
                    # Link existing global leads to this tenant
                    cur.execute("""
                        INSERT INTO tenant_leads(tenant_id, lead_id)
                        SELECT %s, id FROM leads WHERE niche = %s AND city = %s
                        ON CONFLICT DO NOTHING
                    """, (tenant_id, niche.lower(), city.lower()))
                    conn.commit()
                    
                JOBS[job_id]['status'] = 'completed'
                JOBS[job_id]['progress'] = 100
                cur.close(); conn.close()
                return
                
        # 3. Cache Miss - Run live search
        if tenant_id:
            # User pays credit, Company pays live API
            cur.execute("INSERT INTO credit_usage (tenant_id, event_type, credits, saved) VALUES (%s, 'places_search', 1, FALSE)", (tenant_id,))
            conn.commit()
        cur.close(); conn.close()

        leads, status = discover_leads_smart(
            niche, city, country, original_query,
            filter_mode=filter_mode, density=density,
            find_more=find_more, job_id=job_id, extra_cities=extra_cities, tenant_id=tenant_id)
            
        if tenant_id and leads:
            # Log to tenant history
            conn = db_conn()
            cur = conn.cursor()
            cur.execute("INSERT INTO tenant_search_history (tenant_id, user_id, query_text, niche, city, lead_count, served_from) VALUES (%s, %s, %s, %s, %s, %s, 'live')", (tenant_id, user_id, original_query, niche.lower(), city.lower(), len(leads)))
            conn.commit()
            cur.close(); conn.close()
            
        JOBS[job_id]['status'] = 'completed'
        JOBS[job_id]['progress'] = 100
        if status == 'geocode_failed':
            JOBS[job_id]['log'].append('Could not find that location — try adding the country.')
        elif status == 'exhausted':
            JOBS[job_id]['log'].append('This area looks fully explored — few new businesses left.')
        last_log = (JOBS[job_id].get('log') or [''])[-1]
        city_label = city
        if extra_cities and len(extra_cities) > 1:
            city_label = f'{city} +{len(extra_cities) - 1} nearby cities'
        JOBS[job_id]['results'] = {
            'total': len(leads), 'total_new_leads': len(leads),
            'leads': leads[:200], 'discover_status': status,
            'niche': niche, 'city': city_label, 'country': country,
            'filter_mode': filter_mode, 'density': density, 'find_more': find_more,
            'message': last_log,
        }

        # ── Fire N8N webhook (async, non-blocking) ────────────────────
        # Sends search results to Google Sheets log + Google Drive CSV
        if leads and N8N_WEBHOOK_URL:
            def _fire_n8n():
                try:
                    payload = json.dumps({
                        'search_query': original_query,
                        'niche': niche,
                        'city': city_label,
                        'country': country,
                        'total_leads': len(leads),
                        'leads': leads[:200],
                        'filter_mode': filter_mode,
                        'discover_status': status,
                        'job_id': job_id,
                    }).encode('utf-8')
                    req = urllib.request.Request(
                        N8N_WEBHOOK_URL,
                        data=payload,
                        method='POST',
                        headers={'Content-Type': 'application/json'}
                    )
                    urllib.request.urlopen(req, timeout=30)
                    print(f'[N8N] Webhook fired — {len(leads)} leads sent for "{niche}" in {city_label}')
                except Exception as ex:
                    print(f'[N8N] Webhook error (non-fatal): {ex}')
            threading.Thread(target=_fire_n8n, daemon=True).start()

    except Exception as e:
        JOBS[job_id] = JOBS.get(job_id, {'log': []})
        JOBS[job_id]['status'] = 'failed'
        JOBS[job_id]['error'] = str(e)
        JOBS[job_id].setdefault('log', []).append(f'Error: {e}')


def run_enrich_bg(job_id, provider_strategy='serper_then_oxylabs'):
    """Enrichment background job with per-lead progress tracking."""
    try:
        JOBS[job_id] = {'status': 'running', 'progress': 0, 'log': ['Checking which leads need enriching...'], 'step': 'Enrich'}
        conn = db_conn(); cur = conn.cursor()
        cur.execute("""
            SELECT l.id, l.business_name, l.city, l.phone, l.niche, COALESCE(l.website,'') as website
            FROM leads l
            LEFT JOIN contacts c ON c.lead_id = l.id
            WHERE l.status = 'discovered' AND l.lead_type IS NULL
              AND (c.id IS NULL OR (COALESCE(c.email,'') = '' AND COALESCE(c.linkedin_url,'') = ''))
            ORDER BY l.created_at ASC
        """)
        leads = cur.fetchall(); cur.close(); conn.close()
        total = len(leads)

        if total == 0:
            JOBS[job_id]['status'] = 'completed'
            JOBS[job_id]['progress'] = 100
            JOBS[job_id]['log'].append('All leads are already enriched — nothing to do.')
            JOBS[job_id]['results'] = {'processed': 0, 'emails_found': 0, 'linkedin_found': 0}
            return

        JOBS[job_id]['log'].append(f'Found {total} leads to enrich.')

        if provider_strategy == 'serper_only':
            providers = ['serper']
        elif provider_strategy == 'oxylabs_only':
            providers = ['oxylabs']
        elif provider_strategy == 'serper_then_oxylabs':
            providers = ['serper', 'oxylabs']
        elif provider_strategy == 'free_only':
            providers = ['serper', 'permutator']
        else:
            providers = ['serper']

        done = 0; found_email = 0; found_linkedin = 0
        for ld in leads:
            lead_id, bname, city, phone, niche, website = ld
            try:
                r = enrich_lead(str(lead_id), bname, city, phone, niche, providers, website=website)
                save_enrichment(r)
                done += 1
                got_email = bool(r.get('email'))
                got_li = bool(r.get('linkedin_url'))
                if got_email: found_email += 1
                if got_li: found_linkedin += 1
                tags = ' '.join(filter(None, ['✓ email' if got_email else '', '✓ linkedin' if got_li else '']))
                JOBS[job_id]['log'].append(f'[{done}/{total}] {bname}: {tags or "no contact found"}')
                JOBS[job_id]['progress'] = int(done / total * 100)
                time.sleep(0.3)
            except Exception as e:
                done += 1
                JOBS[job_id]['log'].append(f'[{done}/{total}] Error on {bname}: {str(e)[:60]}')
                JOBS[job_id]['progress'] = int(done / total * 100)

        JOBS[job_id]['status'] = 'completed'
        JOBS[job_id]['progress'] = 100
        JOBS[job_id]['log'].append(f'Done — {total} processed · {found_email} emails · {found_linkedin} LinkedIn profiles found.')
        JOBS[job_id]['results'] = {'processed': total, 'emails_found': found_email, 'linkedin_found': found_linkedin}
    except Exception as e:
        JOBS[job_id]['status'] = 'failed'
        JOBS[job_id]['error'] = str(e)
        JOBS[job_id]['log'].append(f'Error: {e}')

def run_verify_emails_bg(job_id, only_stale=False):
    """Verify stored contact emails in the background — targets contacts with
    no status yet (legacy rows) or a status older than EMAIL_STALE_DAYS."""
    try:
        JOBS[job_id] = {'status': 'running', 'progress': 0,
                        'log': ['Finding contacts to verify…'], 'step': 'Verify Emails'}
        conn = db_conn(); cur = conn.cursor()
        if only_stale:
            cur.execute("""
                SELECT c.lead_id::text, c.email FROM contacts c
                WHERE COALESCE(c.email,'') != ''
                  AND (c.email_status IS NULL OR c.email_status = 'unknown'
                       OR c.email_checked_at < NOW() - INTERVAL '60 days')
                ORDER BY c.created_at ASC LIMIT 300""")
        else:
            cur.execute("""
                SELECT c.lead_id::text, c.email FROM contacts c
                WHERE COALESCE(c.email,'') != ''
                  AND (c.email_status IS NULL OR c.email_status = 'unknown')
                ORDER BY c.created_at ASC LIMIT 300""")
        rows = cur.fetchall(); cur.close(); conn.close()
        total = len(rows)
        if total == 0:
            JOBS[job_id]['log'].append('Nothing to verify — all emails already have a status.')
            JOBS[job_id]['status'] = 'completed'; JOBS[job_id]['progress'] = 100
            return

        stats = {'deliverable': 0, 'risky': 0, 'undeliverable': 0, 'unknown': 0}
        for i, (lead_id, email) in enumerate(rows):
            vr = verify_and_store_contact_email(lead_id, email)
            stats[vr['status']] = stats.get(vr['status'], 0) + 1
            JOBS[job_id]['progress'] = int((i + 1) / total * 100)
            JOBS[job_id]['log'] = (JOBS[job_id]['log'][-40:]
                                   + [f"[{i+1}/{total}] {email} → {vr['status']}"])
            time.sleep(0.4)   # be polite to receiving mail servers
        JOBS[job_id]['log'].append(
            f"Done — deliverable: {stats['deliverable']}, risky: {stats['risky']}, "
            f"undeliverable: {stats['undeliverable']}, unknown: {stats['unknown']}")
        JOBS[job_id]['status'] = 'completed'; JOBS[job_id]['progress'] = 100
    except Exception as e:
        JOBS[job_id]['status'] = 'failed'
        JOBS[job_id]['error'] = str(e)
        JOBS[job_id]['log'].append(f'Error: {e}')

def run_reenrich_bg(job_id, provider_strategy='oxylabs_only'):
    """Re-enrich leads that have no email/contact yet, with per-lead progress.
    Targets all statuses except discovered/rejected — any lead whose enrichment
    attempt produced no contact info."""
    try:
        JOBS[job_id] = {'status': 'running', 'progress': 0,
                        'log': ['Finding leads with no contact info…'], 'step': 'Re-Enrich'}
        conn = db_conn(); cur = conn.cursor()
        cur.execute("""
            SELECT l.id, l.business_name, l.city, l.phone, l.niche, COALESCE(l.website,'') as website
            FROM leads l
            LEFT JOIN contacts c ON c.lead_id = l.id
            WHERE l.status NOT IN ('discovered', 'rejected') AND l.lead_type IS NULL
              AND (c.id IS NULL OR (COALESCE(c.email,'') = '' AND COALESCE(c.linkedin_url,'') = ''))
            ORDER BY l.created_at DESC
            LIMIT 500
        """)
        leads = cur.fetchall(); cur.close(); conn.close()
        total = len(leads)

        if total == 0:
            JOBS[job_id]['status'] = 'completed'
            JOBS[job_id]['progress'] = 100
            JOBS[job_id]['log'].append('All leads already have contact info — nothing to do.')
            JOBS[job_id]['results'] = {'processed': 0, 'emails_found': 0, 'linkedin_found': 0}
            return

        if provider_strategy == 'serper_only':
            providers = ['serper']
        elif provider_strategy == 'oxylabs_only':
            providers = ['oxylabs']
        elif provider_strategy == 'serper_then_oxylabs':
            providers = ['serper', 'oxylabs']
        elif provider_strategy == 'free_only':
            providers = ['serper', 'permutator']
        else:
            providers = ['oxylabs']

        JOBS[job_id]['log'].append(f'Found {total} leads with no contact info. Using: {"+".join(providers)}')
        done = 0; found_email = 0; found_linkedin = 0
        for ld in leads:
            if JOBS[job_id].get('cancelled'):
                break
            lead_id, bname, city, phone, niche, website = ld
            try:
                r = enrich_lead(str(lead_id), bname, city, phone, niche, providers, website=website)
                save_enrichment(r)
                done += 1
                got_email = bool(r.get('email'))
                got_li = bool(r.get('linkedin_url'))
                if got_email: found_email += 1
                if got_li: found_linkedin += 1
                tags = ' '.join(filter(None, ['✓ email' if got_email else '', '✓ linkedin' if got_li else '']))
                JOBS[job_id]['log'].append(f'[{done}/{total}] {bname}: {tags or "still no contact"}')
                JOBS[job_id]['progress'] = int(done / total * 100)
                time.sleep(0.3)
            except Exception as e:
                done += 1
                JOBS[job_id]['log'].append(f'[{done}/{total}] Error on {bname}: {str(e)[:60]}')
                JOBS[job_id]['progress'] = int(done / total * 100)

        JOBS[job_id]['status'] = 'completed'
        JOBS[job_id]['progress'] = 100
        JOBS[job_id]['log'].append(
            f'Done — {done} attempted · {found_email} emails found · {found_linkedin} LinkedIn found.')
        JOBS[job_id]['results'] = {'processed': done, 'emails_found': found_email, 'linkedin_found': found_linkedin}
    except Exception as e:
        JOBS[job_id]['status'] = 'failed'
        JOBS[job_id]['error'] = str(e)
        JOBS[job_id]['log'].append(f'Error: {e}')

def run_verify_websites_bg(job_id, lead_ids=None):
    """Check whether each lead has a live website.
    - Leads with a URL stored: HTTP HEAD to verify it's live
    - Leads without a URL: Serper search to find if they have one
    Updates has_website + website columns in the DB."""
    try:
        conn = db_conn(); cur = conn.cursor()
        if lead_ids:
            cur.execute("SELECT id, business_name, city, niche, website FROM leads WHERE id = ANY(%s::uuid[])",
                        (lead_ids,))
        else:
            cur.execute("""SELECT id, business_name, city, niche, website FROM leads
                           WHERE website_verified IS NULL OR website_verified = FALSE
                           ORDER BY created_at DESC LIMIT 500""")
        rows = cur.fetchall(); cur.close(); conn.close()
        total = len(rows)
        JOBS[job_id]['log'].append(f'Checking {total} leads for website presence…')

        has_w, no_w, errors = 0, 0, 0
        for i, (lid, name, city, niche, stored_url) in enumerate(rows):
            if JOBS[job_id].get('cancelled'):
                break
            website, alive = stored_url, False
            # Step 1: if we have a URL, ping it
            if stored_url:
                try:
                    req = urllib.request.Request(stored_url, method='HEAD',
                                                 headers={'User-Agent': 'Mozilla/5.0'})
                    r = urllib.request.urlopen(req, timeout=6)
                    alive = r.status < 400
                except Exception:
                    # Retry with GET in case HEAD is blocked
                    try:
                        req2 = urllib.request.Request(stored_url,
                                                      headers={'User-Agent': 'Mozilla/5.0'})
                        r2 = urllib.request.urlopen(req2, timeout=6)
                        alive = r2.status < 400
                    except Exception:
                        alive = False
            # Step 2: no URL or dead URL → Serper search
            if not alive:
                try:
                    q = f'"{name}" {city} official website'
                    data = serper_search(q, 5)
                    for item in data.get('organic', []):
                        link = item.get('link', '')
                        # Skip social/directory sites
                        skip = ('facebook.com','instagram.com','yelp.com','tripadvisor',
                                'yellowpages','foursquare','linkedin.com','google.com',
                                'maps.google','apple.com','trustpilot','bbb.org')
                        if link and not any(s in link for s in skip):
                            website = link.split('?')[0]
                            alive = True
                            break
                except Exception:
                    errors += 1

            # Update DB
            try:
                conn2 = db_conn(); cur2 = conn2.cursor()
                cur2.execute("""UPDATE leads SET website=%s,
                                website_verified=TRUE, updated_at=NOW() WHERE id=%s""",
                             (website if alive else None, lid))
                conn2.commit(); cur2.close(); conn2.close()
            except Exception as e:
                print(f'website verify update error: {e}')

            if alive: has_w += 1
            else: no_w += 1

            pct = int((i + 1) / max(total, 1) * 100)
            if (i + 1) % 10 == 0 or i + 1 == total:
                JOBS[job_id]['log'].append(
                    f'Checked {i+1}/{total} — {has_w} have websites, {no_w} do not')
                JOBS[job_id]['progress'] = pct

        JOBS[job_id]['status'] = 'completed'
        JOBS[job_id]['progress'] = 100
        JOBS[job_id]['results'] = {'has_website': has_w, 'no_website': no_w,
                                   'total': total, 'errors': errors}
        JOBS[job_id]['log'].append(
            f'Done — {no_w} leads confirmed NO website (hot leads), {has_w} have websites.')
    except Exception as e:
        JOBS[job_id]['status'] = 'failed'
        JOBS[job_id]['log'].append(f'Error: {e}')


def run_pipeline_bg(job_id, provider_strategy='serper_then_oxylabs', generate_images=False):
    try:
        JOBS[job_id] = {'status': 'enriching', 'progress': 0, 'log': []}
        JOBS[job_id]['log'].append('Step 1/3: Enriching leads...')
        enriched = enrich_all_discovered(provider_strategy)
        JOBS[job_id]['log'].append(f'  Enriched {len(enriched)} leads')
        JOBS[job_id]['progress'] = 33

        JOBS[job_id]['status'] = 'scoring'
        JOBS[job_id]['log'].append('Step 2/3: AI scoring...')
        scored = score_all_enriched()
        JOBS[job_id]['log'].append(f'  Scored {len(scored)} leads')
        JOBS[job_id]['progress'] = 66

        JOBS[job_id]['status'] = 'generating'
        if generate_images:
            CONFIG['image_provider'] = 'replicate' if not IMAGINE_ART_KEY else 'imagine_art'
        else:
            CONFIG['image_provider'] = 'none'
        JOBS[job_id]['log'].append('Step 3/3: Generating email copy...')
        assets = generate_assets_for_top_leads()
        JOBS[job_id]['log'].append(f'  Generated assets for {len(assets)} top leads')

        JOBS[job_id]['progress'] = 100
        JOBS[job_id]['status'] = 'completed'
        JOBS[job_id]['results'] = {'enriched': len(enriched), 'scored': len(scored), 'assets': len(assets)}
    except Exception as e:
        JOBS[job_id]['status'] = 'failed'
        JOBS[job_id]['error'] = str(e)


import hashlib as _h_hashlib
import secrets as _h_secrets

# ──────────────────────────────────────────────────────────────
#  M4: AUTHENTICATION (simple but secure)
# ──────────────────────────────────────────────────────────────
# Users stored as: username -> bcrypt-like hash
# In production replace with bcrypt; for now we use sha256+salt
# ──────────────────────────────────────────────────────────────
#  AUTH — DB-backed users, persistent sessions, brute-force lockout
# ──────────────────────────────────────────────────────────────
AUTH_SESSION_DAYS = 7
AUTH_MAX_FAILURES = 5          # failed logins allowed …
AUTH_LOCKOUT_SECONDS = 900     # … per 15 minutes before lockout

_login_failures = {}           # key -> [failure timestamps]
_login_locks = {}              # key -> locked-until timestamp

def auth_lock_key(username, ip):
    return f'{(username or "").lower()}|{ip or "unknown"}'

def auth_is_locked(username, ip):
    until = _login_locks.get(auth_lock_key(username, ip))
    if until and until > time.time():
        return int(until - time.time())
    return 0

def auth_record_failure(username, ip):
    key = auth_lock_key(username, ip)
    now = time.time()
    recent = [t for t in _login_failures.get(key, []) if now - t < AUTH_LOCKOUT_SECONDS]
    recent.append(now)
    _login_failures[key] = recent
    if len(recent) >= AUTH_MAX_FAILURES:
        _login_locks[key] = now + AUTH_LOCKOUT_SECONDS
        _login_failures[key] = []
    return AUTH_MAX_FAILURES - len(recent)

def auth_clear_failures(username, ip):
    _login_failures.pop(auth_lock_key(username, ip), None)
    _login_locks.pop(auth_lock_key(username, ip), None)

def ensure_auth_tables():
    """Create auth tables and seed the admin user on first boot."""
    conn = db_conn(); cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS auth_users (
            username   VARCHAR(100) PRIMARY KEY,
            salt       VARCHAR(64) NOT NULL,
            pwhash     VARCHAR(128) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS auth_sessions (
            token      VARCHAR(128) PRIMARY KEY,
            username   VARCHAR(100) NOT NULL,
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )""")
    cur.execute("SELECT COUNT(*) FROM auth_users")
    if cur.fetchone()[0] == 0:
        # First boot: seed admin from env/config if provided; otherwise
        # generate a random one and print it ONCE to the server log
        # (view with: journalctl -u leadgen-api | head -50).
        seed_pw = os.environ.get('ADMIN_PASSWORD', '')
        if not seed_pw:
            try:
                with open(CONFIG_FILE) as f:
                    seed_pw = json.load(f).get('admin_password', '')
            except Exception:
                seed_pw = ''
        generated = False
        if not seed_pw:
            seed_pw = _h_secrets.token_urlsafe(12)
            generated = True
        salt = _h_secrets.token_hex(16)
        cur.execute("INSERT INTO auth_users (username, salt, pwhash) VALUES (%s, %s, %s)",
                    ('admin', salt, auth_hash(seed_pw, salt)))
        if generated:
            print('=' * 64)
            print('FIRST BOOT — admin login generated:')
            print(f'  username: admin')
            print(f'  password: {seed_pw}')
            print('Save it now, then change it: POST /auth/change-password')
            print('(this is shown only once — recover by deleting the')
            print(' auth_users table and restarting)')
            print('=' * 64)
        else:
            print('Admin user seeded from ADMIN_PASSWORD / config.json')
    conn.commit(); cur.close(); conn.close()

def auth_hash(password, salt):
    return _h_hashlib.sha256((password + salt).encode()).hexdigest()

def auth_login(username, password, ip=''):
    if auth_is_locked(username, ip):
        return None
    try:
        conn = db_conn(); cur = conn.cursor()
        cur.execute("SELECT salt, pwhash FROM auth_users WHERE username = %s", (username,))
        row = cur.fetchone()
    except Exception:
        return None
    if not row or auth_hash(password, row[0]) != row[1]:
        try: cur.close(); conn.close()
        except Exception: pass
        auth_record_failure(username, ip)
        return None
    token = _h_secrets.token_urlsafe(48)
    try:
        cur.execute("INSERT INTO auth_sessions (token, username, expires_at) VALUES (%s, %s, NOW() + INTERVAL '%s days')",
                    (token, username, AUTH_SESSION_DAYS))
        conn.commit(); cur.close(); conn.close()
    except Exception:
        pass
    auth_clear_failures(username, ip)
    return token

def auth_check(token):
    if not token: return None
    if SERVICE_TOKEN and token == SERVICE_TOKEN:
        return 'service'          # internal service account (controva_api)
    try:
        conn = db_conn(); cur = conn.cursor()
        cur.execute("SELECT username FROM auth_sessions WHERE token = %s AND expires_at > NOW()", (token,))
        row = cur.fetchone()
        cur.close(); conn.close()
        return row[0] if row else None
    except Exception:
        return None

def auth_logout(token):
    try:
        conn = db_conn(); cur = conn.cursor()
        cur.execute("DELETE FROM auth_sessions WHERE token = %s", (token,))
        conn.commit(); cur.close(); conn.close()
    except Exception:
        pass
    return True

def auth_change_password(username, old_password, new_password):
    if len(new_password or '') < 10:
        return False, 'New password must be at least 10 characters'
    try:
        conn = db_conn(); cur = conn.cursor()
        cur.execute("SELECT salt, pwhash FROM auth_users WHERE username = %s", (username,))
        row = cur.fetchone()
        if not row or auth_hash(old_password, row[0]) != row[1]:
            cur.close(); conn.close()
            return False, 'Current password is incorrect'
        new_salt = _h_secrets.token_hex(16)
        cur.execute("UPDATE auth_users SET salt = %s, pwhash = %s WHERE username = %s",
                    (new_salt, auth_hash(new_password, new_salt), username))
        # Invalidate all existing sessions — force re-login everywhere
        cur.execute("DELETE FROM auth_sessions WHERE username = %s", (username,))
        conn.commit(); cur.close(); conn.close()
        return True, 'Password updated. All sessions revoked — log in again.'
    except Exception as e:
        return False, str(e)

def ensure_service_token():
    """Generate and persist the internal service token on first boot."""
    global SERVICE_TOKEN
    if SERVICE_TOKEN:
        return SERVICE_TOKEN
    SERVICE_TOKEN = _h_secrets.token_urlsafe(32)
    try:
        data = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE) as f:
                data = json.load(f)
        data['service_token'] = SERVICE_TOKEN
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        print(f'Service token generated and saved to {CONFIG_FILE}')
    except Exception as e:
        print(f'Warning: could not persist service token: {e}')
    return SERVICE_TOKEN

# ──────────────────────────────────────────────────────────────
#  M4: FOLLOW-UP SEQUENCES — automatic multi-touch outreach
#  Default: Day 0 initial → Day 3 nudge → Day 8 final note.
#  Stops automatically on reply, unsubscribe, or bounced email.
# ──────────────────────────────────────────────────────────────
DEFAULT_SEQUENCE = [
    {'step': 1, 'delay_days': 0,  'kind': 'initial'},   # uses existing generated email
    {'step': 2, 'delay_days': 3,  'kind': 'nudge'},
    {'step': 3, 'delay_days': 8,  'kind': 'final'},
]

def ensure_m4_tables():
    conn = db_conn(); cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sequences (
            id          SERIAL PRIMARY KEY,
            name        VARCHAR(200) NOT NULL,
            is_active   BOOLEAN DEFAULT TRUE,
            created_at  TIMESTAMPTZ DEFAULT NOW()
        )""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sequence_steps (
            id           SERIAL PRIMARY KEY,
            sequence_id  INT REFERENCES sequences(id) ON DELETE CASCADE,
            step_number  INT NOT NULL,
            delay_days   INT NOT NULL DEFAULT 0,
            kind         VARCHAR(30) NOT NULL,   -- initial | nudge | final
            UNIQUE (sequence_id, step_number)
        )""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS enrollments (
            id            SERIAL PRIMARY KEY,
            lead_id       UUID REFERENCES leads(id) ON DELETE CASCADE,
            sequence_id   INT REFERENCES sequences(id) ON DELETE CASCADE,
            current_step  INT DEFAULT 1,
            next_send_at  TIMESTAMPTZ,
            status        VARCHAR(30) DEFAULT 'active',  -- active|completed|stopped|replied|unsubscribed|bounced
            stop_reason   TEXT,
            steps_sent    INT DEFAULT 0,
            last_sent_at  TIMESTAMPTZ,
            created_at    TIMESTAMPTZ DEFAULT NOW(),
            updated_at    TIMESTAMPTZ DEFAULT NOW()
        )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_enroll_due ON enrollments(status, next_send_at)")
    # Seed the default sequence once
    cur.execute("SELECT COUNT(*) FROM sequences")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO sequences (name) VALUES ('3-Touch Outreach') RETURNING id")
        seq_id = cur.fetchone()[0]
        for st in DEFAULT_SEQUENCE:
            cur.execute("INSERT INTO sequence_steps (sequence_id, step_number, delay_days, kind) VALUES (%s,%s,%s,%s)",
                        (seq_id, st['step'], st['delay_days'], st['kind']))
    conn.commit(); cur.close(); conn.close()

def generate_followup_copy(business_name, niche, city, owner_name, kind, prev_subject=''):
    """Claude-generated follow-up emails (sequence steps 2 and 3)."""
    if not CLAUDE_KEY:
        return None
    if kind == 'nudge':
        spec = ("This is follow-up #2 of 3 (they got an initial email 3 days ago offering a free "
                "website mockup). Keep it under 70 words. Reference the mockup we made for them. "
                "One soft question. Friendly, zero pressure. DON'T apologize for emailing again.")
    else:
        spec = ("This is follow-up #3 of 3, the final message (initial + one nudge already sent). "
                "Under 50 words. Politely signal this is the last email — e.g. asking whether to "
                "close their file. Leave the door open. No guilt-tripping.")
    name_part = owner_name if owner_name else 'there'
    prompt = f"""Write a cold-outreach follow-up email for a small business owner.

Business: {business_name}
Type: {niche}
City: {city}
Owner: {name_part}
Previous email subject: {prev_subject or '(initial offer of a free website mockup)'}
{spec}

Respond ONLY with valid JSON:
{{"subject": "<under 7 words, Re: style ok>", "body": "<body with \\n for line breaks>"}}"""
    try:
        body = json.dumps({
            'model': 'claude-opus-4-5', 'max_tokens': 400,
            'messages': [{'role': 'user', 'content': prompt}]
        }).encode()
        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages', data=body, method='POST',
            headers={'x-api-key': CLAUDE_KEY, 'anthropic-version': '2023-06-01',
                     'Content-Type': 'application/json'})
        resp = urllib.request.urlopen(req, timeout=30)
        text = json.loads(resp.read().decode())['content'][0]['text']
        m = re.search(r'\{[\s\S]*\}', text)
        if m:
            log_api_usage('claude', 'email_copy')
            return json.loads(m.group())
    except Exception as e:
        print(f'[sequence] claude {kind} failed: {e}')
    return None

# ──────────────────────────────────────────────────────────────
#  M5: COST TRACKING — every paid API call logged with an estimate
# ──────────────────────────────────────────────────────────────
COST_PER_CALL = {
    'serper': 0.001, 'gemini': 0.0002, 'claude': 0.03,
    'google_places': 0.032, 'oxylabs': 0.002, 'replicate': 0.003,
    'imagine_art': 0.005, 'resend': 0.0005, 'millionverifier': 0.001,
}

def ensure_m5_tables():
    conn = db_conn(); cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS api_usage (
            id          BIGSERIAL PRIMARY KEY,
            provider    VARCHAR(60) NOT NULL,
            endpoint    VARCHAR(120),
            cost        NUMERIC(10,6) NOT NULL DEFAULT 0,
            meta        TEXT,
            created_at  TIMESTAMPTZ DEFAULT NOW()
        )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_api_usage_time ON api_usage(created_at DESC)")
    conn.commit(); cur.close(); conn.close()

def log_api_usage(provider, endpoint='', cost=None, meta=''):
    """Fire-and-forget cost logging. NEVER raises into the caller."""
    try:
        c = COST_PER_CALL.get(provider, 0) if cost is None else cost
        conn = db_conn(); cur = conn.cursor()
        cur.execute("INSERT INTO api_usage (provider, endpoint, cost, meta) VALUES (%s,%s,%s,%s)",
                    (provider, endpoint[:120], c, (meta or '')[:300]))
        conn.commit(); cur.close(); conn.close()
    except Exception:
        pass

def enroll_lead_in_default(lead_id):
    """Enroll a lead into the default 3-touch sequence (step 1 sends on the next tick)."""
    try:
        conn = db_conn(); cur = conn.cursor()
        cur.execute("SELECT id FROM sequences WHERE is_active ORDER BY id LIMIT 1")
        row = cur.fetchone()
        if not row:
            cur.close(); conn.close(); return {'success': False, 'error': 'no sequence configured'}
        seq_id = row[0]
        cur.execute("""SELECT id, status FROM enrollments
                       WHERE lead_id = %s AND status = 'active'""", (lead_id,))
        if cur.fetchone():
            cur.close(); conn.close(); return {'success': False, 'error': 'already enrolled'}
        cur.execute("""INSERT INTO enrollments (lead_id, sequence_id, current_step, next_send_at, status)
                       VALUES (%s, %s, 1, NOW(), 'active') RETURNING id""", (lead_id, seq_id))
        enrollment_id = cur.fetchone()[0]
        conn.commit(); cur.close(); conn.close()
        return {'success': True, 'enrollment_id': enrollment_id}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def stop_enrollment(lead_id, status, reason):
    """Auto-exit hook: called on reply/unsubscribe/bounce."""
    try:
        conn = db_conn(); cur = conn.cursor()
        cur.execute("""UPDATE enrollments SET status=%s, stop_reason=%s, updated_at=NOW()
                       WHERE lead_id=%s AND status='active'""", (status, reason, lead_id))
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        print(f'[sequence] stop failed: {e}')

def get_sequence_step_assets(lead_id, step, kind, detail):
    """Return (subject, body) for a step, generating + caching follow-ups via Claude."""
    if step == 1:
        return detail.get('email_subject') or '', detail.get('email_body') or ''
    subj_key, body_key = f'email_subject_step{step}', f'email_body_step{step}'
    conn = db_conn(); cur = conn.cursor()
    cur.execute("""SELECT (SELECT content FROM assets WHERE lead_id=%s AND asset_type=%s LIMIT 1),
                          (SELECT content FROM assets WHERE lead_id=%s AND asset_type=%s LIMIT 1)""",
                (lead_id, subj_key, lead_id, body_key))
    row = cur.fetchone(); cur.close(); conn.close()
    if row and row[0] and row[1]:
        return row[0], row[1]
    copy = generate_followup_copy(detail['business_name'], detail['niche'], detail['city'],
                                  detail.get('owner_name'), kind,
                                  prev_subject=detail.get('email_subject') or '')
    if not copy:
        return None, None
    conn = db_conn(); cur = conn.cursor()
    cur.execute("INSERT INTO assets (lead_id, asset_type, content) VALUES (%s,%s,%s)", (lead_id, subj_key, copy['subject']))
    cur.execute("INSERT INTO assets (lead_id, asset_type, content) VALUES (%s,%s,%s)", (lead_id, body_key, copy['body']))
    conn.commit(); cur.close(); conn.close()
    return copy['subject'], copy['body']

def process_due_enrollments():
    """One scheduler pass: send every due step, respect all M2/M3 gates."""
    if not CONFIG.get('sequences_enabled', True):
        return
    sent, skipped, stopped = 0, 0, 0
    try:
        conn = db_conn(); cur = conn.cursor()
        cur.execute("""
            SELECT e.id, e.lead_id::text, e.current_step, ss.delay_days, ss.kind
            FROM enrollments e
            JOIN sequences q ON q.id = e.sequence_id AND q.is_active
            JOIN sequence_steps ss ON ss.sequence_id = e.sequence_id AND ss.step_number = e.current_step
            WHERE e.status = 'active' AND e.next_send_at <= NOW()
            ORDER BY e.next_send_at ASC LIMIT 25
        """)
        due = cur.fetchall(); cur.close(); conn.close()
    except Exception as e:
        print(f'[sequence] due query failed: {e}')
        return

    for en_id, lead_id, step, delay_days, kind in due:
        detail = get_lead_detail(lead_id)
        if not detail:
            continue
        # Auto-exit conditions
        lstatus = (detail.get('status') or '').lower()
        if lstatus in ('replied', 'closed'):
            stop_enrollment(lead_id, 'replied', 'lead replied'); stopped += 1; continue
        if lstatus in ('unsubscribed', 'rejected'):
            stop_enrollment(lead_id, 'unsubscribed', f'lead status {lstatus}'); stopped += 1; continue

        # Deliverability + suppression + throttle gates (same as manual send)
        email, estatus = contact_email_for_sending(lead_id)
        if not email or estatus == 'undeliverable':
            stop_enrollment(lead_id, 'bounced', f'email {estatus or "missing"}'); stopped += 1; continue
        if estatus not in ('deliverable', 'risky'):
            skipped += 1; continue
        if is_suppressed(email):
            stop_enrollment(lead_id, 'unsubscribed', 'address suppressed'); stopped += 1; continue
        ok, throttle_info = send_throttle_status()
        if not ok:
            print(f'[sequence] throttle: {throttle_info}')
            skipped += 1
            break   # hour/day cap reached — stop processing, retry next tick

        subject, body = get_sequence_step_assets(lead_id, step, kind, detail)
        if not subject or not body:
            print(f'[sequence] step {step} copy unavailable for {lead_id} (no Claude key?)')
            skipped += 1
            # Push a day so we don't spin
            try:
                conn = db_conn(); cur = conn.cursor()
                cur.execute("UPDATE enrollments SET next_send_at = NOW() + INTERVAL '1 day', updated_at=NOW() WHERE id=%s", (en_id,))
                conn.commit(); cur.close(); conn.close()
            except Exception:
                pass
            continue

        unsub_token = get_or_create_unsub_token(lead_id)
        body_html = body.replace('\n', '<br>')
        if detail.get('mockup_url'):
            body_html += f'<br><br><img src="{detail["mockup_url"]}" alt="Website Mockup" style="max-width:100%; border-radius:8px;">'
        result = send_email_via_resend(email, subject, body, body_html,
                                       unsub_url=build_unsub_url(unsub_token))
        try:
            conn = db_conn(); cur = conn.cursor()
            if result.get('success'):
                cur.execute("""INSERT INTO outreach_log (lead_id, email_to, email_subject, email_body,
                               mockup_url, sent_at, status, resend_message_id)
                               VALUES (%s,%s,%s,%s,%s,NOW(),'sent',%s)""",
                            (lead_id, email, subject, body, detail.get('mockup_url') or '',
                             result.get('message_id')))
                # advance; gap to next step from the schedule (absolute days → difference)
                cur.execute("""SELECT ns.delay_days - ss.delay_days FROM enrollments e
                               JOIN sequence_steps ss ON ss.sequence_id=e.sequence_id AND ss.step_number=e.current_step
                               JOIN sequence_steps ns ON ns.sequence_id=e.sequence_id AND ns.step_number=e.current_step+1
                               WHERE e.id=%s""", (en_id,))
                gap_row = cur.fetchone()
                if step >= 3 or not gap_row:
                    cur.execute("""UPDATE enrollments SET steps_sent=steps_sent+1, last_sent_at=NOW(),
                                   status='completed', current_step=current_step+1, updated_at=NOW() WHERE id=%s""", (en_id,))
                else:
                    gap_days = max(int(gap_row[0]), 1)
                    cur.execute("""UPDATE enrollments SET steps_sent=steps_sent+1, last_sent_at=NOW(),
                                   current_step=current_step+1, next_send_at=NOW() + (%s || ' days')::interval,
                                   updated_at=NOW() WHERE id=%s""", (str(gap_days), en_id))
                sent += 1
            else:
                err = str(result.get('error'))[:200]
                # auth errors = permanent stop; anything else (network, provider
                # hiccup) = retry tomorrow instead of hammering every 10 minutes
                if '403' in err or '401' in err:
                    cur.execute("UPDATE enrollments SET status='stopped', stop_reason=%s, updated_at=NOW() WHERE id=%s",
                                (f'send failed: {err}', en_id))
                    stopped += 1
                else:
                    cur.execute("UPDATE enrollments SET stop_reason=%s, next_send_at=NOW() + INTERVAL '1 day', updated_at=NOW() WHERE id=%s",
                                (f'send failed: {err}', en_id))
            conn.commit(); cur.close(); conn.close()
        except Exception as e:
            print(f'[sequence] update failed: {e}')
    if sent or stopped:
        print(f'[sequence] pass: sent={sent} skipped={skipped} stopped={stopped}')

def sequence_scheduler_loop():
    """Background thread: process due sequence steps every N minutes."""
    interval = max(int(CONFIG.get('sequence_interval_minutes', 10)), 1) * 60
    while True:
        try:
            process_due_enrollments()
        except Exception as e:
            print(f'[sequence] scheduler error: {e}')
        time.sleep(interval)

# ──────────────────────────────────────────────────────────────
#  M3: OUTREACH COMPLIANCE — suppression, throttle, unsubscribe
# ──────────────────────────────────────────────────────────────
def ensure_m3_tables():
    """Unsubscribe/suppression table + per-lead unsubscribe tokens (idempotent)."""
    conn = db_conn(); cur = conn.cursor()
    cur.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS unsub_token VARCHAR(64)")
    cur.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_unsub_token
                   ON leads(unsub_token) WHERE unsub_token IS NOT NULL""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS unsubscribes (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            email           VARCHAR(500),
            email_domain    VARCHAR(300),
            lead_id         UUID REFERENCES leads(id) ON DELETE SET NULL,
            type            VARCHAR(30) NOT NULL DEFAULT 'unsubscribe',
            reason          TEXT,
            created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_unsub_email  ON unsubscribes(email)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_unsub_domain ON unsubscribes(email_domain)")
    conn.commit(); cur.close(); conn.close()

def add_suppression(email, stype='unsubscribe', lead_id=None, reason='', domain_wide=False):
    """Record a suppressed address (or whole domain). Idempotent per (email/domain, type)."""
    email = (email or '').strip().lower()
    if not email and not domain_wide: return
    domain = email.rsplit('@', 1)[1] if '@' in email else ''
    conn = db_conn(); cur = conn.cursor()
    try:
        cur.execute("""
            SELECT 1 FROM unsubscribes
            WHERE (email = %s OR (email IS NULL AND email_domain = %s AND %s))
              AND type = %s LIMIT 1
        """, (email or None, domain, 'true' if domain_wide else 'false', stype))
        if cur.fetchone():
            conn.commit(); cur.close(); conn.close(); return
        cur.execute("""
            INSERT INTO unsubscribes (email, email_domain, lead_id, type, reason)
            VALUES (%s, %s, %s, %s, %s)
        """, (email if not domain_wide else None,
              domain or None, lead_id, stype, reason))
        conn.commit()
    except Exception as e:
        print(f'[suppression] add failed: {e}'); conn.rollback()
    finally:
        cur.close(); conn.close()

def is_suppressed(email):
    """True when the address or its whole domain is suppressed for any reason."""
    email = (email or '').strip().lower()
    if not email or '@' not in email: return False
    domain = email.rsplit('@', 1)[1]
    try:
        conn = db_conn(); cur = conn.cursor()
        cur.execute("""SELECT 1 FROM unsubscribes
                       WHERE email = %s OR (email_domain = %s AND email IS NULL) LIMIT 1""",
                    (email, domain))
        row = cur.fetchone(); cur.close(); conn.close()
        return bool(row)
    except Exception:
        return False   # DB down → don't block sends on a broken check

def get_or_create_unsub_token(lead_id, cur=None):
    """Stable random token used in the unsubscribe URL for this lead."""
    own_conn = cur is None
    if own_conn:
        conn = db_conn(); cur = conn.cursor()
    cur.execute("SELECT unsub_token FROM leads WHERE id = %s", (lead_id,))
    row = cur.fetchone()
    if row and row[0]:
        if own_conn: cur.close(); conn.close()
        return row[0]
    token = _h_secrets.token_urlsafe(24)
    cur.execute("UPDATE leads SET unsub_token = %s WHERE id = %s", (token, lead_id))
    if own_conn:
        conn.commit(); cur.close(); conn.close()
    return token

def build_unsub_url(token):
    base = (PUBLIC_BASE_URL or '').rstrip('/')
    if base:
        return f'{base}/u/{token}'
    # No public base URL configured — fall back to a reply-to-unsubscribe
    # instruction (still CAN-SPAM compliant as a mechanism).
    return None

def send_throttle_status():
    """Return (ok, reason) against the hourly/daily send caps."""
    try:
        conn = db_conn(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM outreach_log WHERE sent_at > NOW() - INTERVAL '1 hour'")
        hourly = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM outreach_log WHERE sent_at > NOW() - INTERVAL '24 hours'")
        daily = cur.fetchone()[0]
        cur.close(); conn.close()
        h_limit = int(CONFIG.get('send_hourly_limit', 30))
        d_limit = int(CONFIG.get('send_daily_limit', 100))
        if daily >= d_limit:
            return False, f'Daily send cap reached ({daily}/{d_limit}) — resume after the 24h window resets'
        if hourly >= h_limit:
            return False, f'Hourly send cap reached ({hourly}/{h_limit}) — wait before sending more'
        return True, f'{hourly}/{h_limit} hourly, {daily}/{d_limit} daily'
    except Exception:
        return True, 'throttle check unavailable'

# ──────────────────────────────────────────────────────────────
#  M4: EMAIL SENDING via RESEND.COM
# ──────────────────────────────────────────────────────────────
RESEND_KEY = os.environ.get('RESEND_KEY', '')
FROM_EMAIL = os.environ.get('FROM_EMAIL', 'you@yourdomain.com')
FROM_NAME  = os.environ.get('FROM_NAME', 'Controva')


# ──────────────────────────────────────────────────────────────
#  M3: RESEND WEBHOOK — real delivery/open/bounce/complaint tracking
# ──────────────────────────────────────────────────────────────
def verify_svix_signature(headers, raw_body, secret, tolerance_secs=300):
    """Resend signs webhooks with Svix (svix-id, svix-timestamp, svix-signature).
    Signed content = "{id}.{timestamp}.{body}", HMAC-SHA256, base64.
    Returns (ok, reason)."""
    import hmac as _hmac
    import base64 as _b64
    svix_id = headers.get('svix-id') or headers.get('Svix-Id')
    ts_hdr  = headers.get('svix-timestamp') or headers.get('Svix-Timestamp')
    sig_hdr = headers.get('svix-signature') or headers.get('Svix-Signature') or ''
    if not (svix_id and ts_hdr and sig_hdr):
        return False, 'missing svix headers'
    try:
        age = abs(time.time() - int(ts_hdr))
        if age > tolerance_secs:
            return False, f'timestamp skew too large ({age:.0f}s)'
    except ValueError:
        return False, 'bad timestamp'
    signed = f'{svix_id}.{ts_hdr}.'.encode() + raw_body
    expected = _b64.b64encode(_hmac.new(secret.encode(), signed, _h_hashlib.sha256).digest()).decode()
    # signature header may contain multiple space-separated v1,<sig> pairs
    for part in sig_hdr.split(' '):
        if part.startswith('v1,'):
            if _hmac.compare_digest(part[3:], expected):
                return True, 'ok'
    return False, 'signature mismatch'

def handle_resend_webhook(headers, raw_body):
    """Process a verified Resend event. Returns a dict summary."""
    if not RESEND_WEBHOOK_SECRET:
        return {'ok': False, 'status': 503, 'error': 'resend_webhook_secret not configured (Settings)'}
    ok, reason = verify_svix_signature(headers, raw_body, RESEND_WEBHOOK_SECRET)
    if not ok:
        return {'ok': False, 'status': 401, 'error': f'signature verification failed: {reason}'}
    try:
        event = json.loads(raw_body.decode('utf-8'))
    except Exception:
        return {'ok': False, 'status': 400, 'error': 'invalid JSON'}
    etype = event.get('type', '')
    data = event.get('data') or {}
    msg_id = (data.get('email') or {}).get('id') or data.get('emailId') or ''
    to_email = ((data.get('email') or {}).get('to') or data.get('recipient') or '')
    if isinstance(to_email, list): to_email = to_email[0] if to_email else ''
    summary = {'ok': True, 'type': etype, 'message_id': msg_id}

    try:
        conn = db_conn(); cur = conn.cursor()
        if etype == 'email.delivered':
            cur.execute("UPDATE outreach_log SET status='delivered' WHERE resend_message_id=%s", (msg_id,))
        elif etype == 'email.opened':
            # FIRST open writes opened_at; later opens just refresh status
            cur.execute("""UPDATE outreach_log SET opened_at=COALESCE(opened_at, NOW()), status='opened'
                           WHERE resend_message_id=%s""", (msg_id,))
            cur.execute("""UPDATE leads l SET status='opened' FROM outreach_log o
                           WHERE o.lead_id=l.id AND o.resend_message_id=%s
                             AND l.status IN ('sent','delivered','opened')""", (msg_id,))
        elif etype == 'email.bounced':
            cur.execute("UPDATE outreach_log SET status='bounced' WHERE resend_message_id=%s", (msg_id,))
            if to_email:
                add_suppression(to_email, 'bounce', reason='hard bounce reported by Resend')
                cur.execute("UPDATE enrollments SET status='bounced', stop_reason='hard bounce', updated_at=NOW() "
                            "WHERE status='active' AND lead_id IN "
                            "(SELECT lead_id FROM outreach_log WHERE resend_message_id=%s)", (msg_id,))
                cur.execute("""UPDATE contacts SET email_status='undeliverable', email_checked_at=NOW()
                               WHERE LOWER(email)=LOWER(%s)""", (to_email,))
        elif etype == 'email.complained':
            cur.execute("UPDATE outreach_log SET status='complained' WHERE resend_message_id=%s", (msg_id,))
            if to_email:
                # Spam complaint → suppress the entire domain: they run aggressive filters
                add_suppression(to_email, 'complaint', reason='spam complaint', domain_wide=True)
        conn.commit(); cur.close(); conn.close()
        print(f'[webhook] {etype} msg={msg_id} to={to_email}')
    except Exception as e:
        print(f'[webhook] db error: {e}')
        summary['db_error'] = str(e)
    return summary


# ──────────────────────────────────────────────────────────────
#  M3: REPLY DETECTION via IMAP (lightweight)
# ──────────────────────────────────────────────────────────────
def run_check_replies_bg(job_id):
    """Scan the reply mailbox via IMAP for messages that answer our outreach.
    Matches senders against outreach_log, marks replied_at + lead status."""
    import imaplib
    import email as _email_lib
    try:
        JOBS[job_id] = {'status': 'running', 'progress': 0,
                        'log': [f'Connecting to {IMAP_HOST}…'], 'step': 'Check Replies'}
        if not (IMAP_HOST and IMAP_USER and IMAP_PASS):
            JOBS[job_id]['log'].append('IMAP not configured — set imap_host/user/pass in Settings')
            JOBS[job_id]['status'] = 'failed'
            return

        imap = imaplib.IMAP4_SSL(IMAP_HOST)
        imap.login(IMAP_USER, IMAP_PASS)
        imap.select('INBOX')
        # Search messages addressed to us that look like replies (auto "Re:")
        _, msg_ids = imap.search(None, 'TO', f'"{IMAP_USER}"', 'SUBJECT', '"Re:"')
        ids = (msg_ids[0] or b'').split()
        JOBS[job_id]['log'].append(f'Found {len(ids)} reply-candidates in INBOX')

        matched = 0
        for num in ids[-200:]:   # newest 200 max
            _, msg_data = imap.fetch(num, '(RFC822)')
            raw = msg_data[0][1]
            msg = _email_lib.message_from_bytes(raw)
            sender = (_email_lib.utils.parseaddr(msg.get('From', ''))[1] or '').lower()
            if not sender:
                continue
            try:
                conn = db_conn(); cur = conn.cursor()
                cur.execute("""SELECT o.id, o.lead_id FROM outreach_log o
                               WHERE LOWER(o.email_to) = %s
                                 AND o.replied_at IS NULL
                                 AND o.status IN ('sent','delivered','opened')""",
                            (sender,))
                row = cur.fetchone()
                if row:
                    body_preview = ''
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == 'text/plain':
                                body_preview = (part.get_payload(decode=True) or b'')[:2000].decode('utf-8', 'ignore')
                                break
                    else:
                        body_preview = (msg.get_payload(decode=True) or b'')[:2000].decode('utf-8', 'ignore')
                    cur.execute("""UPDATE outreach_log SET replied_at=NOW(), status='replied',
                                   reply_content=%s WHERE id=%s""", (body_preview, row[0]))
                    cur.execute("UPDATE leads SET status='replied' WHERE id=%s", (row[1],))
                    stop_enrollment(row[1], 'replied', 'reply detected via IMAP')
                    conn.commit(); matched += 1
                    JOBS[job_id]['log'].append(f'Reply matched: {sender}')
                cur.close(); conn.close()
            except Exception as e:
                print(f'[replies] {sender}: {e}')
        imap.logout()
        JOBS[job_id]['log'].append(f'Done — {matched} new replies matched to outreach')
        JOBS[job_id]['progress'] = 100
        JOBS[job_id]['status'] = 'completed'
        JOBS[job_id]['results'] = {'matched': matched}
    except Exception as e:
        JOBS[job_id]['status'] = 'failed'
        JOBS[job_id]['error'] = str(e)
        JOBS[job_id]['log'].append(f'Error: {e}')

def handle_unsubscribe(token):
    """Process an unsubscribe click. Returns a plain confirmation page (HTML string).
    Suppresses the address AND the whole domain? No — address only; domain-wide
    suppression is reserved for spam complaints."""
    token = (token or '').strip()
    if not token or len(token) > 128:
        return ('<html><body style="font-family:sans-serif;text-align:center;padding-top:60px;">'
                '<h2>Invalid link</h2></body></html>')
    try:
        conn = db_conn(); cur = conn.cursor()
        cur.execute("""SELECT l.id, c.email FROM leads l
                       LEFT JOIN LATERAL (
                           SELECT email FROM contacts WHERE lead_id = l.id
                           ORDER BY (COALESCE(email,'') != '') DESC, created_at DESC LIMIT 1
                       ) c ON TRUE
                       WHERE l.unsub_token = %s""", (token,))
        row = cur.fetchone()
        if not row:
            cur.close(); conn.close()
            return ('<html><body style="font-family:sans-serif;text-align:center;padding-top:60px;">'
                    '<h2>Link expired or invalid</h2>'
                    '<p style="color:#666;">No subscription found for this link.</p></body></html>')
        lead_id, email = row
        if email:
            add_suppression(email, 'unsubscribe', lead_id=lead_id,
                            reason='clicked unsubscribe link')
        cur.execute("UPDATE leads SET status='unsubscribed' WHERE id=%s AND status NOT IN "
                    "('replied','closed')", (lead_id,))
        stop_enrollment(lead_id, 'unsubscribed', 'clicked unsubscribe link')
        conn.commit(); cur.close(); conn.close()
        print(f'[unsubscribe] lead {lead_id} ({email})')
        return ('<html><body style="font-family:sans-serif;text-align:center;padding-top:60px;">'
                '<h2>You have been removed &#10003;</h2>'
                '<p style="color:#666;">You will not receive any further emails from us.</p>'
                '</body></html>')
    except Exception as e:
        print(f'[unsubscribe] error: {e}')
        return ('<html><body style="font-family:sans-serif;text-align:center;padding-top:60px;">'
                '<h2>Something went wrong</h2>'
                '<p style="color:#666;">Please reply to the email with "unsubscribe".</p></body></html>')

def build_compliance_footer(unsub_url=None):
    """CAN-SPAM/GDPR footer: unsubscribe mechanism + company name + postal address.
    Every commercial email must carry these — non-negotiable."""
    lines = ['—']
    if unsub_url:
        lines.append(f'Don\'t want emails from us? <a href="{unsub_url}" style="color:#888;">Unsubscribe</a>')
    else:
        lines.append(f'Don\'t want emails from us? Reply with "unsubscribe" and we\'ll remove you immediately.')
    if COMPANY_ADDRESS:
        lines.append(f'{COMPANY_NAME} · {COMPANY_ADDRESS}')
    elif COMPANY_NAME:
        lines.append(COMPANY_NAME)
    return '\n'.join(lines)

def send_email_via_resend(to_email, subject, body_text, body_html=None, from_email=None,
                          from_name=None, unsub_url=None, skip_footer=False):
    """Send an email via Resend.com API. Appends the compliance footer unless
    skip_footer is set (use ONLY for non-commercial transactional mail)."""
    if not body_html:
        # Convert plain text with line breaks to HTML
        body_html = body_text.replace("\\n", "<br>")
        body_html = f"""<html><body style="font-family: -apple-system, sans-serif; font-size: 15px; line-height: 1.6; color: #333; max-width: 600px;">{body_html}</body></html>"""

    if not skip_footer:
        footer_html = ('<div style="margin-top:24px; padding-top:12px; border-top:1px solid #eee;'
                       ' font-size:12px; color:#888; line-height:1.5;">'
                       + build_compliance_footer(unsub_url) + '</div>')
        footer_text = '\n\n' + re.sub(r'<[^>]+>', '', build_compliance_footer(unsub_url))
        body_html = body_html.replace('</body>', footer_html + '</body>')
        body_text = body_text + footer_text

    payload = {
        "from": f"{from_name or FROM_NAME} <{from_email or FROM_EMAIL}>",
        "to": [to_email],
        "subject": subject,
        "html": body_html,
        "text": body_text
    }

    try:
        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=json.dumps(payload).encode(),
            method="POST",
            headers={
                "Authorization": f"Bearer {RESEND_KEY}",
                "Content-Type": "application/json"
            }
        )
        resp = urllib.request.urlopen(req, timeout=20)
        data = json.loads(resp.read().decode())
        log_api_usage('resend', 'send')
        return {"success": True, "message_id": data.get("id"), "data": data}
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        return {"success": False, "error": err, "code": e.code}
    except Exception as e:
        return {"success": False, "error": str(e)}

def send_lead_email(lead_id):
    """Send the prepared email for a specific lead."""
    conn = db_conn(); cur = conn.cursor()
    cur.execute("""
        SELECT l.id, l.business_name, l.niche, l.city,
               c.email, c.full_name,
               (SELECT content FROM assets WHERE lead_id=l.id AND asset_type='email_subject' LIMIT 1) as subj,
               (SELECT content FROM assets WHERE lead_id=l.id AND asset_type='email_body' LIMIT 1) as body,
               (SELECT content FROM assets WHERE lead_id=l.id AND asset_type='mockup_image' LIMIT 1) as mockup
        FROM leads l LEFT JOIN contacts c ON c.lead_id = l.id
        WHERE l.id = %s
    """, (lead_id,))
    row = cur.fetchone()

    if not row:
        cur.close(); conn.close()
        return {"success": False, "error": "Lead not found"}

    lead_id, name, niche, city, email, full_name, subj, body, mockup = row

    if not subj or not body:
        cur.close(); conn.close()
        return {"success": False, "error": "Email copy not generated yet"}
    cur.close(); conn.close()

    # Deliverability gate: verify (or re-verify if stale) before sending.
    email, estatus = contact_email_for_sending(lead_id)
    if not email:
        return {"success": False, "error": "No email for this lead"}
    if estatus == 'undeliverable':
        return {"success": False, "error": "Blocked: email failed verification (undeliverable) — "
                                           "re-enrich this lead to find a working address"}
    if estatus not in ('deliverable', 'risky'):
        return {"success": False, "error": f"Blocked: email not verified yet (status: {estatus}). "
                                           "Run verification from the Pipeline page first"}
    # Suppression gate: unsubscribes, past bounces, spam complaints
    if is_suppressed(email):
        return {"success": False, "error": "Blocked: this address (or its domain) unsubscribed, "
                                           "bounced, or complained before — it is permanently suppressed"}
    # Send throttle: hourly/daily caps protect sender reputation
    ok, throttle_info = send_throttle_status()
    if not ok:
        return {"success": False, "error": f"Blocked: {throttle_info}"}

    # Build HTML version with mockup if available
    body_html = body.replace("\\n", "<br>")
    if mockup:
        body_html += f'<br><br><img src="{mockup}" alt="Website Mockup for {name}" style="max-width:100%; border-radius:8px;">'
    body_html = f"""<html><body style="font-family: -apple-system, BlinkMacSystemFont, sans-serif; font-size: 15px; line-height: 1.6; color: #333; max-width: 600px; padding: 16px;">{body_html}</body></html>"""

    unsub_token = get_or_create_unsub_token(lead_id)
    result = send_email_via_resend(email, subj, body, body_html,
                                   unsub_url=build_unsub_url(unsub_token))

    if result.get("success"):
        conn = db_conn(); cur = conn.cursor()
        cur.execute("""
            INSERT INTO outreach_log
              (lead_id, email_to, email_subject, email_body, mockup_url, sent_at, status, resend_message_id)
            VALUES (%s, %s, %s, %s, %s, NOW(), 'sent', %s)
            RETURNING id
        """, (lead_id, email, subj, body, mockup or "", result.get("message_id")))
        cur.execute("UPDATE leads SET status='sent' WHERE id=%s", (lead_id,))
        conn.commit()
        cur.close(); conn.close()
    return result

def approve_lead(lead_id):
    conn = db_conn(); cur = conn.cursor()
    cur.execute("UPDATE leads SET status='approved' WHERE id=%s", (lead_id,))
    conn.commit(); cur.close(); conn.close()
    return {"success": True, "lead_id": lead_id, "status": "approved"}

def reject_lead(lead_id):
    conn = db_conn(); cur = conn.cursor()
    cur.execute("UPDATE leads SET status='rejected' WHERE id=%s", (lead_id,))
    conn.commit(); cur.close(); conn.close()
    return {"success": True, "lead_id": lead_id, "status": "rejected"}

def get_lead_detail(lead_id):
    """Get full details of one lead."""
    conn = db_conn(); cur = conn.cursor()
    cur.execute("""
        SELECT l.id, l.business_name, l.niche, l.city, l.country, l.phone, l.address,
               l.ai_score, l.score_reason, l.status, l.created_at,
               COALESCE(l.google_rating, 0), COALESCE(l.review_count, 0),
               c.full_name, c.email, c.email_status, c.linkedin_url, c.job_title,
               (SELECT content FROM assets WHERE lead_id=l.id AND asset_type='mockup_image' LIMIT 1) as mockup,
               (SELECT content FROM assets WHERE lead_id=l.id AND asset_type='email_subject' LIMIT 1) as subj,
               (SELECT content FROM assets WHERE lead_id=l.id AND asset_type='email_body' LIMIT 1) as body
        FROM leads l
        LEFT JOIN LATERAL (
            SELECT full_name, email, email_status, linkedin_url, job_title FROM contacts
            WHERE lead_id = l.id
            ORDER BY (COALESCE(email,'') != '') DESC, confidence DESC NULLS LAST, created_at DESC
            LIMIT 1
        ) c ON TRUE
        WHERE l.id = %s
    """, (lead_id,))
    r = cur.fetchone()
    cur.close(); conn.close()
    if not r:
        return None
    return {
        "id": str(r[0]),
        "business_name": r[1], "niche": r[2], "city": r[3], "country": r[4],
        "phone": r[5], "address": r[6],
        "ai_score": r[7], "score_reason": r[8], "status": r[9],
        "created_at": r[10].isoformat() if r[10] else None,
        "google_rating": float(r[11]) if r[11] else 0, "review_count": r[12],
        "owner_name": r[13] or "", "owner_email": r[14] or "",
        "email_status": r[15] or "",
        "linkedin_url": r[16] or "", "job_title": r[17] or "",
        "mockup_url": r[18] or "", "email_subject": r[19] or "", "email_body": r[20] or ""
    }

def regenerate_email_for_lead(lead_id, extra_instructions=""):
    """Regenerate email copy with Claude for a specific lead."""
    detail = get_lead_detail(lead_id)
    if not detail: return {"success": False, "error": "Lead not found"}

    prompt_suffix = f"\\n\\nExtra instructions: {extra_instructions}" if extra_instructions else ""
    email = generate_email_copy(
        detail["business_name"],
        detail["niche"],
        detail["city"],
        detail["owner_name"]
    )

    if not email:
        if not CONFIG.get('auto_email_copy', True):
            return {"success": False, "error": "Claude email generation is OFF. Enable it in Settings > Pipeline Automation."}
        if not CLAUDE_KEY:
            return {"success": False, "error": "No Claude API key configured. Add one in Settings > API Keys."}
        return {"success": False, "error": "Claude generation failed"}

    conn = db_conn(); cur = conn.cursor()
    # Delete old email copy
    cur.execute("DELETE FROM assets WHERE lead_id=%s AND asset_type IN ('email_subject', 'email_body')", (lead_id,))
    cur.execute("INSERT INTO assets(lead_id, asset_type, content, model_used) VALUES(%s, 'email_subject', %s, 'claude')",
               (lead_id, email.get("subject", "")))
    cur.execute("INSERT INTO assets(lead_id, asset_type, content, model_used) VALUES(%s, 'email_body', %s, 'claude')",
               (lead_id, email.get("body", "")))
    conn.commit(); cur.close(); conn.close()
    return {"success": True, "subject": email.get("subject"), "body": email.get("body")}

def get_outreach_log(limit=100):
    conn = db_conn(); cur = conn.cursor()
    cur.execute("""
        SELECT o.id, o.lead_id, l.business_name, o.email_to, o.email_subject,
               o.sent_at, o.opened_at, o.replied_at, o.status, o.resend_message_id
        FROM outreach_log o LEFT JOIN leads l ON l.id = o.lead_id
        ORDER BY o.sent_at DESC NULLS LAST LIMIT %s
    """, (limit,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [{
        "id": str(r[0]), "lead_id": str(r[1]), "business_name": r[2],
        "email_to": r[3], "email_subject": r[4],
        "sent_at": r[5].isoformat() if r[5] else None,
        "opened_at": r[6].isoformat() if r[6] else None,
        "replied_at": r[7].isoformat() if r[7] else None,
        "status": r[8], "message_id": r[9]
    } for r in rows]

def get_chart_stats():
    """Time-series data for charts."""
    try:
        conn = db_conn(); cur = conn.cursor()

        # Leads per day for the last 14 days
        cur.execute("""
            SELECT DATE(created_at) as d, COUNT(*) as c
            FROM leads
            WHERE created_at > NOW() - INTERVAL '14 days' AND lead_type IS NULL
            GROUP BY DATE(created_at) ORDER BY d
        """)
        leads_per_day = [{"date": str(r[0]), "count": r[1]} for r in cur.fetchall()]

        # Status breakdown
        cur.execute("SELECT status, COUNT(*) FROM leads WHERE lead_type IS NULL GROUP BY status")
        status_breakdown = [{"status": r[0], "count": r[1]} for r in cur.fetchall()]

        # Niche breakdown
        cur.execute("SELECT niche, COUNT(*) FROM leads WHERE lead_type IS NULL GROUP BY niche ORDER BY 2 DESC LIMIT 10")
        niche_breakdown = [{"niche": r[0], "count": r[1]} for r in cur.fetchall()]

        # City breakdown
        cur.execute("SELECT city, COUNT(*) FROM leads WHERE lead_type IS NULL GROUP BY city ORDER BY 2 DESC LIMIT 10")
        city_breakdown = [{"city": r[0], "count": r[1]} for r in cur.fetchall()]

        # Score distribution
        cur.execute("""
            SELECT
              CASE
                WHEN ai_score IS NULL THEN 'Unscored'
                WHEN ai_score >= 8 THEN 'Excellent (8-10)'
                WHEN ai_score >= 5 THEN 'Good (5-7)'
                ELSE 'Low (1-4)'
              END as bucket,
              COUNT(*) as c
            FROM leads WHERE lead_type IS NULL GROUP BY bucket
        """)
        score_distribution = [{"bucket": r[0], "count": r[1]} for r in cur.fetchall()]

        cur.close(); conn.close()
        return {
            "leads_per_day": leads_per_day,
            "status_breakdown": status_breakdown,
            "niche_breakdown": niche_breakdown,
            "city_breakdown": city_breakdown,
            "score_distribution": score_distribution
        }
    except Exception as e:
        return {
            "leads_per_day": [],
            "status_breakdown": [],
            "niche_breakdown": [],
            "city_breakdown": [],
            "score_distribution": []
        }


# ──────────────────────────────────────────────────────────────
#  HTTP HANDLERS
# ──────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    # Paths reachable without a login token. Everything else requires auth.
    PUBLIC_GET_PATHS = {'/', '/dashboard', '/index.html', '/health'}
    PUBLIC_GET_PREFIXES = ('/assets/', '/mockups/', '/u/')
    PUBLIC_POST_PATHS = {'/auth/login', '/auth/check', '/webhook/resend'}

    def check_auth(self):
        """Authenticate the request. Returns (tenant_id, user_id) for valid
        sessions and (None, None) when unauthenticated. Accepts the token via
        the Authorization header or a ?token= query parameter (CSV downloads)."""
        auth_header = self.headers.get('Authorization')
        token = ''
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ', 1)[1].strip()
        if not token:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            token = (qs.get('token') or [''])[0]
        user = auth_check(token)
        if not user:
            return None, None
        # Single-tenant deployment: authenticated users share the default tenant.
        return '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000002'

    def require_auth(self):
        """Enforce auth for non-public paths. Returns False after sending a 401."""
        p = self.path.split('?')[0]
        if self.command == 'GET':
            if p in self.PUBLIC_GET_PATHS or p.startswith(self.PUBLIC_GET_PREFIXES):
                return True
        elif self.command == 'POST' and p in self.PUBLIC_POST_PATHS:
            return True
        tenant_id, _ = self.check_auth()
        if tenant_id:
            return True
        self.send_json(401, {'error': 'Unauthorized — log in first'})
        return False

    def send_json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS,PUT,DELETE')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS,PUT,DELETE')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        self.end_headers()

    def send_html(self, html):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def do_GET(self):
        p = self.path.split('?')[0]
        if not self.require_auth():
            return
        if p == '/' or p == '/dashboard' or p == '/index.html':
            try:
                # Try to serve Vite built frontend, fallback to old dashboard.html
                dist_index = os.path.join(LEADGEN_HOME, 'frontend', 'dist', 'index.html')
                if os.path.exists(dist_index):
                    with open(dist_index, 'r', encoding='utf-8') as f:
                        html = f.read()
                else:
                    with open(os.path.join(LEADGEN_HOME, 'dashboard.html'), 'r', encoding='utf-8') as f:
                        html = f.read()
                self.send_html(html)
            except Exception as e:
                self.send_json(500, {'error': str(e)})
        elif p.startswith('/assets/'):
            try:
                filename = p[8:]
                if '..' in filename or '/' in filename:
                    self.send_json(404, {'error': 'not found'})
                    return
                filepath = os.path.join(LEADGEN_HOME, 'frontend', 'dist', 'assets', filename)
                if not os.path.exists(filepath):
                    self.send_json(404, {'error': 'not found'})
                    return
                with open(filepath, 'rb') as f:
                    data = f.read()
                self.send_response(200)
                ext = filename.split('.')[-1].lower()
                ctype = 'application/javascript' if ext == 'js' else 'text/css' if ext == 'css' else 'image/svg+xml' if ext == 'svg' else 'application/octet-stream'
                self.send_header('Content-Type', ctype)
                self.send_header('Cache-Control', 'public, max-age=31536000')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.send_json(500, {'error': str(e)})
        elif p in ('/leads', '/leads.json'):
            try:
                tenant_id, user_id = self.check_auth()
                if not tenant_id:
                    self.send_json(401, {'error': 'Unauthorized'})
                    return
                cols, rows = get_leads()
                self.send_json(200, {'status': 'ok', 'total': len(rows), 'columns': cols, 'leads': rows})
            except Exception as e:
                self.send_json(500, {'error': str(e)})
        elif p == '/leads.csv':
            try:
                tenant_id, user_id = self.check_auth()
                if not tenant_id:
                    self.send_json(401, {'error': 'Unauthorized'})
                    return
                cols, rows = get_leads()
                buf = io.StringIO()
                w = csv.DictWriter(buf, fieldnames=cols)
                w.writeheader()
                for r in rows: w.writerow(r)
                csv_data = buf.getvalue().encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/csv; charset=utf-8')
                self.send_header('Content-Disposition', 'attachment; filename="leadgen_leads.csv"')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(csv_data)
            except Exception as e:
                self.send_json(500, {'error': str(e)})
        elif p == '/config':
            self.send_json(200, CONFIG)
        elif p == '/health':
            self.send_json(200, {
                'status': 'ok', 'version': '5.0',
                'modules': ['discover', 'enrich', 'score', 'assets', 'seo', 'competitor', 'ecommerce'],
                'providers': {
                    'serper': bool(SERPER_KEY),
                    'oxylabs': bool(OXYLABS),
                    'gemini': bool(GEMINI_KEY),
                    'claude': bool(CLAUDE_KEY),
                    'replicate': bool(REPLICATE_TOKEN),
                    'imagine_art': bool(IMAGINE_ART_KEY)
                }
            })

        elif p.startswith('/u/'):
            # Public unsubscribe link: /u/<token>
            try:
                token = p[3:].split('?')[0]
                self.send_html(handle_unsubscribe(token))
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p.startswith('/mockups/'):
            try:
                filename = p[9:]
                # Security: prevent path traversal
                if '..' in filename or '/' in filename:
                    self.send_json(404, {'error': 'not found'})
                    return
                filepath = os.path.join(LEADGEN_HOME, 'mockups', filename)
                if not os.path.exists(filepath):
                    self.send_json(404, {'error': 'not found'})
                    return
                with open(filepath, 'rb') as f:
                    data = f.read()
                self.send_response(200)
                ext = filename.split('.')[-1].lower()
                ctype = 'image/jpeg' if ext in ('jpg','jpeg') else 'image/png' if ext == 'png' else 'image/webp' if ext == 'webp' else 'application/octet-stream'
                self.send_header('Content-Type', ctype)
                self.send_header('Cache-Control', 'public, max-age=86400')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(data)
                return
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/api-keys':
            try:
                self.send_json(200, get_api_keys_masked())
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p.startswith('/job/'):
            self.send_json(200, JOBS.get(p[5:], {'status': 'not_found'}))
        elif p == '/sequences':
            try:
                conn = db_conn(); cur = conn.cursor()
                cur.execute("""SELECT q.id, q.name, q.is_active,
                               (SELECT COUNT(*) FROM sequence_steps WHERE sequence_id=q.id),
                               (SELECT COUNT(*) FROM enrollments WHERE sequence_id=q.id AND status='active')
                               FROM sequences q ORDER BY q.id""")
                seqs = [{'id': r[0], 'name': r[1], 'is_active': r[2],
                         'steps': r[3], 'active_enrollments': r[4]} for r in cur.fetchall()]
                cur.execute("""SELECT e.id, e.lead_id::text, l.business_name, e.current_step,
                                      e.status, e.steps_sent, to_char(e.next_send_at,'YYYY-MM-DD HH24:MI'),
                                      e.stop_reason
                               FROM enrollments e JOIN leads l ON l.id=e.lead_id
                               WHERE e.status IN ('active','completed') OR e.updated_at > NOW() - INTERVAL '7 days'
                               ORDER BY e.status='active' DESC, e.updated_at DESC LIMIT 50""")
                enrls = [{'id': r[0], 'lead_id': r[1], 'business': r[2], 'step': r[3],
                          'status': r[4], 'steps_sent': r[5], 'next_send': r[6], 'stop_reason': r[7]}
                         for r in cur.fetchall()]
                cur.close(); conn.close()
                self.send_json(200, {'sequences': seqs, 'enrollments': enrls,
                                     'enabled': bool(CONFIG.get('sequences_enabled', True))})
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/cost-stats':
            try:
                conn = db_conn(); cur = conn.cursor()
                cur.execute("""SELECT provider, SUM(cost),
                               SUM(cost) FILTER (WHERE created_at > NOW() - INTERVAL '24 hours') as today
                               FROM api_usage WHERE created_at > NOW() - INTERVAL '30 days'
                               GROUP BY provider ORDER BY SUM(cost) DESC""")
                by_provider = [{'provider': r[0], 'month': float(r[1] or 0), 'today': float(r[2] or 0)}
                               for r in cur.fetchall()]
                cur.execute("SELECT COALESCE(SUM(cost),0) FROM api_usage WHERE created_at > NOW() - INTERVAL '24 hours'")
                today = float(cur.fetchone()[0])
                cur.execute("SELECT COALESCE(SUM(cost),0) FROM api_usage WHERE created_at >= date_trunc('month', NOW())")
                month = float(cur.fetchone()[0])
                cur.execute("SELECT COUNT(*) FROM leads WHERE lead_type IS NULL")
                nleads = cur.fetchone()[0]
                cur.close(); conn.close()
                budget = float(CONFIG.get('cost_budget_monthly', 50))
                self.send_json(200, {
                    'today': round(today, 4), 'month': round(month, 4),
                    'by_provider': by_provider,
                    'cost_per_lead': round(month / nleads, 4) if nleads else 0,
                    'budget': budget,
                    'budget_pct': int(month / budget * 100) if budget else 0,
                    'budget_warning': month >= budget * 0.8,
                })
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/stats':
            try:
                conn = db_conn(); cur = conn.cursor()
                cur.execute("""
                    SELECT
                      COUNT(*) FILTER (WHERE has_website = FALSE) as hot_leads,
                      COUNT(*) as total,
                      COUNT(*) FILTER (WHERE status = 'discovered') as discovered,
                      COUNT(*) FILTER (WHERE status = 'enriched') as enriched,
                      COUNT(*) FILTER (WHERE status = 'scored') as scored,
                      COUNT(*) FILTER (WHERE status = 'ready') as ready,
                      COUNT(*) FILTER (WHERE status = 'sent') as sent,
                      COUNT(*) FILTER (WHERE ai_score >= 7) as high_score
                    FROM leads
                    WHERE lead_type IS NULL
                """)
                row = cur.fetchone()
                cur.execute("""
                    SELECT COUNT(*) FROM contacts c
                    JOIN leads l ON l.id = c.lead_id
                    WHERE c.email != '' AND l.lead_type IS NULL
                """)
                with_email = cur.fetchone()[0]
                cur.execute("SELECT COUNT(DISTINCT city) FROM leads WHERE lead_type IS NULL")
                cities = cur.fetchone()[0]
                # Leads that went through enrichment but still have no email or LinkedIn
                cur.execute("""
                    SELECT COUNT(l.id) FROM leads l
                    LEFT JOIN contacts c ON c.lead_id = l.id
                    WHERE l.lead_type IS NULL
                      AND l.status NOT IN ('discovered', 'rejected')
                      AND (c.id IS NULL OR (COALESCE(c.email,'') = '' AND COALESCE(c.linkedin_url,'') = ''))
                """)
                enriched_no_contact = cur.fetchone()[0]
                # Email verification summary — feeds the Pipeline page card
                cur.execute("""
                    SELECT
                      COUNT(*) FILTER (WHERE email_status = 'deliverable'),
                      COUNT(*) FILTER (WHERE email_status = 'risky'),
                      COUNT(*) FILTER (WHERE email_status = 'undeliverable'),
                      COUNT(*) FILTER (WHERE email_status IS NULL OR email_status = 'unknown'),
                      COUNT(*) FILTER (WHERE email_status = 'deliverable'
                                       AND email_checked_at < NOW() - INTERVAL '60 days')
                    FROM contacts
                    WHERE COALESCE(email,'') != ''
                """)
                v = cur.fetchone()
                cur.close(); conn.close()
                self.send_json(200, {
                    'hot_leads': row[0], 'total': row[1], 'discovered': row[2],
                    'enriched': row[3], 'scored': row[4], 'ready': row[5],
                    'sent': row[6], 'high_score': row[7],
                    'with_email': with_email, 'cities': cities,
                    'enriched_no_contact': enriched_no_contact,
                    'email_verification': {
                        'deliverable': v[0], 'risky': v[1],
                        'undeliverable': v[2], 'unknown': v[3],
                        'stale': v[4],
                        'sendable': v[0] + v[1],
                    }
                })
            except Exception as e:
                self.send_json(200, {
                    'hot_leads': 0, 'total': 0, 'discovered': 0,
                    'enriched': 0, 'scored': 0, 'ready': 0,
                    'sent': 0, 'high_score': 0,
                    'with_email': 0, 'cities': 0,
                    'enriched_no_contact': 0,
                    'email_verification': {'deliverable': 0, 'risky': 0,
                                           'undeliverable': 0, 'unknown': 0,
                                           'stale': 0, 'sendable': 0}
                })

        elif p == '/intent-leads':
            try:
                q = urllib.parse.urlparse(self.path).query
                qs = urllib.parse.parse_qs(q)
                direction = (qs.get('direction', [None])[0])
                qf = qs.get('q', [''])[0]
                limit = int(qs.get('limit', ['100'])[0])
                min_conf = int(qs.get('min_confidence', ['0'])[0])
                rows = get_intent_leads(direction=direction, query_filter=qf, min_confidence=min_conf, limit=limit)
                self.send_json(200, {'total': len(rows), 'leads': rows})
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/intent-leads.csv':
            try:
                q = urllib.parse.urlparse(self.path).query
                qs = urllib.parse.parse_qs(q)
                direction = (qs.get('direction', [None])[0])
                min_conf = int(qs.get('min_confidence', ['0'])[0])
                rows = get_intent_leads(direction=direction, min_confidence=min_conf, limit=1000)
                csv_data = intent_leads_to_csv(rows)
                self.send_response(200)
                self.send_header('Content-Type', 'text/csv; charset=utf-8')
                self.send_header('Content-Disposition', 'attachment; filename="intent_leads.csv"')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(csv_data)
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/intent-stats':
            try:
                self.send_json(200, get_intent_stats())
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/batches':
            try:
                self.send_json(200, {'batches': get_search_batches()})
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p.startswith('/lead/'):
            try:
                lead_id = p.split('/')[2]
                detail = get_lead_detail(lead_id)
                if detail:
                    self.send_json(200, detail)
                else:
                    self.send_json(404, {'error': 'Lead not found'})
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/outreach':
            try:
                self.send_json(200, {'total': 0, 'log': get_outreach_log(100)})
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/stats-chart':
            try:
                self.send_json(200, get_chart_stats())
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p.startswith('/research-history/') and p.endswith('/csv'):
            try:
                entry_id = int(p.split('/')[2])
                result = get_research_history_entry(entry_id)
                if not result:
                    self.send_json(404, {'error': 'not found'})
                    return
                csv_data = research_result_to_csv(result)
                self.send_response(200)
                self.send_header('Content-Type', 'text/csv; charset=utf-8')
                self.send_header('Content-Disposition', f'attachment; filename="product_hunt_{entry_id}.csv"')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(csv_data)
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p.startswith('/research-history/'):
            try:
                entry_id = int(p.split('/')[2])
                result = get_research_history_entry(entry_id)
                if result:
                    result['cached'] = True
                    result['history_id'] = entry_id
                    self.send_json(200, result)
                else:
                    self.send_json(404, {'error': 'not found'})
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        else:
            self.send_json(404, {'error': 'not found'})

    def do_POST(self):
        p = self.path.split('?')[0]
        # Read the raw body once — the webhook route needs the exact bytes
        # for signature verification; everyone else gets the parsed dict.
        raw_body = b''
        try:
            length = int(self.headers.get('Content-Length', 0))
            raw_body = self.rfile.read(length) if length else b''
            body = json.loads(raw_body.decode()) if length else {}
        except:
            body = {}

        if p == '/webhook/resend':
            try:
                result = handle_resend_webhook(self.headers, raw_body)
                self.send_json(result.get('status', 200),
                               {'ok': result.get('ok'), **{k: v for k, v in result.items() if k != 'ok'}})
            except Exception as e:
                self.send_json(500, {'error': str(e)})
            return

        if not self.require_auth():
            return

        if p == '/auth/login':
            try:
                username = str(body.get('username') or body.get('email') or '').strip().lower()
                # The React login posts emails — map the known admin aliases to 'admin'
                if '@' in username:
                    username = 'admin' if username in ('admin@controva.com', 'admin@controvallc.com') else username
                password = str(body.get('password') or '')
                ip = self.client_address[0] if self.client_address else ''

                remaining_lock = auth_is_locked(username, ip)
                if remaining_lock:
                    self.send_json(429, {'success': False,
                                         'error': f'Too many failed attempts. Try again in {remaining_lock // 60 + 1} minutes.'})
                    return
                tok = auth_login(username, password, ip)
                if tok:
                    self.send_json(200, {'success': True, 'status': 'ok', 'token': tok,
                                         'user': {'email': username, 'role': 'admin'}})
                else:
                    left = AUTH_MAX_FAILURES - len(_login_failures.get(auth_lock_key(username, ip), []))
                    self.send_json(401, {'success': False,
                                         'error': f'Invalid credentials. {max(left, 0)} attempt(s) remaining before temporary lockout.'})
            except Exception as e:
                self.send_json(500, {'success': False, 'error': str(e)})
            return

        elif p == '/auth/change-password':
            try:
                auth_header = self.headers.get('Authorization', '')
                token = auth_header[7:] if auth_header.startswith('Bearer ') else ''
                user = auth_check(token)
                if not user or user == 'service':
                    self.send_json(401, {'success': False, 'error': 'Not authenticated'})
                    return
                ok, msg = auth_change_password(user, str(body.get('old_password') or ''),
                                               str(body.get('new_password') or ''))
                self.send_json(200 if ok else 400, {'success': ok, 'message': msg})
            except Exception as e:
                self.send_json(500, {'success': False, 'error': str(e)})
            return

        elif p == '/auth/logout':
            try:
                auth_header = self.headers.get('Authorization', '')
                token = auth_header[7:] if auth_header.startswith('Bearer ') else ''
                auth_logout(token)
                self.send_json(200, {'success': True})
            except Exception as e:
                self.send_json(500, {'error': str(e)})
            return

        elif p == '/auth/check':
            try:
                token = body.get('token', '')
                user = auth_check(token)
                self.send_json(200, {'authenticated': bool(user), 'valid': bool(user),
                                     'user': user if user else None})
            except Exception as e:
                self.send_json(500, {'error': str(e)})
            return

        if p == '/search':
            # Free-text natural language search → background discovery job
            try:
                tenant_id, user_id = self.check_auth()
                if not tenant_id:
                    self.send_json(401, {'error': 'Unauthorized'})
                    return
                    
                query = body.get('query', '')
                if not query:
                    self.send_json(400, {'error': 'query required'})
                    return
                filter_mode = body.get('filter_mode', 'no_website')  # no_website | with_website | all
                density = body.get('density', 'standard')  # low | standard | high
                find_more = bool(body.get('find_more', False))
                parsed = parse_search_query(query)
                if not parsed:
                    self.send_json(500, {'error': 'failed to parse query'})
                    return
                if parsed.get('_parse_failed') or not parsed.get('city'):
                    self.send_json(200, {
                        'error': 'Could not work out the location from your search. '
                                 'Try the format "<business type> in <city>", '
                                 'e.g. "pest control in Newark USA".',
                        'parsed': parsed})
                    return
                state_cities = parsed.get('_state_cities')
                where = parsed.get('city')
                if state_cities and len(state_cities) > 1:
                    where = f'{len(state_cities)} cities across {parsed.get("_state_search") or parsed.get("city")}'
                job_id = f'job_{int(time.time() * 1000)}'
                JOBS[job_id] = {'status': 'running', 'progress': 0,
                                'log': [f'Parsing "{query}" → {parsed.get("niche")} in {where}'],
                                'step': 'Discover'}
                t = threading.Thread(target=run_discover_bg, args=(
                    job_id, parsed['niche'], parsed['city'], parsed.get('country', ''),
                    filter_mode, density, find_more, query, state_cities, tenant_id, user_id))
                t.daemon = True; t.start()
                self.send_json(200, {'job_id': job_id, 'status': 'started',
                                     'parsed': parsed, 'find_more': find_more})
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/intent-search':
            try:
                query = (body.get('query') or '').strip()
                direction = body.get('direction', 'demand')
                location = (body.get('location') or '').strip()
                recency_days = int(body.get('recency_days') or 30)
                min_confidence = int(body.get('min_confidence') or 55)
                per_source_limit = int(body.get('per_source_limit') or 3)
                max_results = int(body.get('max_results') or 30)
                if not query:
                    self.send_json(400, {'error': 'query required'})
                    return
                if direction not in ('demand', 'supply'):
                    self.send_json(400, {'error': 'direction must be demand or supply'})
                    return
                results, status = intent_search(
                    query, direction=direction, location=location,
                    recency_days=recency_days, min_confidence=min_confidence,
                    per_source_limit=per_source_limit, max_results=max_results
                )
                self.send_json(200, {
                    'status': status, 'direction': direction, 'query': query,
                    'total': len(results), 'results': results,
                    'message': f'Found {len(results)} {direction} signals for "{query}"' if status == 'success'
                              else 'Cached results — re-query in 12h for fresh data'
                })
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p.startswith('/intent-leads/') and p.endswith('/delete'):
            try:
                lead_id = p.split('/')[2]
                deleted = delete_intent_lead(lead_id)
                self.send_json(200, {'success': deleted})
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p.startswith('/job/') and p.endswith('/cancel'):
            job_id = p[5:-7]
            if job_id in JOBS:
                JOBS[job_id]['cancelled'] = True
                JOBS[job_id]['status'] = 'cancelled'
                self.send_json(200, {'ok': True})
            else:
                self.send_json(404, {'error': 'job not found'})

        elif p == '/discover':
            try:
                niche = body.get('niche', 'restaurant')
                city = body.get('city', 'Dubai')
                country = body.get('country', '')
                filter_mode = body.get('filter_mode', 'no_website')
                density = body.get('density', 'standard')
                find_more = bool(body.get('find_more', False))
                # If a US state was passed as the city, redirect + enable sweep
                fixed = _fix_state_as_city({'city': city, 'country': country})
                city = fixed.get('city', city)
                country = fixed.get('country', country)
                state_cities = fixed.get('_state_cities')
                job_id = f'job_{int(time.time() * 1000)}'
                JOBS[job_id] = {'status': 'running', 'progress': 0,
                                'log': [f'Discovering "{niche}" in {city}…'], 'step': 'Discover'}
                t = threading.Thread(target=run_discover_bg, args=(
                    job_id, niche, city, country, filter_mode, density, find_more, '', state_cities))
                t.daemon = True; t.start()
                self.send_json(200, {'job_id': job_id, 'status': 'started'})
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/enrich':
            try:
                strategy = body.get('provider', 'serper_then_oxylabs')
                job_id = f'job_{int(time.time())}'
                JOBS[job_id] = {'status': 'running', 'progress': 0, 'log': ['Checking which leads need enriching...'], 'step': 'Enrich'}
                t = threading.Thread(target=run_enrich_bg, args=(job_id, strategy))
                t.daemon = True; t.start()
                self.send_json(200, {'job_id': job_id, 'status': 'started'})
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/enrich-company':
            try:
                company = (body.get('company_name') or '').strip()
                if not company:
                    self.send_json(400, {'error': 'company_name required'}); return
                city     = (body.get('city') or '').strip()
                niche    = (body.get('niche') or '').strip()
                website  = (body.get('website') or '').strip()
                strategy = body.get('strategy', 'free_first')
                result = enrich_single_company(company, city, niche, website, strategy)
                self.send_json(200, result)
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/enrich-csv':
            # Accepts JSON body: {rows: [{company_name, city, niche},...], strategy}
            # OR raw CSV text in body.csv_text
            try:
                strategy = body.get('strategy', 'free_first')
                rows = body.get('rows')
                if not rows:
                    csv_text = body.get('csv_text', '')
                    if not csv_text:
                        self.send_json(400, {'error': 'rows or csv_text required'}); return
                    reader = csv.DictReader(io.StringIO(csv_text))
                    rows = list(reader)
                if not rows:
                    self.send_json(400, {'error': 'no rows in CSV'}); return
                job_id = f'job_{int(time.time() * 1000)}'
                JOBS[job_id] = {'status': 'running', 'progress': 0,
                                'log': [], 'step': 'CSV Enrich'}
                t = threading.Thread(target=run_csv_enrich_bg, args=(job_id, rows, strategy))
                t.daemon = True; t.start()
                self.send_json(200, {'job_id': job_id, 'total': len(rows)})
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/verify-websites':
            try:
                lead_ids = body.get('lead_ids') or []  # empty = all unverified
                job_id = f'job_{int(time.time())}'
                JOBS[job_id] = {'status': 'running', 'progress': 0,
                                'log': ['Starting website verification…'], 'step': 'Verify Websites'}
                t = threading.Thread(target=run_verify_websites_bg, args=(job_id, lead_ids))
                t.daemon = True; t.start()
                self.send_json(200, {'job_id': job_id, 'status': 'started'})
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/sequence/enroll':
            try:
                lead_ids = body.get('lead_ids') or ([body['lead_id']] if body.get('lead_id') else [])
                results = []
                for lid in lead_ids[:50]:
                    r = enroll_lead_in_default(lid)
                    r['lead_id'] = lid
                    results.append(r)
                ok_count = sum(1 for r in results if r.get('success'))
                self.send_json(200, {'success': ok_count > 0,
                                     'enrolled': ok_count,
                                     'already': sum(1 for r in results if r.get('error') == 'already enrolled'),
                                     'results': results})
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/sequence/stop':
            try:
                lead_id = body.get('lead_id', '')
                stop_enrollment(lead_id, 'stopped', 'stopped manually')
                self.send_json(200, {'success': True})
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/sequence/run':
            try:
                process_due_enrollments()
                self.send_json(200, {'success': True, 'message': 'scheduler pass complete'})
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/check-replies':
            try:
                job_id = f'job_{int(time.time() * 1000)}'
                t = threading.Thread(target=run_check_replies_bg, args=(job_id,))
                t.daemon = True; t.start()
                self.send_json(200, {'job_id': job_id, 'status': 'started'})
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/verify-emails':
            try:
                only_stale = bool(body.get('only_stale', False))
                job_id = f'job_{int(time.time() * 1000)}'
                t = threading.Thread(target=run_verify_emails_bg, args=(job_id, only_stale))
                t.daemon = True; t.start()
                self.send_json(200, {'job_id': job_id, 'status': 'started'})
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/reenrich-missing-emails':
            try:
                strategy = body.get('provider_strategy', 'oxylabs_only')
                job_id = f'job_{int(time.time() * 1000)}'
                t = threading.Thread(target=run_reenrich_bg, args=(job_id, strategy))
                t.daemon = True; t.start()
                self.send_json(200, {'job_id': job_id, 'status': 'started'})
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/score':
            try:
                job_id = f'job_{int(time.time())}'
                JOBS[job_id] = {'status': 'running', 'progress': 0, 'log': ['Starting: AI score leads...'], 'step': 'AI Score'}
                t = threading.Thread(target=run_step_bg, args=(job_id, score_all_enriched, 'AI score leads'))
                t.daemon = True; t.start()
                self.send_json(200, {'job_id': job_id, 'status': 'started'})
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/generate-assets':
            try:
                img_prov = body.get('image_provider', 'none')
                CONFIG['image_provider'] = img_prov
                min_score = body.get('min_score', 5)
                job_id = f'job_{int(time.time())}'
                JOBS[job_id] = {'status': 'running', 'progress': 0, 'log': ['Starting: Generate email copy & assets...'], 'step': 'Generate Assets'}
                t = threading.Thread(target=run_step_bg, args=(job_id, generate_assets_for_top_leads, 'Generate email copy & assets', min_score))
                t.daemon = True; t.start()
                self.send_json(200, {'job_id': job_id, 'status': 'started'})
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/keywords':
            try:
                seed = body.get('keyword', '')
                location = body.get('location', '')
                if not seed:
                    self.send_json(400, {'error': 'keyword required'})
                    return
                result = keyword_research(seed, location)
                self.send_json(200, result)
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/serp':
            try:
                kw = body.get('keyword', '')
                loc = body.get('location', '')
                if not kw:
                    self.send_json(400, {'error': 'keyword required'})
                    return
                result = serp_analysis(kw, loc)
                self.send_json(200, result)
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/competitor':
            try:
                target = body.get('target', '')
                if not target:
                    self.send_json(400, {'error': 'target (domain or company name) required'})
                    return
                result = competitor_intel(target)
                self.send_json(200, result)
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/ecommerce':
            try:
                q       = body.get('query', '').strip()
                country = body.get('country', 'us').lower()
                force   = bool(body.get('force'))
                if not q:
                    self.send_json(400, {'error': 'query required'})
                    return
                if country not in MARKET_CONFIG:
                    country = 'us'
                ckey = {'q': q.lower(), 'country': country}
                if not force:
                    cached = get_cached_research('ecommerce', ckey, max_age_hours=24)
                    if cached:
                        cached['cached'] = True
                        self.send_json(200, cached)
                        return
                result = ecommerce_research(q, country)
                result['cached'] = False
                result['history_id'] = save_research_history('ecommerce', q, country, result)
                save_cached_research('ecommerce', ckey, result)
                self.send_json(200, result)
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/product-hunt':
            try:
                category = body.get('category', '').strip()
                country  = body.get('country', 'us').lower()
                cnt      = body.get('count', 8)
                force    = bool(body.get('force'))
                if not category:
                    self.send_json(400, {'error': 'category required'})
                    return
                if country not in MARKET_CONFIG:
                    country = 'us'
                ckey = {'cat': category.lower(), 'country': country, 'n': cnt}
                if not force:
                    cached = get_cached_research('product_hunt', ckey, max_age_hours=12)
                    if cached:
                        cached['cached'] = True
                        self.send_json(200, cached)
                        return
                result = product_hunt(category, country, cnt)
                result['cached'] = False
                result['history_id'] = save_research_history('product_hunt', category, country, result)
                save_cached_research('product_hunt', ckey, result)
                self.send_json(200, result)
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/research-history/list':
            try:
                run_type = body.get('run_type', 'product_hunt')
                limit = int(body.get('limit', 30))
                self.send_json(200, {'history': list_research_history(run_type, limit)})
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p.startswith('/research-history/') and p.endswith('/delete'):
            try:
                entry_id = int(p.split('/')[2])
                deleted = delete_research_history_entry(entry_id)
                self.send_json(200, {'success': deleted})
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/config':
            try:
                for k, v in body.items():
                    if k in CONFIG: CONFIG[k] = v
                save_config()  # Persist to disk
                self.send_json(200, CONFIG)
            except Exception as e:
                self.send_json(500, {'error': str(e)})


        elif p == '/api-keys/update':
            try:
                key_name = body.get('key', '')
                key_value = body.get('value', '')
                if not key_name:
                    self.send_json(400, {'error': 'key required'})
                    return
                ok = update_api_key(key_name, key_value)
                if ok:
                    self.send_json(200, {'success': True, 'message': f'{key_name} updated'})
                else:
                    self.send_json(400, {'success': False, 'error': 'Invalid key name'})
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/run-pipeline':
            try:
                strategy = body.get('provider', 'serper_then_oxylabs')
                gen_images = body.get('generate_images', False)
                job_id = f'job_{int(time.time())}'
                t = threading.Thread(target=run_pipeline_bg, args=(job_id, strategy, gen_images))
                t.daemon = True; t.start()
                self.send_json(200, {'job_id': job_id, 'status': 'started'})
            except Exception as e:
                self.send_json(500, {'error': str(e)})


        elif p == '/find-emails':
            try:
                business = body.get('business_name', '')
                domain = body.get('domain', '')
                fn = body.get('first_name', '')
                ln = body.get('last_name', '')
                result = find_emails(business, domain, fn, ln)
                self.send_json(200, result)
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/find-people':
            try:
                company = body.get('company_name', '')
                titles = body.get('titles', None)
                location = body.get('location', '')
                if not company:
                    self.send_json(400, {'error': 'company_name required'})
                    return
                result = find_people(company, titles, location)
                self.send_json(200, result)
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/find-domain':
            try:
                business = body.get('business_name', '')
                if not business:
                    self.send_json(400, {'error': 'business_name required'})
                    return
                domain = guess_domain_from_business(business)
                self.send_json(200, {'business': business, 'guessed_domain': domain})
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/domain-intel':
            try:
                domain = body.get('domain', '')
                if not domain:
                    self.send_json(400, {'error': 'domain required'})
                    return
                result = domain_intel(domain)
                self.send_json(200, result)
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/wayback':
            try:
                url = body.get('url', '')
                limit = body.get('limit', 5)
                if not url:
                    self.send_json(400, {'error': 'url required'})
                    return
                result = wayback_snapshots(url, limit)
                self.send_json(200, result)
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/trends':
            try:
                kw = body.get('keyword', '')
                geo = body.get('geo', '')
                if not kw:
                    self.send_json(400, {'error': 'keyword required'})
                    return
                result = google_trends(kw, geo)
                self.send_json(200, result)
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/social-scout':
            try:
                niche = body.get('niche', '')
                location = body.get('location', '')
                platforms = body.get('platforms', None)
                if not niche:
                    self.send_json(400, {'error': 'niche required'})
                    return
                result = social_scout(niche, location, platforms)
                self.send_json(200, result)
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/verify-email':
            try:
                email = body.get('email', '')
                if not email:
                    self.send_json(400, {'error': 'email required'})
                    return
                result = verify_email(email)
                self.send_json(200, result)
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/backlinks':
            try:
                target = body.get('url', '')
                if not target:
                    self.send_json(400, {'error': 'url required'})
                    return
                result = find_backlinks(target)
                self.send_json(200, result)
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/tech-stack':
            try:
                domain = body.get('domain', '')
                if not domain:
                    self.send_json(400, {'error': 'domain required'})
                    return
                result = domain_intel(domain)
                self.send_json(200, {'domain': domain, 'tech_stack': result.get('tech_hints', []),
                                    'title': result.get('title', ''),
                                    'description': result.get('description', '')})
            except Exception as e:
                self.send_json(500, {'error': str(e)})


        elif p == '/auth/login':
            try:
                tok = auth_login(body.get('username',''), body.get('password',''))
                if tok:
                    self.send_json(200, {'success': True, 'token': tok})
                else:
                    self.send_json(401, {'success': False, 'error': 'Invalid credentials'})
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/auth/check':
            try:
                user = auth_check(body.get('token', ''))
                self.send_json(200, {'authenticated': bool(user), 'user': user or None})
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/send-email':
            try:
                result = send_email_via_resend(
                    body.get('to', ''),
                    body.get('subject', ''),
                    body.get('body', ''),
                    body.get('html', None)
                )
                self.send_json(200 if result.get('success') else 400, result)
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p.startswith('/lead/') and p.endswith('/send'):
            try:
                lead_id = p.split('/')[2]
                result = send_lead_email(lead_id)
                self.send_json(200 if result.get('success') else 400, result)
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p.startswith('/lead/') and p.endswith('/approve'):
            try:
                lead_id = p.split('/')[2]
                self.send_json(200, approve_lead(lead_id))
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p.startswith('/lead/') and p.endswith('/reject'):
            try:
                lead_id = p.split('/')[2]
                self.send_json(200, reject_lead(lead_id))
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p.startswith('/lead/') and p.endswith('/regenerate-email'):
            try:
                lead_id = p.split('/')[2]
                extras = body.get('instructions', '')
                self.send_json(200, regenerate_email_for_lead(lead_id, extras))
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p.startswith('/lead/') and p.endswith('/generate-mockup'):
            try:
                lead_id = p.split('/')[2]
                custom_prompt = body.get('custom_prompt', '') or None
                self.send_json(200, generate_mockup_for_lead(lead_id, custom_prompt=custom_prompt))
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p.startswith('/batch/') and p.endswith('/delete'):
            try:
                batch_id = p.split('/')[2]
                deleted = delete_search_batch(batch_id)
                self.send_json(200, {'success': True, 'deleted': deleted, 'batch_id': batch_id})
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/leads/delete':
            try:
                lead_ids = body.get('lead_ids') or []
                deleted = delete_leads_bulk(lead_ids)
                self.send_json(200, {'success': True, 'deleted': deleted})
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        else:
            self.send_json(404, {'error': 'not found'})

class ThreadingServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

if __name__ == '__main__':
    # Run schema migrations at startup so columns added in new releases
    # exist before any endpoint is called (avoids "column does not exist" crashes).
    try:
        ensure_discovery_tables()
        ensure_research_cache_table()
        ensure_research_history_table()
        ensure_intent_tables()
        ensure_email_verification_columns()
        ensure_m3_tables()
        ensure_m4_tables()
        ensure_m5_tables()
        print('Schema migration: OK')
    except Exception as e:
        print(f'Schema migration warning (non-fatal): {e}')
    try:
        ensure_auth_tables()
        ensure_service_token()
        print('Auth: OK (users + sessions in DB)')
    except Exception as e:
        print(f'WARNING: auth tables unavailable — login will fail until Postgres is up: {e}')
    # M4: follow-up sequence scheduler (every N minutes)
    if CONFIG.get('sequences_enabled', True):
        t = threading.Thread(target=sequence_scheduler_loop, daemon=True)
        t.start()
        print('Sequences: scheduler running')
    server = ThreadingServer(('0.0.0.0', 8080), Handler)
    print('LeadGen v5 - Multi-Module Intelligence Platform')
    print('Modules: discover, enrich, score, assets, seo, competitor, ecommerce')
    print('Endpoints: /search /discover /enrich /score /keywords /serp /competitor /ecommerce')
    print('Listening on :8080')
    server.serve_forever()
