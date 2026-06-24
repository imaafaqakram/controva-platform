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
GOOGLE_API_KEY = 'AIzaSyBLBQ8bN9EW6Gwj0Evy6EuU3zgGnaui6Dw'
SERPER_KEY     = 'd62d91f02d52f98ddacdf4ea623218502c1c492b'
GEMINI_KEY     = 'AIzaSyA4pX6dw-LrOMGn45h5RoNP9KQrnEtIcU4'
CLAUDE_KEY     = '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'
REPLICATE_TOKEN= 'r8_Vkh65JAx4ds9PN3XIDynavgw8DTn1KR3jKRMn'
IMAGINE_ART_KEY= os.environ.get('IMAGINE_ART_KEY', '')  # Set this when user provides it
OXYLABS_KEY    = 'iPz3YfTsAOsRt1ZE49T2wGdkOz0lPcInRQOEEgOW'
CRAWL4AI_URL   = 'http://localhost:11235'
CRAWL4AI_TOKEN = 'crawl4ai_secret_token_2024'
HERE_API_KEY   = os.environ.get('HERE_API_KEY', '')  # Free 250k/mo: developer.here.com

# Configuration toggles (can be changed via /config endpoint)
CONFIG = {
    'enrichment_primary': 'serper',       # serper | oxylabs | both
    'enrichment_fallback': 'oxylabs',     # oxylabs | none
    'image_provider': 'none',             # none | replicate | imagine_art
    'auto_score': True,                   # Run Gemini scoring during pipeline
    'auto_email_copy': False,             # Claude email writing OFF by default (saves credits)
    'auto_image': False,                  # Image generation OFF by default
}

# ──────────────────────────────────────────────────────────────
#  PERSISTENT CONFIG (saved to /opt/leadgen/config.json)
# ──────────────────────────────────────────────────────────────
CONFIG_FILE = '/opt/leadgen/config.json'

def load_config():
    """Load config from disk, fall back to defaults."""
    global GOOGLE_API_KEY, SERPER_KEY, GEMINI_KEY, CLAUDE_KEY, REPLICATE_TOKEN, IMAGINE_ART_KEY, OXYLABS_KEY, RESEND_KEY, FROM_EMAIL, FROM_NAME, HERE_API_KEY
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                saved = json.load(f)
            # API keys
            keys_map = {
                'google_api_key': 'GOOGLE_API_KEY',
                'serper_key': 'SERPER_KEY',
                'gemini_key': 'GEMINI_KEY',
                'claude_key': 'CLAUDE_KEY',
                'replicate_token': 'REPLICATE_TOKEN',
                'imagine_art_key': 'IMAGINE_ART_KEY',
                'oxylabs_key': 'OXYLABS_KEY',
                'resend_key': 'RESEND_KEY',
                'from_email': 'FROM_EMAIL',
                'from_name': 'FROM_NAME',
                'here_api_key': 'HERE_API_KEY',
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
            'google_api_key': GOOGLE_API_KEY,
            'serper_key': SERPER_KEY,
            'gemini_key': GEMINI_KEY,
            'claude_key': CLAUDE_KEY,
            'replicate_token': REPLICATE_TOKEN,
            'imagine_art_key': IMAGINE_ART_KEY,
            'oxylabs_key': OXYLABS_KEY,
            'resend_key': RESEND_KEY,
            'from_email': FROM_EMAIL,
            'from_name': FROM_NAME,
            'here_api_key': HERE_API_KEY,
            'config': CONFIG,
        }
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f'Config save error: {e}')
        return False

def update_api_key(name, value):
    """Update an API key and save."""
    global GOOGLE_API_KEY, SERPER_KEY, GEMINI_KEY, CLAUDE_KEY, REPLICATE_TOKEN, IMAGINE_ART_KEY, OXYLABS_KEY, RESEND_KEY, FROM_EMAIL, FROM_NAME, HERE_API_KEY
    name_lower = name.lower()
    valid_keys = ['google_api_key', 'serper_key', 'gemini_key', 'claude_key',
                  'replicate_token', 'imagine_art_key', 'oxylabs_key', 'resend_key',
                  'from_email', 'from_name', 'here_api_key']
    if name_lower not in valid_keys: return False
    # Update the actual global variable
    var_name = name_lower.upper()
    globals()[var_name] = value
    save_config()
    return True

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
    }

# Load saved config at startup
load_config()


FIELD_MASK = 'places.id,places.displayName,places.formattedAddress,places.location,places.websiteUri,places.nationalPhoneNumber,places.rating,places.userRatingCount'

DB = dict(host='127.0.0.1', port=5432, database='leadgen_db',
          user='leadgen', password='LeadGen_Secure_2024!')

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

# ──────────────────────────────────────────────────────────────
#  GEMINI - Natural Language Query Parser
# ──────────────────────────────────────────────────────────────
def gemini_call(prompt, max_tokens=300):
    try:
        body = json.dumps({
            'contents': [{'parts': [{'text': prompt}]}],
            'generationConfig': {'temperature': 0.2, 'maxOutputTokens': max_tokens}
        }).encode()
        req = urllib.request.Request(
            f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}',
            data=body, method='POST',
            headers={'Content-Type': 'application/json'}
        )
        resp = urllib.request.urlopen(req, timeout=20)
        data = json.loads(resp.read().decode())
        return data['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        print(f'Gemini error: {e}')
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

Country codes: US, GB, AE, IN, PK, BD, SA, AU, CA, SG, MY, EG, NG, ZA, BR, MX, AR, TR, ID, PH, TH, VN, JP, KR, CN, DE, FR, ES, IT, NL, BE, CH, SE, NO, DK, FI, PL, RU, UA, IR, IQ, JO, KW, BH, OM, QA, LB, MA, KE

Examples:
- "barber shops in Manchester UK" -> {{"niche":"barber","city":"Manchester","country":"GB","modifiers":[]}}
- "restaurants in Lahore Pakistan" -> {{"niche":"restaurant","city":"Lahore","country":"PK","modifiers":[]}}
- "dental clinics in Mumbai India" -> {{"niche":"dentist","city":"Mumbai","country":"IN","modifiers":[]}}
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
                    return parsed
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

    # Detect country (explicit country name in text)
    country = None
    for cname, code in country_to_iso.items():
        if re.search(r'\b' + re.escape(cname) + r'\b', text_lower):
            country = code
            break

    # Niche detection
    niche_words = ['restaurant', 'cafe', 'coffee', 'salon', 'hair', 'beauty', 'nail',
                   'barber', 'barbershop', 'hotel', 'bar', 'pub', 'gym', 'fitness',
                   'clinic', 'pharmacy', 'bakery', 'shop', 'retail', 'spa', 'dentist',
                   'laundry', 'supermarket', 'grocery', 'mechanic', 'school']
    niche = 'restaurant'
    for word in niche_words:
        if word in text_lower:
            niche = word
            break

    # City detection
    # Look for known cities first (most reliable)
    city = None
    for city_name in sorted(city_to_country.keys(), key=len, reverse=True):
        if re.search(r'\b' + re.escape(city_name) + r'\b', text_lower):
            city = city_name.title()
            if not country:
                country = city_to_country[city_name]
            break

    # If no known city, look for capitalized words after "in", "at", "near"
    if not city:
        m = re.search(r'\b(?:in|at|near|around|of)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2})', text)
        if m:
            city = m.group(1).strip()
            # Strip country words
            for cwords in ['UK', 'USA', 'UAE', 'India', 'Pakistan', 'Saudi', 'Canada',
                          'Australia', 'GB', 'US', 'AE', 'IN', 'PK', 'SA', 'CA', 'AU']:
                city = re.sub(r'\s*' + cwords + r'\s*$', '', city, flags=re.IGNORECASE).strip()

    # Final fallback
    if not city:
        city = 'Dubai'
    if not country:
        country = 'AE'

    # Sanity check: if city name IS a country name, use capital as city
    country_to_capital = {
        'pakistan': ('Islamabad', 'PK'), 'india': ('Mumbai', 'IN'),
        'bangladesh': ('Dhaka', 'BD'), 'uae': ('Dubai', 'AE'),
        'saudi arabia': ('Riyadh', 'SA'), 'singapore': ('Singapore', 'SG'),
    }
    city_lower = city.lower()
    if city_lower in country_to_capital:
        city, country = country_to_capital[city_lower]

    return {'niche': niche, 'city': city, 'country': country, 'modifiers': []}


# ──────────────────────────────────────────────────────────────
#  GEOCODING (Google Geocoding API, free with billing enabled)
# ──────────────────────────────────────────────────────────────
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
            # Cache in DB
            try:
                conn = db_conn(); cur = conn.cursor()
                cur.execute("INSERT INTO assets(asset_type, content, model_used) VALUES('geocode', %s, 'google-geocode')",
                           (json.dumps({**result, 'key': key}),))
                conn.commit(); cur.close(); conn.close()
            except Exception as e:
                print(f'Cache geocode error: {e}')
            return result
    except Exception as e:
        print(f'Geocode error: {e}')
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
PLACES_TEXT_URL = 'https://places.googleapis.com/v1/places:searchText'
TEXT_FIELD_MASK = ('places.id,places.displayName,places.formattedAddress,places.location,'
                   'places.websiteUri,places.nationalPhoneNumber,places.rating,'
                   'places.userRatingCount,nextPageToken')
OVERPASS_ENDPOINTS = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
]
NICHE_EXPANSION_CACHE = {}


def _places_text_post(body, tries=3):
    """POST to Places Text Search with retry/backoff.
    A 400 right after getting a nextPageToken usually means the token isn't
    valid yet (propagation delay) → back off and retry. 429 = rate limited."""
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
            return json.loads(resp.read().decode())
        except Exception as e:
            code = getattr(e, 'code', None)
            if code in (400, 429) and attempt < tries - 1:
                time.sleep(delay); delay *= 2; continue
            print(f'TextSearch error (code={code}): {e}')
            return {}
    return {}


def text_search_places(text_query, lat=None, lng=None, radius_m=None, rank='RELEVANCE', max_pages=3):
    """Google Places Text Search (New). Free-text → ANY niche works (no place-type
    enum needed). Paginates via nextPageToken up to ~60 results. Optionally bounded
    to a circular tile via locationRestriction."""
    base = {'textQuery': text_query, 'pageSize': 20}
    if rank in ('DISTANCE', 'RELEVANCE'):
        base['rankPreference'] = rank
    if lat is not None and lng is not None and radius_m:
        base['locationRestriction'] = {'circle': {
            'center': {'latitude': float(lat), 'longitude': float(lng)},
            'radius': float(min(radius_m, 50000))}}
    results, token = [], None
    for _page in range(max_pages):
        body = dict(base)
        if token:
            body['pageToken'] = token
        data = _places_text_post(body)
        results.extend(data.get('places', []))
        token = data.get('nextPageToken')
        if not token:
            break
        time.sleep(2.0)  # nextPageToken needs a moment to become valid
    return results


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
        cur.execute("CREATE INDEX IF NOT EXISTS idx_leads_phone_norm ON leads(phone_norm)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_leads_domain ON leads(domain)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_leads_website_verified ON leads(website_verified)")
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        print(f'ensure_discovery_tables error: {e}')


def discover_leads_smart(niche, city, country='', original_query='',
                         filter_mode='no_website', density='standard',
                         find_more=False, job_id=None):
    """Multi-source, round-based discovery.

    filter_mode : 'no_website' | 'with_website' | 'all'
    density     : 'low' | 'standard' | 'high' (how aggressive each round starts)
    find_more   : advance to the next round → wider radius, more synonyms, +OSM
    job_id      : if set, live progress is written to JOBS[job_id]
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
    _log(f'Round {rnd} · {len(round_terms)} search terms · {len(tiles)} map tiles · sources: {sources_str}')
    if len(round_terms) > 1:
        _log(f'Terms: {", ".join(round_terms)}')

    # ── harvest (collect raw, dedup in-memory by source_id) ──
    raw = {}
    here_units = len(round_terms) if use_here else 0
    total_units = len(tiles) * len(round_terms) + (len(tiles) if use_osm else 0) + here_units
    done_units = 0
    for (tlat, tlng, trad) in tiles:
        for term in round_terms:
            try:
                for p in text_search_places(term, tlat, tlng, trad):
                    pid = p.get('id')
                    if pid and pid not in raw:
                        raw[pid] = _norm_google_place(p)
            except Exception as e:
                print(f'text_search error: {e}')
            done_units += 1
            if done_units % 2 == 0 or done_units >= total_units:
                _log(f'Searched {done_units}/{total_units} · {len(raw)} candidates so far',
                     pct=min(80, done_units / max(1, total_units) * 80))
        if use_osm:
            try:
                for o in overpass_search(exp['osm_tags'], tlat, tlng, int(trad * 1.2)):
                    if o['source_id'] not in raw:
                        raw[o['source_id']] = o
            except Exception as e:
                print(f'overpass error: {e}')
            done_units += 1

    # HERE Maps: one call per term on the primary tile (100 results each)
    if use_here:
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

    _log(f'Collected {len(raw)} unique candidates. De-duplicating against your database…', pct=88)

    # ── dedup against DB (place_id / phone / domain) + insert NEW ──
    new_leads = []
    conn = db_conn(); cur = conn.cursor()
    for cand in raw.values():
        website = cand.get('website')
        has_website = bool(website)
        if filter_mode == 'no_website' and has_website:
            continue
        if filter_mode == 'with_website' and not has_website:
            continue
        pid = cand.get('source_id')
        if not pid:
            continue
        pn = norm_phone(cand.get('phone'))
        dom = norm_domain(website)
        try:
            cur.execute("""SELECT 1 FROM leads
                           WHERE place_id=%s
                              OR (%s <> '' AND phone_norm=%s)
                              OR (%s <> '' AND domain=%s)
                           LIMIT 1""",
                        (pid, pn, pn, dom, dom))
            if cur.fetchone():
                continue
            cur.execute("""INSERT INTO leads(place_id,business_name,niche,city,country,address,phone,
                          website,latitude,longitude,google_rating,review_count,status,source,phone_norm,domain)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'discovered',%s,%s,%s)
                ON CONFLICT (place_id) DO NOTHING RETURNING id""",
                (pid, (cand.get('name') or 'Unknown')[:480], niche.lower(), city, country,
                 cand.get('address', ''), cand.get('phone', ''), website,
                 cand.get('lat'), cand.get('lng'), cand.get('rating'),
                 cand.get('review_count', 0), cand.get('source', 'google'),
                 pn or None, dom or None))
            if cur.fetchone():
                new_leads.append({
                    'place_id': pid, 'business_name': cand.get('name', 'Unknown'),
                    'niche': niche, 'city': city, 'phone': cand.get('phone', ''),
                    'has_website': has_website, 'website': website,
                    'address': cand.get('address', ''), 'source': cand.get('source', 'google'),
                })
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

    _log(f'Done — {len(new_leads)} NEW leads added (round {rnd}).', pct=100)
    return new_leads, ('exhausted' if exhausted else 'success')


# ──────────────────────────────────────────────────────────────
#  ENRICHMENT - Provider toggle (Serper / Oxylabs / Both)
# ──────────────────────────────────────────────────────────────
def serper_search(query, num=10):
    try:
        body = json.dumps({'q': query, 'num': num}).encode()
        req = urllib.request.Request(
            'https://google.serper.dev/search',
            data=body, method='POST',
            headers={'X-API-KEY': SERPER_KEY, 'Content-Type': 'application/json'}
        )
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read().decode())
    except Exception as e:
        print(f'Serper error: {e}')
        return {}

def oxylabs_scrape(url, output='markdown'):
    if not OXYLABS: return None
    try:
        result = OXYLABS.scrape(url=url, output_format=output, render_javascript=False)
        if result and result.data:
            return result.data if isinstance(result.data, str) else json.dumps(result.data)
    except Exception as e:
        print(f'Oxylabs scrape error: {e}')
    return None

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

def enrich_with_email_permutator(business_name, owner_name=''):
    """FREE Hunter.io alternative: generate likely email patterns + verify via MX."""
    # Find or guess domain
    domain_guess = re.sub(r'\W+', '', business_name.lower())[:20] + '.com'

    if owner_name:
        names = owner_name.lower().split()
        first = names[0] if names else ''
        last = names[-1] if len(names) > 1 else ''
        patterns = [
            f'{first}@{domain_guess}',
            f'{first}.{last}@{domain_guess}',
            f'{first}{last}@{domain_guess}',
            f'{first[0]}{last}@{domain_guess}' if first and last else '',
        ]
    else:
        patterns = [
            f'info@{domain_guess}',
            f'contact@{domain_guess}',
            f'hello@{domain_guess}',
        ]

    # MX verification
    verified = []
    for email in patterns:
        if not email: continue
        domain = email.split('@')[1]
        try:
            socket.gethostbyname(domain)  # basic existence check
            verified.append({'email': email, 'verified': 'domain_exists', 'pattern': True})
        except: pass
    return verified

def enrich_lead(lead_id, business_name, city, phone, niche, providers=None):
    """Smart enrichment with provider selection.

    providers: list of strategies in order. Options:
      - 'serper' (default)
      - 'oxylabs'
      - 'serper+oxylabs' (Serper first, Oxylabs only if no email)
      - 'permutator' (free Hunter alternative)
    """
    if providers is None:
        providers = [CONFIG['enrichment_primary']]
        if CONFIG['enrichment_fallback'] != 'none':
            providers.append(CONFIG['enrichment_fallback'])

    result = {'lead_id': lead_id, 'email': None, 'linkedin_url': None,
              'facebook_url': None, 'instagram_url': None,
              'owner_name': None, 'sources_tried': []}

    for prov in providers:
        if result['email'] and prov != 'serper':
            continue  # already found email, no need to fallback

        if prov == 'serper':
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
            r = enrich_with_email_permutator(business_name, result.get('owner_name', ''))
            result['sources_tried'].append('permutator')
            if r and not result['email']:
                result['email'] = r[0]['email']
                result['email_method'] = 'permutator_guess'
    return result

def save_enrichment(result):
    conn = db_conn(); cur = conn.cursor()
    try:
        confidence = 0
        if result.get('email'):        confidence += 40
        if result.get('linkedin_url'): confidence += 30
        if result.get('facebook_url'): confidence += 15
        if result.get('owner_name'):   confidence += 5

        if result.get('email') or result.get('linkedin_url') or result.get('facebook_url'):
            cur.execute("""
                INSERT INTO contacts (lead_id, full_name, email, linkedin_url, source, confidence)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (result['lead_id'], result.get('owner_name', '') or '',
                  result.get('email', '') or '', result.get('linkedin_url', '') or '',
                  '+'.join(result.get('sources_tried', [])), confidence))

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
        SELECT l.id, l.business_name, l.city, l.phone, l.niche
        FROM leads l
        LEFT JOIN contacts c ON c.lead_id = l.id
        WHERE l.status = 'discovered'
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
        lead_id, bname, city, phone, niche = ld
        try:
            r = enrich_lead(str(lead_id), bname, city, phone, niche, providers)
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

def reenrich_missing_emails(use_oxylabs=True):
    """Find emails for leads that have no email yet, using Oxylabs deep scrape."""
    conn = db_conn(); cur = conn.cursor()
    cur.execute("""
        SELECT l.id, l.business_name, l.city, l.phone, l.niche
        FROM leads l
        LEFT JOIN contacts c ON c.lead_id = l.id
        WHERE l.status IN ('enriched', 'ready') AND (c.email IS NULL OR c.email = '')
        ORDER BY l.created_at DESC LIMIT 50
    """)
    leads = cur.fetchall(); cur.close(); conn.close()
    results = []
    for ld in leads:
        lead_id, bname, city, phone, niche = ld
        try:
            if use_oxylabs and OXYLABS:
                r = enrich_with_oxylabs(bname, city)
                if r.get('email'):
                    conn = db_conn(); cur = conn.cursor()
                    cur.execute("UPDATE contacts SET email=%s WHERE lead_id=%s AND (email IS NULL OR email='')",
                               (r['email'], lead_id))
                    if cur.rowcount == 0:
                        cur.execute("INSERT INTO contacts(lead_id, email, source, confidence) VALUES(%s, %s, 'oxylabs', 40)",
                                   (lead_id, r['email']))
                    conn.commit(); cur.close(); conn.close()
                    results.append({'business_name': bname, 'email': r['email']})
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
#  E-COMMERCE RESEARCH
# ──────────────────────────────────────────────────────────────
def ecommerce_research(product_or_niche, platform='amazon'):
    """Quick product/niche research on Amazon, eBay, etc."""
    result = {
        'query': product_or_niche,
        'platform': platform,
        'top_listings': [],
        'price_range': {},
        'trends': []
    }

    if platform == 'amazon':
        # Use Oxylabs to scrape Amazon search
        url = f'https://www.amazon.com/s?k={urllib.parse.quote(product_or_niche)}'
        if OXYLABS:
            text = oxylabs_scrape(url, 'markdown')
            if text:
                # Extract prices
                prices = re.findall(r'\$(\d+(?:\.\d+)?)', text)
                if prices:
                    prices_f = [float(p) for p in prices[:50]]
                    result['price_range'] = {
                        'min': min(prices_f),
                        'max': max(prices_f),
                        'avg': sum(prices_f) / len(prices_f),
                        'sample_size': len(prices_f)
                    }

    # SERP for general trends
    d = serper_search(f'{product_or_niche} buy review', 10)
    if d:
        for o in d.get('organic', [])[:5]:
            result['top_listings'].append({
                'title': o.get('title', ''),
                'url': o.get('link', ''),
                'snippet': o.get('snippet', '')[:200]
            })
    return result

# ──────────────────────────────────────────────────────────────
#  IMAGE GENERATION (Optional + Toggleable)
# ──────────────────────────────────────────────────────────────
def generate_mockup_replicate(business_name, niche, city):
    """Use Replicate FLUX (existing)."""
    prompt = f"Professional modern website homepage screenshot mockup for '{business_name}', a {niche} business in {city}. Clean hero section, white navigation bar, green CTA button, photorealistic UI mockup, desktop browser viewport"
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

def generate_mockup_imagine_art(business_name, niche, city):
    """Use imagine.art API. Returns URL of generated image."""
    if not IMAGINE_ART_KEY:
        return None
    prompt = f"Professional modern website homepage mockup for {business_name}, a {niche} business in {city}. Clean hero section, elegant typography, modern UI design, photorealistic browser screenshot, premium feel"
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
            filepath = f'/opt/leadgen/mockups/{filename}'
            os.makedirs('/opt/leadgen/mockups', exist_ok=True)
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

def generate_image(business_name, niche, city, provider=None):
    """Generate mockup using configured provider (or specified one)."""
    provider = provider or CONFIG['image_provider']
    if provider == 'replicate':
        return generate_mockup_replicate(business_name, niche, city)
    elif provider == 'imagine_art':
        return generate_mockup_imagine_art(business_name, niche, city)
    return None

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
        if m: return json.loads(m.group())
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
            if m: return json.loads(m.group())
        except: pass
    return {'score': 5, 'reason': 'Default', 'best_channel': 'Phone'}

def score_all_enriched():
    conn = db_conn(); cur = conn.cursor()
    cur.execute("""SELECT l.id, l.business_name, l.niche, l.city, l.phone, c.email, c.linkedin_url
        FROM leads l LEFT JOIN contacts c ON c.lead_id = l.id
        WHERE l.status = 'enriched' AND l.ai_score IS NULL
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
        WHERE l.status = 'enriched' AND l.ai_score >= %s
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

        # Strategy 1: Scrape About/Contact pages (real emails)
        real_emails = scrape_about_page_for_emails(domain)
        for email in real_emails:
            result['verified_emails'].append({
                'email': email,
                'source': 'about_page',
                'confidence': 90
            })

        # Strategy 2: Pattern generation
        if result['mx_valid']:
            patterns = generate_email_patterns(domain, first_name, last_name)
            result['pattern_guesses'] = patterns

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
#  M2: VERIFY EMAIL (SMTP-level)
# ──────────────────────────────────────────────────────────────
def verify_email(email):
    """Verify if an email address looks deliverable.
    Performs syntax, DNS, MX, and SMTP-level mailbox checks where possible.
    """
    result = {
        'email': email,
        'syntax_valid': bool(EMAIL_RE.match(email)),
        'domain_resolves': False,
        'has_mx': False,
        'mailbox_exists': None,  # None=not checked, True/False=checked
        'risk_level': 'unknown',
        'details': []
    }
    if not result['syntax_valid']:
        result['risk_level'] = 'high'
        result['details'].append('Invalid email syntax')
        return result

    domain = email.split('@')[1].lower()

    # Step 1: DNS check
    import socket
    try:
        socket.gethostbyname(domain)
        result['domain_resolves'] = True
    except:
        result['risk_level'] = 'high'
        result['details'].append('Domain does not resolve - invalid')
        return result

    # Step 2: MX check
    mx_hosts = []
    try:
        import subprocess
        mx = subprocess.run(['dig', '+short', 'MX', domain], capture_output=True, text=True, timeout=5)
        if mx.stdout.strip():
            result['has_mx'] = True
            # Parse MX records (format: "10 mx.example.com.")
            for line in mx.stdout.strip().split('\n'):
                parts = line.strip().split()
                if len(parts) >= 2:
                    mx_hosts.append((int(parts[0]) if parts[0].isdigit() else 10, parts[1].rstrip('.')))
            mx_hosts.sort()  # Lowest priority first
    except Exception as e:
        result['details'].append(f'MX lookup failed: {e}')

    # Free email provider detection
    free_providers = ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
                     'icloud.com', 'aol.com', 'protonmail.com', 'mail.com', 'gmx.com',
                     'live.com', 'msn.com', 'zoho.com', 'yandex.com']

    is_free = domain in free_providers

    # Step 3: SMTP-level RCPT TO check (the REAL verification)
    if mx_hosts:
        try:
            import smtplib
            mx_host = mx_hosts[0][1]
            with smtplib.SMTP(timeout=10) as smtp:
                smtp.connect(mx_host)
                smtp.helo('controvallc.com')
                smtp.mail('verify@controvallc.com')
                code, msg = smtp.rcpt(email)
                # 250 = mailbox exists, 550 = does not exist, others = unknown
                if code == 250:
                    result['mailbox_exists'] = True
                    result['details'].append(f'SMTP {mx_host} accepted recipient (code 250)')
                elif code in (550, 551, 553):
                    result['mailbox_exists'] = False
                    result['details'].append(f'SMTP {mx_host} rejected recipient (code {code}): {msg.decode() if isinstance(msg, bytes) else msg}')
                else:
                    result['details'].append(f'SMTP {mx_host} returned code {code} (inconclusive)')
        except Exception as e:
            result['details'].append(f'SMTP check failed: {str(e)[:100]}')

    # Determine type and risk level
    if is_free:
        result['type'] = 'free_provider'
        if result['mailbox_exists'] is True:
            result['risk_level'] = 'low'
        elif result['mailbox_exists'] is False:
            result['risk_level'] = 'high'
            result['details'].append('Free provider rejected this mailbox')
        else:
            result['risk_level'] = 'medium'
            result['details'].append('Free providers (Gmail/Yahoo/etc) often hide mailbox existence')
    elif result['has_mx']:
        result['type'] = 'business'
        if result['mailbox_exists'] is True:
            result['risk_level'] = 'low'
        elif result['mailbox_exists'] is False:
            result['risk_level'] = 'high'
        else:
            result['risk_level'] = 'medium'
    else:
        result['type'] = 'unknown'
        result['risk_level'] = 'high'

    return result

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
    'linkedin_profile': 'LinkedIn /in/', 'github': 'GitHub',
    'stackoverflow': 'Stack Overflow', 'upwork_profiles': 'Upwork freelancers',
    'behance': 'Behance', 'dribbble': 'Dribbble',
    'open_to_work': '"Open to work"', 'generic_provide': 'Generic web (for hire)',
}

def intent_search_dorks(query, direction, location=''):
    q = query.strip()
    loc = f' "{location}"' if location else ''
    if direction == 'demand':
        return [
            ('linkedin_jobs',   f'site:linkedin.com/jobs "{q}"{loc}'),
            ('reddit_forhire',  f'site:reddit.com/r/forhire "{q}"'),
            ('reddit_general',  f'site:reddit.com "hiring {q}"'),
            ('hn_hiring',       f'site:news.ycombinator.com "{q}" hiring'),
            ('twitter_x',       f'(site:twitter.com OR site:x.com) "hiring {q}"'),
            ('indeed',          f'site:indeed.com "{q}"{loc}'),
            ('wellfound',       f'(site:wellfound.com OR site:angel.co) "{q}"'),
            ('generic_hiring',  f'"we are hiring" "{q}"{loc}'),
            ('generic_looking', f'"looking for {q}"{loc}'),
        ]
    elif direction == 'supply':
        return [
            ('linkedin_profile',f'site:linkedin.com/in/ "{q}"{loc}'),
            ('github',          f'site:github.com "{q}"{loc}'),
            ('stackoverflow',   f'site:stackoverflow.com/users "{q}"'),
            ('upwork_profiles', f'site:upwork.com/freelancers "{q}"'),
            ('behance',         f'site:behance.net "{q}"'),
            ('dribbble',        f'site:dribbble.com "{q}"'),
            ('open_to_work',    f'"{q}" ("open to work" OR "available for hire")'),
            ('generic_provide', f'"{q}" "for hire"{loc}'),
        ]
    return []

def serper_search_with_recency(query, num=10, recency_days=30):
    """Serper search with Google date filter (qdr param)."""
    if   recency_days <= 1:   tbs = 'qdr:d'
    elif recency_days <= 7:   tbs = 'qdr:w'
    elif recency_days <= 31:  tbs = 'qdr:m'
    elif recency_days <= 365: tbs = 'qdr:y'
    else: tbs = None
    try:
        body_dict = {'q': query, 'num': num}
        if tbs: body_dict['tbs'] = tbs
        body = json.dumps(body_dict).encode()
        req = urllib.request.Request(
            'https://google.serper.dev/search',
            data=body, method='POST',
            headers={'X-API-KEY': SERPER_KEY, 'Content-Type': 'application/json'}
        )
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read().decode())
    except Exception as e:
        print(f'Serper intent error: {e}')
        return {}

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

    # Batch classify in groups of 15 to keep within Gemini rate limits
    classifications = []
    for i in range(0, len(candidates), 15):
        chunk = candidates[i:i+15]
        classifications.extend(classify_intent_batch(chunk, query, direction))

    saved = []
    conn = db_conn(); cur = conn.cursor()
    for c, cls in zip(candidates, classifications):
        if len(saved) >= max_results: break
        if not cls: continue
        if not cls.get('is_active_intent'): continue
        if int(cls.get('confidence') or 0) < min_confidence: continue

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

            # If contact_hint looks like an email, save to contacts table too
            if contact and EMAIL_RE.match(contact.strip()):
                cur.execute("""
                    INSERT INTO contacts(lead_id, full_name, email, source, confidence)
                    VALUES(%s, %s, %s, 'intent_classifier', %s)
                """, (lead_id, lead_name[:400], contact.strip()[:500],
                      int(cls.get('confidence') or 0)))

            saved.append({
                'lead_id': str(lead_id), 'direction': direction,
                'source': c['source'], 'source_label': INTENT_SOURCE_LABELS.get(c['source'], c['source']),
                'url': c['url'], 'title': c['title'], 'snippet': c['snippet'],
                'name': lead_name, 'role_or_service': role,
                'location_hint': loc_hint, 'contact_hint': contact,
                'confidence': int(cls.get('confidence') or 0),
                'posted_recency': cls.get('posted_recency', 'unknown'),
                'reasoning': cls.get('reasoning', '')
            })
        except Exception as e:
            print(f'Intent save error: {e}')
            conn.rollback()
            continue

    conn.commit(); cur.close(); conn.close()
    mark_query_cached('intent', cache_payload)
    return saved, 'success'

def get_intent_leads(direction=None, query_filter='', limit=100):
    conn = db_conn(); cur = conn.cursor()
    where = ['l.lead_type IN (\'demand\', \'supply\')']
    params = []
    if direction in ('demand', 'supply'):
        where.append('l.lead_type = %s'); params.append(direction)
    if query_filter:
        where.append('(i.role_or_service ILIKE %s OR l.business_name ILIKE %s)')
        params.append(f'%{query_filter}%'); params.append(f'%{query_filter}%')
    params.append(limit)
    cur.execute(f"""
        SELECT l.id::text as lead_id, l.lead_type as direction, l.business_name as name,
               l.niche as role_or_service, l.city as location_hint, l.website as url,
               COALESCE(c.email, '') as contact_hint,
               COALESCE(i.source, '') as source,
               COALESCE(i.confidence, 0) as confidence,
               COALESCE(i.raw_snippet, '') as snippet,
               to_char(l.created_at,'YYYY-MM-DD HH24:MI') as found_at
        FROM leads l
        LEFT JOIN LATERAL (
            SELECT source, confidence, raw_snippet FROM intent_signals
            WHERE lead_id = l.id ORDER BY confidence DESC LIMIT 1
        ) i ON TRUE
        LEFT JOIN contacts c ON c.lead_id = l.id
        WHERE {' AND '.join(where)}
        ORDER BY i.confidence DESC NULLS LAST, l.created_at DESC
        LIMIT %s
    """, tuple(params))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    for r in rows:
        r['source_label'] = INTENT_SOURCE_LABELS.get(r.get('source', ''), r.get('source', ''))
    cur.close(); conn.close()
    return rows

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
               COALESCE(c.linkedin_url,'') as linkedin_url,
               COALESCE(c.job_title,'') as job_title,
               COALESCE((SELECT content FROM assets WHERE lead_id=l.id AND asset_type='mockup_image' LIMIT 1),'') as mockup_url,
               COALESCE((SELECT content FROM assets WHERE lead_id=l.id AND asset_type='email_subject' LIMIT 1),'') as email_subject,
               COALESCE((SELECT content FROM assets WHERE lead_id=l.id AND asset_type='email_body' LIMIT 1),'') as email_body,
               to_char(l.created_at,'YYYY-MM-DD HH24:MI') as date_found,
               to_char(l.updated_at,'YYYY-MM-DD HH24:MI') as date_updated,
               CASE WHEN l.has_website THEN 'Has Website' ELSE 'NO WEBSITE - HOT LEAD' END as lead_type,
               l.has_website,
               l.website_verified
        FROM leads l LEFT JOIN contacts c ON c.lead_id=l.id
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

def run_discover_bg(job_id, niche, city, country, filter_mode, density, find_more, original_query=''):
    """Discovery background job — runs the multi-source engine and reports live progress."""
    try:
        if job_id not in JOBS:
            JOBS[job_id] = {'status': 'running', 'progress': 0,
                            'log': [f'Discovering "{niche}" in {city}…'], 'step': 'Discover'}
        leads, status = discover_leads_smart(
            niche, city, country, original_query,
            filter_mode=filter_mode, density=density,
            find_more=find_more, job_id=job_id)
        JOBS[job_id]['status'] = 'completed'
        JOBS[job_id]['progress'] = 100
        if status == 'geocode_failed':
            JOBS[job_id]['log'].append('Could not find that location — try adding the country.')
        elif status == 'exhausted':
            JOBS[job_id]['log'].append('This area looks fully explored — few new businesses left.')
        JOBS[job_id]['results'] = {
            'total': len(leads), 'total_new_leads': len(leads),
            'leads': leads[:200], 'discover_status': status,
            'niche': niche, 'city': city, 'country': country,
            'filter_mode': filter_mode, 'density': density, 'find_more': find_more,
        }
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
            SELECT l.id, l.business_name, l.city, l.phone, l.niche
            FROM leads l
            LEFT JOIN contacts c ON c.lead_id = l.id
            WHERE l.status = 'discovered'
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
            lead_id, bname, city, phone, niche = ld
            try:
                r = enrich_lead(str(lead_id), bname, city, phone, niche, providers)
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

def run_verify_websites_bg(job_id, lead_ids=None):
    """Check whether each lead has a live website.
    - Leads with a URL stored: HTTP HEAD to verify it's live
    - Leads without a URL: Serper search to find if they have one
    Updates has_website + website columns in the DB."""
    try:
        conn = db_conn(); cur = conn.cursor()
        if lead_ids:
            cur.execute("SELECT id, business_name, city, niche, website FROM leads WHERE id = ANY(%s::int[])",
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
                cur2.execute("""UPDATE leads SET has_website=%s, website=%s,
                                website_verified=TRUE, updated_at=NOW() WHERE id=%s""",
                             (alive, website if alive else None, lid))
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
AUTH_USERS = {
    "admin": {"salt": "controva2026salt", "hash": _h_hashlib.sha256(("ChangeMe_2026!" + "controva2026salt").encode()).hexdigest()}
}
ACTIVE_TOKENS = {}  # token -> {user, expires_at}

def auth_hash(password, salt):
    return _h_hashlib.sha256((password + salt).encode()).hexdigest()

def auth_login(username, password):
    user = AUTH_USERS.get(username)
    if not user: return None
    if auth_hash(password, user["salt"]) != user["hash"]: return None
    token = _h_secrets.token_urlsafe(32)
    ACTIVE_TOKENS[token] = {"user": username, "expires_at": time.time() + 86400 * 7}
    return token

def auth_check(token):
    if not token: return False
    entry = ACTIVE_TOKENS.get(token)
    if not entry: return False
    if entry["expires_at"] < time.time():
        del ACTIVE_TOKENS[token]
        return False
    return entry["user"]

def auth_change_password(username, old_password, new_password):
    user = AUTH_USERS.get(username)
    if not user: return False
    if auth_hash(old_password, user["salt"]) != user["hash"]: return False
    new_salt = _h_secrets.token_hex(8)
    AUTH_USERS[username] = {"salt": new_salt, "hash": auth_hash(new_password, new_salt)}
    return True

# ──────────────────────────────────────────────────────────────
#  M4: EMAIL SENDING via RESEND.COM
# ──────────────────────────────────────────────────────────────
RESEND_KEY = "re_gaFiXEZr_KYM9sRWj4Bsfx3UXpceXnzzx"
FROM_EMAIL = "Support@controvallc.com"
FROM_NAME = "Controva LLC"

def send_email_via_resend(to_email, subject, body_text, body_html=None, from_email=None, from_name=None):
    """Send an email via Resend.com API."""
    if not body_html:
        # Convert plain text with line breaks to HTML
        body_html = body_text.replace("\\n", "<br>")
        body_html = f"""<html><body style="font-family: -apple-system, sans-serif; font-size: 15px; line-height: 1.6; color: #333; max-width: 600px;">{body_html}</body></html>"""

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

    if not email:
        cur.close(); conn.close()
        return {"success": False, "error": "No email for this lead"}
    if not subj or not body:
        cur.close(); conn.close()
        return {"success": False, "error": "Email copy not generated yet"}

    # Build HTML version with mockup if available
    body_html = body.replace("\\n", "<br>")
    if mockup:
        body_html += f'<br><br><img src="{mockup}" alt="Website Mockup for {name}" style="max-width:100%; border-radius:8px;">'
    body_html = f"""<html><body style="font-family: -apple-system, BlinkMacSystemFont, sans-serif; font-size: 15px; line-height: 1.6; color: #333; max-width: 600px; padding: 16px;">{body_html}</body></html>"""

    result = send_email_via_resend(email, subj, body, body_html)

    if result.get("success"):
        # Log the outreach
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
               c.full_name, c.email, c.linkedin_url, c.job_title,
               (SELECT content FROM assets WHERE lead_id=l.id AND asset_type='mockup_image' LIMIT 1) as mockup,
               (SELECT content FROM assets WHERE lead_id=l.id AND asset_type='email_subject' LIMIT 1) as subj,
               (SELECT content FROM assets WHERE lead_id=l.id AND asset_type='email_body' LIMIT 1) as body
        FROM leads l LEFT JOIN contacts c ON c.lead_id = l.id WHERE l.id = %s
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
        "linkedin_url": r[15] or "", "job_title": r[16] or "",
        "mockup_url": r[17] or "", "email_subject": r[18] or "", "email_body": r[19] or ""
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
    conn = db_conn(); cur = conn.cursor()

    # Leads per day for the last 14 days
    cur.execute("""
        SELECT DATE(created_at) as d, COUNT(*) as c
        FROM leads
        WHERE created_at > NOW() - INTERVAL '14 days'
        GROUP BY DATE(created_at) ORDER BY d
    """)
    leads_per_day = [{"date": str(r[0]), "count": r[1]} for r in cur.fetchall()]

    # Status breakdown
    cur.execute("SELECT status, COUNT(*) FROM leads GROUP BY status")
    status_breakdown = [{"status": r[0], "count": r[1]} for r in cur.fetchall()]

    # Niche breakdown
    cur.execute("SELECT niche, COUNT(*) FROM leads GROUP BY niche ORDER BY 2 DESC LIMIT 10")
    niche_breakdown = [{"niche": r[0], "count": r[1]} for r in cur.fetchall()]

    # City breakdown
    cur.execute("SELECT city, COUNT(*) FROM leads GROUP BY city ORDER BY 2 DESC LIMIT 10")
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
        FROM leads GROUP BY bucket
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


# ──────────────────────────────────────────────────────────────
#  HTTP HANDLERS
# ──────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

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
        if p == '/' or p == '/dashboard':
            try:
                with open('/opt/leadgen/dashboard.html', 'r', encoding='utf-8') as f:
                    html = f.read()
                self.send_html(html)
            except Exception as e:
                self.send_json(500, {'error': str(e)})
        elif p in ('/leads', '/leads.json'):
            try:
                cols, rows = get_leads()
                self.send_json(200, {'status': 'ok', 'total': len(rows), 'columns': cols, 'leads': rows})
            except Exception as e:
                self.send_json(500, {'error': str(e)})
        elif p == '/leads.csv':
            try:
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

        elif p.startswith('/mockups/'):
            try:
                filename = p[9:]
                # Security: prevent path traversal
                if '..' in filename or '/' in filename:
                    self.send_json(404, {'error': 'not found'})
                    return
                filepath = '/opt/leadgen/mockups/' + filename
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
                """)
                row = cur.fetchone()
                cur.execute("SELECT COUNT(*) FROM contacts WHERE email != ''")
                with_email = cur.fetchone()[0]
                cur.execute("SELECT COUNT(DISTINCT city) FROM leads")
                cities = cur.fetchone()[0]
                cur.close(); conn.close()
                self.send_json(200, {
                    'hot_leads': row[0], 'total': row[1], 'discovered': row[2],
                    'enriched': row[3], 'scored': row[4], 'ready': row[5],
                    'sent': row[6], 'high_score': row[7],
                    'with_email': with_email, 'cities': cities
                })
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/intent-leads':
            try:
                q = urllib.parse.urlparse(self.path).query
                qs = urllib.parse.parse_qs(q)
                direction = (qs.get('direction', [None])[0])
                qf = qs.get('q', [''])[0]
                limit = int(qs.get('limit', ['100'])[0])
                rows = get_intent_leads(direction=direction, query_filter=qf, limit=limit)
                self.send_json(200, {'total': len(rows), 'leads': rows})
            except Exception as e:
                self.send_json(500, {'error': str(e)})

        elif p == '/intent-stats':
            try:
                self.send_json(200, get_intent_stats())
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

        else:
            self.send_json(404, {'error': 'not found'})

    def do_POST(self):
        p = self.path.split('?')[0]
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length).decode()) if length else {}
        except:
            body = {}

        if p == '/search':
            # Free-text natural language search → background discovery job
            try:
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
                job_id = f'job_{int(time.time() * 1000)}'
                JOBS[job_id] = {'status': 'running', 'progress': 0,
                                'log': [f'Parsing "{query}" → {parsed.get("niche")} in {parsed.get("city")}'],
                                'step': 'Discover'}
                t = threading.Thread(target=run_discover_bg, args=(
                    job_id, parsed['niche'], parsed['city'], parsed.get('country', ''),
                    filter_mode, density, find_more, query))
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

        elif p == '/discover':
            try:
                niche = body.get('niche', 'restaurant')
                city = body.get('city', 'Dubai')
                country = body.get('country', '')
                filter_mode = body.get('filter_mode', 'no_website')
                density = body.get('density', 'standard')
                find_more = bool(body.get('find_more', False))
                job_id = f'job_{int(time.time() * 1000)}'
                JOBS[job_id] = {'status': 'running', 'progress': 0,
                                'log': [f'Discovering "{niche}" in {city}…'], 'step': 'Discover'}
                t = threading.Thread(target=run_discover_bg, args=(
                    job_id, niche, city, country, filter_mode, density, find_more, ''))
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

        elif p == '/reenrich-missing-emails':
            try:
                use_oxy = body.get('use_oxylabs', True)
                job_id = f'job_{int(time.time())}'
                JOBS[job_id] = {'status': 'running', 'progress': 0, 'log': ['Starting: Find missing emails...'], 'step': 'Find missing emails'}
                t = threading.Thread(target=run_step_bg, args=(job_id, reenrich_missing_emails, 'Find missing emails', use_oxy))
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
                q = body.get('query', '')
                plat = body.get('platform', 'amazon')
                if not q:
                    self.send_json(400, {'error': 'query required'})
                    return
                result = ecommerce_research(q, plat)
                self.send_json(200, result)
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

        else:
            self.send_json(404, {'error': 'not found'})

class ThreadingServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

if __name__ == '__main__':
    server = ThreadingServer(('0.0.0.0', 8080), Handler)
    print('LeadGen v5 - Multi-Module Intelligence Platform')
    print('Modules: discover, enrich, score, assets, seo, competitor, ecommerce')
    print('Endpoints: /search /discover /enrich /score /keywords /serp /competitor /ecommerce')
    print('Listening on :8080')
    server.serve_forever()
