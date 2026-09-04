#!/usr/bin/env python3
"""
Controva Platform Public API  v1.0
====================================
Dedicated REST API layer. Runs on port 8081.
Main platform stays on 8080.

Auth   : X-API-Key header
Limits : 100 req/min per key
Port   : 8081

Quickstart:
    python server/controva_api.py

Create first key:
    curl -X POST http://localhost:8081/api/v1/keys \
      -H "Content-Type: application/json" \
      -d '{"master_secret":"YOUR_MASTER_SECRET","name":"my-app","scopes":["read","write"]}'
"""
import json, time, hashlib, os, threading, urllib.request, urllib.parse, io, csv as csvlib
import psycopg2, secrets, uuid

from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

# ─────────────────────────────────────────────────────────
#  Config
# ─────────────────────────────────────────────────────────
API_PORT   = int(os.environ.get('API_PORT', 8081))
API_VER    = 'v1'
BASE       = f'/api/{API_VER}'
RATE_LIMIT = 100          # req / minute per key
PLATFORM   = os.environ.get('PLATFORM_URL', 'http://localhost:8080')

DB = dict(
    host     = os.environ.get('DB_HOST',  '127.0.0.1'),
    port     = int(os.environ.get('DB_PORT', 5433)),
    database = os.environ.get('DB_NAME', 'leadgen_db'),
    user     = os.environ.get('DB_USER', 'leadgen'),
    password = os.environ.get('DB_PASS', ''),
    connect_timeout = 2,
)

# ── Master secret & service token ─────────────────────────────
# MASTER_KEY authorizes creating API keys. Set via env or the shared
# config.json (the same file leads_api.py uses) — never hardcode it.
# SERVICE_TOKEN is what we present to leads_api.py, which now rejects
# anonymous requests.
_LEADGEN_HOME = os.environ.get('LEADGEN_HOME', '/opt/leadgen')
if not os.path.isdir(_LEADGEN_HOME):
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.exists(os.path.join(_script_dir, 'config.json')):
        _LEADGEN_HOME = _script_dir

def _read_shared_config(*keys):
    vals = {}
    for path in (os.path.join(_LEADGEN_HOME, 'config.json'),
                 os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')):
        try:
            with open(path) as f:
                data = json.load(f)
            for k in keys:
                if k in data and data[k] and k not in vals:
                    vals[k] = data[k]
        except Exception:
            pass
    return vals

_shared = _read_shared_config('master_secret', 'service_token')
MASTER_KEY    = os.environ.get('API_MASTER_SECRET', '') or _shared.get('master_secret', '')
SERVICE_TOKEN = os.environ.get('SERVICE_TOKEN', '') or _shared.get('service_token', '')



# ─────────────────────────────────────────────────────────
#  Rate limiter  (in-memory)
# ─────────────────────────────────────────────────────────
_rl_lock  = threading.Lock()
_rl_store = {}   # key -> [timestamps]

def _rate(api_key):
    """Return (allowed, remaining, reset_secs)."""
    now, win = time.time(), 60.0
    with _rl_lock:
        hits = [t for t in _rl_store.get(api_key, []) if now - t < win]
        rem = RATE_LIMIT - len(hits)
        if rem <= 0:
            reset = int(win - (now - hits[0])) if hits else 60
            _rl_store[api_key] = hits
            return False, 0, reset
        hits.append(now)
        _rl_store[api_key] = hits
        return True, rem - 1, int(win)

# ─────────────────────────────────────────────────────────
#  DB helpers
# ─────────────────────────────────────────────────────────
def db():
    return psycopg2.connect(**DB)

def ensure_tables():
    """Try to create DB tables; silently fall back to file storage if DB unavailable."""
    try:
        c = db(); cur = c.cursor()
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
        c.commit(); cur.close(); c.close()
        print('[API] api_keys table ready (DB mode)')
    except Exception as e:
        print(f'[API] DB unavailable — using file-based key storage ({e})')

# ─────────────────────────────────────────────────────────
#  File-based key store fallback
# ─────────────────────────────────────────────────────────
KEY_FILE = os.path.join(os.path.dirname(__file__), 'api_keys.json')
_kf_lock = threading.Lock()

def _load_keys():
    with _kf_lock:
        if os.path.exists(KEY_FILE):
            try:
                with open(KEY_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return []

def _save_keys(keys):
    with _kf_lock:
        with open(KEY_FILE, 'w') as f:
            json.dump(keys, f, indent=2, default=str)


def validate_key(raw):
    """Returns {'scopes':[...]} or None. Tries DB first, falls back to file."""
    if not raw:
        return None
    h = hashlib.sha256(raw.encode()).hexdigest()
    # Try DB
    try:
        c = db(); cur = c.cursor()
        cur.execute(
            "SELECT id, scopes, is_active FROM api_keys WHERE key_hash=%s", (h,))
        row = cur.fetchone()
        if row and row[2]:
            cur.execute(
                "UPDATE api_keys SET last_used=NOW(), request_count=request_count+1 WHERE id=%s",
                (row[0],))
            c.commit()
            cur.close(); c.close()
            return {'scopes': row[1] or ['read']}
        cur.close(); c.close()
        return None
    except Exception:
        pass
    # File fallback
    for k in _load_keys():
        if k.get('key_hash') == h and k.get('is_active', True):
            return {'scopes': k.get('scopes', ['read'])}
    return None


def mk_key(name, scopes):
    """Generate key, store in DB if available, always persist to file."""
    raw    = 'ctrv_' + secrets.token_urlsafe(32)
    prefix = raw[:12]
    h      = hashlib.sha256(raw.encode()).hexdigest()
    kid    = str(uuid.uuid4())
    # Try DB
    try:
        c = db(); cur = c.cursor()
        cur.execute(
            "INSERT INTO api_keys (key_hash, key_prefix, name, scopes) VALUES (%s,%s,%s,%s) RETURNING id",
            (h, prefix, name, scopes))
        kid = str(cur.fetchone()[0])
        c.commit(); cur.close(); c.close()
    except Exception:
        pass
    # Always save to file (survives DB restarts)
    keys = _load_keys()
    keys.append({'id': kid, 'key_hash': h, 'key_prefix': prefix,
                 'name': name, 'scopes': scopes, 'is_active': True,
                 'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ')})
    _save_keys(keys)
    return {'key': raw, 'id': kid, 'prefix': prefix}


# ─────────────────────────────────────────────────────────
#  Handler
# ─────────────────────────────────────────────────────────
class H(BaseHTTPRequestHandler):
    server_version = 'Controva-API/1.0'

    def log_message(self, *a):
        pass  # suppress default log

    # ── response helpers ─────────────────────────────────
    def _resp(self, code, data, extra=None):
        body = json.dumps(data, ensure_ascii=False, default=str).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type,X-API-Key,Authorization')
        self.send_header('X-API-Version', API_VER)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def ok(self, d, **kw):         self._resp(200, d, **kw)
    def created(self, d):          self._resp(201, d)
    def bad(self, m):              self._resp(400, {'error': m, 'status': 400})
    def unauth(self, m='Unauthorized. Provide X-API-Key header.'):
                                   self._resp(401, {'error': m, 'status': 401})
    def forbidden(self, m='Insufficient scope'):
                                   self._resp(403, {'error': m, 'status': 403})
    def notfound(self, m='Not found'):
                                   self._resp(404, {'error': m, 'status': 404})
    def ratelimited(self, r):
        self._resp(429, {'error': 'Rate limit exceeded', 'retry_after': r},
                   extra={'Retry-After': str(r)})
    def err(self, e):              self._resp(500, {'error': str(e), 'status': 500})

    def body(self):
        n = int(self.headers.get('Content-Length', 0))
        return json.loads(self.rfile.read(n) or b'{}') if n else {}

    def auth(self, scope='read'):
        """Authenticate + rate-limit. Returns scopes dict or None."""
        raw = (self.headers.get('X-API-Key') or
               self.headers.get('Authorization', '').replace('Bearer ', ''))
        if not raw:
            self.unauth(); return None
        info = validate_key(raw)
        if not info:
            self.unauth('Invalid or expired API key'); return None
        ok, rem, reset = _rate(raw)
        if not ok:
            self.ratelimited(reset); return None
        scopes = info['scopes']
        if scope and scope not in scopes and 'admin' not in scopes:
            self.forbidden(f'Scope "{scope}" required; your key has: {scopes}')
            return None
        return info

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type,X-API-Key,Authorization')
        self.end_headers()

    # ── GET ──────────────────────────────────────────────
    def do_GET(self):
        p  = self.path.split('?')[0].rstrip('/')
        qs = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
        segs = p.split('/')

        if p == f'{BASE}/health':
            return self.ok({'status': 'ok', 'version': API_VER,
                            'platform': 'Controva', 'ts': int(time.time())})

        if p == f'{BASE}/docs':
            return self.ok(self.docs())

        if p == f'{BASE}/leads':
            if self.auth('read') is None: return
            return self.list_leads(qs)

        # /api/v1/leads/:id
        if len(segs) == 5 and segs[3] == 'leads':
            if self.auth('read') is None: return
            return self.get_lead(segs[4])

        if p == f'{BASE}/jobs':
            if self.auth('read') is None: return
            return self.list_jobs()

        # /api/v1/jobs/:id
        if len(segs) == 5 and segs[3] == 'jobs':
            if self.auth('read') is None: return
            return self.get_job(segs[4])

        if p == f'{BASE}/analytics':
            if self.auth('read') is None: return
            return self.analytics()

        if p == f'{BASE}/analytics/searches':
            if self.auth('read') is None: return
            return self.search_history(qs)

        if p == f'{BASE}/keys':
            if self.auth('admin') is None: return
            return self.list_keys()

        return self.notfound(f'GET {p} — see {BASE}/docs')

    # ── POST ─────────────────────────────────────────────
    def do_POST(self):
        p    = self.path.split('?')[0].rstrip('/')
        segs = p.split('/')
        b    = self.body()

        if p == f'{BASE}/keys':
            return self.create_key(b)

        if p == f'{BASE}/search':
            if self.auth('write') is None: return
            return self.trigger_search(b)

        if p == f'{BASE}/enrich':
            if self.auth('write') is None: return
            return self.trigger_enrich()

        if p == f'{BASE}/leads/export':
            if self.auth('read') is None: return
            return self.export_leads(b)

        if p == f'{BASE}/webhooks/test':
            if self.auth('admin') is None: return
            return self.test_webhook(b)

        return self.notfound(f'POST {p} — see {BASE}/docs')

    # ── PUT ──────────────────────────────────────────────
    def do_PUT(self):
        p    = self.path.split('?')[0].rstrip('/')
        segs = p.split('/')
        b    = self.body()

        if len(segs) == 5 and segs[3] == 'leads':
            if self.auth('write') is None: return
            return self.update_lead(segs[4], b)

        return self.notfound(f'PUT {p} — see {BASE}/docs')

    # ── DELETE ───────────────────────────────────────────
    def do_DELETE(self):
        p    = self.path.split('?')[0].rstrip('/')
        segs = p.split('/')

        if len(segs) == 5 and segs[3] == 'leads':
            if self.auth('admin') is None: return
            return self.delete_lead(segs[4])

        if len(segs) == 5 and segs[3] == 'keys':
            if self.auth('admin') is None: return
            return self.revoke_key(segs[4])

        return self.notfound(f'DELETE {p} — see {BASE}/docs')

    # ─────────────────────────────────────────────────────
    #  Implementations
    # ─────────────────────────────────────────────────────

    def list_leads(self, qs):
        try:
            page     = max(1, int(qs.get('page', 1)))
            per_page = min(100, max(1, int(qs.get('per_page', 50))))
            offset   = (page - 1) * per_page
            niche    = qs.get('niche', '')
            city     = qs.get('city', '')
            status   = qs.get('status', '')
            has_email= qs.get('has_email', '')
            has_phone= qs.get('has_phone', '')
            min_score= qs.get('min_score', '')
            sort_by  = qs.get('sort_by', 'created_at')
            sort_dir = 'DESC' if qs.get('sort_dir', 'desc').lower() == 'desc' else 'ASC'

            COLS = {'created_at': 'l.created_at', 'score': 'l.ai_score',
                    'name': 'l.business_name', 'city': 'l.city'}
            order = COLS.get(sort_by, 'l.created_at')

            conds, params = ['1=1'], []
            if niche:      conds.append('LOWER(l.niche) LIKE %s');  params.append(f'%{niche.lower()}%')
            if city:       conds.append('LOWER(l.city)  LIKE %s');  params.append(f'%{city.lower()}%')
            if status:     conds.append('l.status = %s');           params.append(status)
            if has_email == '1':
                conds.append("EXISTS(SELECT 1 FROM contacts c WHERE c.lead_id=l.id AND COALESCE(c.email,'')!='')")
            if has_phone == '1':
                conds.append("COALESCE(l.phone,'')!=''")
            if min_score:  conds.append('l.ai_score >= %s');        params.append(int(min_score))

            where = ' AND '.join(conds)
            c = db(); cur = c.cursor()
            cur.execute(f'SELECT COUNT(*) FROM leads l WHERE {where}', params)
            total = cur.fetchone()[0]

            cur.execute(f"""
                SELECT l.id, l.business_name, l.phone, l.website, l.address,
                       l.city, l.niche, l.google_rating AS rating, l.review_count, l.has_website,
                       l.ai_score, l.icp_score, l.meeting_booked, l.status, l.source, l.created_at,
                       (SELECT c.email FROM contacts c
                        WHERE c.lead_id=l.id AND COALESCE(c.email,'')!='' LIMIT 1) AS email
                FROM leads l
                WHERE {where}
                ORDER BY {order} {sort_dir}
                LIMIT %s OFFSET %s
            """, params + [per_page, offset])
            cols  = [d[0] for d in cur.description]
            leads = [dict(zip(cols, r)) for r in cur.fetchall()]
            cur.close(); c.close()

            return self.ok({
                'data': leads,
                'pagination': {'page': page, 'per_page': per_page,
                               'total': total, 'pages': max(1, -(-total // per_page))},
                'filters': {'niche': niche, 'city': city, 'status': status}
            })
        except Exception as e:
            return self.err(e)

    def get_lead(self, lead_id):
        try:
            c = db(); cur = c.cursor()
            cur.execute("""
                SELECT l.id, l.business_name, l.phone, l.website, l.address,
                       l.city, l.country, l.niche, l.google_rating AS rating, l.review_count,
                       l.has_website, l.ai_score, l.icp_score, l.score_breakdown, l.score_reason,
                       l.meeting_booked, l.status, l.source, l.latitude, l.longitude, l.created_at
                FROM leads l WHERE l.id=%s
            """, (lead_id,))
            row = cur.fetchone()
            if not row:
                cur.close(); c.close()
                return self.notfound(f'Lead {lead_id} not found')
            cols = [d[0] for d in cur.description]
            lead = dict(zip(cols, row))

            cur.execute(
                "SELECT email, phone, linkedin_url, job_title AS title, source FROM contacts WHERE lead_id=%s",
                (lead_id,))
            cols2 = [d[0] for d in cur.description]
            lead['contacts'] = [dict(zip(cols2, r)) for r in cur.fetchall()]

            cur.execute("""
                SELECT status, pain_points, needs_summary, recommended_angle, researched_at
                FROM lead_research WHERE lead_id=%s
            """, (lead_id,))
            rr = cur.fetchone()
            if rr:
                lead['research'] = {'status': rr[0], 'pain_points': rr[1] or [],
                                    'needs_summary': rr[2] or '', 'recommended_angle': rr[3] or '',
                                    'researched_at': rr[4].isoformat() if rr[4] else None}

            cur.execute("""
                SELECT content FROM assets WHERE lead_id=%s AND asset_type='email_subject' LIMIT 1
            """, (lead_id,))
            subj_row = cur.fetchone()
            cur.execute("""
                SELECT content FROM assets WHERE lead_id=%s AND asset_type='email_body' LIMIT 1
            """, (lead_id,))
            body_row = cur.fetchone()
            if subj_row or body_row:
                lead['email_copy'] = {'subject': subj_row[0] if subj_row else '',
                                      'body': body_row[0] if body_row else ''}

            cur.close(); c.close()
            return self.ok({'data': lead})
        except Exception as e:
            return self.err(e)

    def update_lead(self, lead_id, body):
        allowed = {'status', 'notes', 'ai_score'}
        updates = {k: v for k, v in body.items() if k in allowed}
        if not updates:
            return self.bad(f'No valid fields. Allowed: {", ".join(allowed)}')
        try:
            c = db(); cur = c.cursor()
            parts = [f'{k}=%s' for k in updates]
            cur.execute(f"UPDATE leads SET {', '.join(parts)} WHERE id=%s RETURNING id",
                        list(updates.values()) + [lead_id])
            if not cur.fetchone():
                cur.close(); c.close()
                return self.notfound(f'Lead {lead_id} not found')
            c.commit(); cur.close(); c.close()
            return self.ok({'success': True, 'id': lead_id, 'updated': updates})
        except Exception as e:
            return self.err(e)

    def delete_lead(self, lead_id):
        try:
            c = db(); cur = c.cursor()
            cur.execute("DELETE FROM leads WHERE id=%s RETURNING id", (lead_id,))
            if not cur.fetchone():
                cur.close(); c.close()
                return self.notfound(f'Lead {lead_id} not found')
            c.commit(); cur.close(); c.close()
            return self.ok({'success': True, 'deleted_id': lead_id})
        except Exception as e:
            return self.err(e)

    def trigger_search(self, body):
        query = (body.get('query') or '').strip()
        if not query:
            return self.bad('query is required. E.g. "dentists in Chicago USA"')
        try:
            payload = json.dumps({
                'query':       query,
                'filter_mode': body.get('filter_mode', 'no_website'),
                'density':     body.get('density', 'standard'),
                'find_more':   bool(body.get('find_more', False)),
            }).encode()
            req = urllib.request.Request(
                f'{PLATFORM}/search', data=payload, method='POST',
                headers={'Content-Type': 'application/json',
                         'Authorization': 'Bearer ' + SERVICE_TOKEN})
            resp = urllib.request.urlopen(req, timeout=10)
            r = json.loads(resp.read().decode())
            jid = r.get('job_id', '')
            return self.created({
                'success':  True,
                'job_id':   jid,
                'parsed':   r.get('parsed'),
                'poll_url': f'{BASE}/jobs/{jid}',
                'message':  'Search started. Poll poll_url to track progress.'
            })
        except Exception as e:
            return self.err(e)

    def trigger_enrich(self):
        try:
            req = urllib.request.Request(
                f'{PLATFORM}/enrich', data=b'{}', method='POST',
                headers={'Content-Type': 'application/json',
                         'Authorization': 'Bearer ' + SERVICE_TOKEN})
            resp = urllib.request.urlopen(req, timeout=10)
            r = json.loads(resp.read().decode())
            jid = r.get('job_id', '')
            return self.created({
                'success':  True,
                'job_id':   jid,
                'poll_url': f'{BASE}/jobs/{jid}',
                'message':  'Enrichment started.'
            })
        except Exception as e:
            return self.err(e)

    def get_job(self, job_id):
        try:
            req = urllib.request.Request(
                f'{PLATFORM}/job/{job_id}',
                headers={'Authorization': 'Bearer ' + SERVICE_TOKEN})
            resp = urllib.request.urlopen(req, timeout=10)
            r = json.loads(resp.read().decode())
            return self.ok({
                'job_id':   job_id,
                'status':   r.get('status'),
                'progress': r.get('progress'),
                'log':      r.get('log', []),
                'results':  r.get('results'),
            })
        except Exception as e:
            return self.err(e)

    def list_jobs(self):
        try:
            req = urllib.request.Request(
                f'{PLATFORM}/jobs',
                headers={'Authorization': 'Bearer ' + SERVICE_TOKEN})
            resp = urllib.request.urlopen(req, timeout=5)
            return self.ok(json.loads(resp.read().decode()))
        except Exception:
            return self.ok({'data': [], 'note': 'Could not reach platform server'})

    def export_leads(self, body):
        try:
            niche  = body.get('niche', '')
            city   = body.get('city', '')
            status = body.get('status', '')
            limit  = min(5000, int(body.get('limit', 1000)))
            fmt    = body.get('format', 'json')

            conds, params = ['1=1'], []
            if niche:  conds.append('LOWER(niche) LIKE %s'); params.append(f'%{niche.lower()}%')
            if city:   conds.append('LOWER(city)  LIKE %s'); params.append(f'%{city.lower()}%')
            if status: conds.append('status = %s');          params.append(status)
            where = ' AND '.join(conds)

            c = db(); cur = c.cursor()
            cur.execute(f"""
                SELECT l.id, l.business_name, l.phone, l.website, l.address,
                       l.city, l.niche, l.rating, l.ai_score, l.status,
                       l.has_website, l.created_at,
                       (SELECT ct.email FROM contacts ct
                        WHERE ct.lead_id=l.id AND COALESCE(ct.email,'')!='' LIMIT 1) AS email
                FROM leads l WHERE {where}
                ORDER BY l.created_at DESC LIMIT %s
            """, params + [limit])
            cols  = [d[0] for d in cur.description]
            rows  = cur.fetchall()
            cur.close(); c.close()
            leads = [dict(zip(cols, r)) for r in rows]

            if fmt == 'csv':
                buf = io.StringIO()
                w   = csvlib.DictWriter(buf, fieldnames=cols)
                w.writeheader(); w.writerows(leads)
                raw = buf.getvalue().encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/csv')
                self.send_header('Content-Disposition', 'attachment; filename="controva_leads.csv"')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(raw)
                return

            return self.ok({'data': leads, 'count': len(leads),
                            'exported_at': int(time.time())})
        except Exception as e:
            return self.err(e)

    def analytics(self):
        try:
            c = db(); cur = c.cursor()
            cur.execute("SELECT COUNT(*) FROM leads"); total = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM leads WHERE has_website=FALSE"); no_web = cur.fetchone()[0]
            cur.execute("SELECT COUNT(DISTINCT email) FROM contacts WHERE COALESCE(email,'')!=''"); emails = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM leads WHERE status='sent'"); sent = cur.fetchone()[0]

            cur.execute("SELECT niche, COUNT(*) c FROM leads GROUP BY niche ORDER BY c DESC LIMIT 10")
            top_niches = [{'niche': r[0], 'count': r[1]} for r in cur.fetchall()]

            cur.execute("SELECT city, COUNT(*) c FROM leads GROUP BY city ORDER BY c DESC LIMIT 10")
            top_cities = [{'city': r[0], 'count': r[1]} for r in cur.fetchall()]

            cur.execute("""
                SELECT DATE_TRUNC('day', created_at) d, COUNT(*) c
                FROM leads WHERE created_at > NOW()-INTERVAL '30 days'
                GROUP BY d ORDER BY d
            """)
            daily = [{'date': str(r[0])[:10], 'count': r[1]} for r in cur.fetchall()]

            cur.close(); c.close()
            return self.ok({
                'totals': {
                    'total_leads': total,
                    'no_website':  no_web,
                    'emails_found': emails,
                    'emails_sent': sent,
                },
                'top_niches': top_niches,
                'top_cities': top_cities,
                'leads_last_30_days': daily,
            })
        except Exception as e:
            return self.err(e)

    def search_history(self, qs):
        try:
            limit = min(100, int(qs.get('limit', 20)))
            c = db(); cur = c.cursor()
            cur.execute("""
                SELECT query_text, niche, city, lead_count, served_from, searched_at
                FROM tenant_search_history ORDER BY searched_at DESC LIMIT %s
            """, (limit,))
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            cur.close(); c.close()
            return self.ok({'data': rows, 'count': len(rows)})
        except Exception as e:
            return self.err(e)

    def create_key(self, body):
        if body.get('master_secret') != MASTER_KEY:
            return self.unauth('Invalid master_secret')
        name   = (body.get('name') or 'unnamed').strip()
        scopes = [s for s in body.get('scopes', ['read'])
                  if s in ('read', 'write', 'admin')] or ['read']
        result = mk_key(name, scopes)
        if 'error' in result:
            return self.err(result['error'])
        return self.created({
            'success':  True,
            'api_key':  result['key'],   # shown ONCE
            'prefix':   result['prefix'],
            'name':     name,
            'scopes':   scopes,
            'warning':  'Store this key securely — it will not be shown again.',
            'usage':    f'X-API-Key: {result["key"]}',
        })

    def list_keys(self):
        try:
            c = db(); cur = c.cursor()
            cur.execute("""
                SELECT id, key_prefix, name, scopes, is_active,
                       last_used, request_count, created_at
                FROM api_keys ORDER BY created_at DESC
            """)
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            cur.close(); c.close()
            return self.ok({'data': rows, 'count': len(rows)})
        except Exception as e:
            return self.err(e)

    def revoke_key(self, key_id):
        try:
            c = db(); cur = c.cursor()
            cur.execute(
                "UPDATE api_keys SET is_active=FALSE WHERE id=%s RETURNING id", (key_id,))
            if not cur.fetchone():
                cur.close(); c.close()
                return self.notfound(f'Key {key_id} not found')
            c.commit(); cur.close(); c.close()
            return self.ok({'success': True, 'revoked_id': key_id})
        except Exception as e:
            return self.err(e)

    def test_webhook(self, body):
        url = (body.get('url') or '').strip()
        if not url:
            return self.bad('url is required')
        payload = json.dumps({
            'event': 'test', 'source': 'Controva API',
            'ts': int(time.time()),
            'data': {'message': 'Webhook test from Controva Platform'}
        }).encode()
        try:
            req = urllib.request.Request(
                url, data=payload, method='POST',
                headers={'Content-Type': 'application/json', 'X-Controva-Event': 'test'})
            resp = urllib.request.urlopen(req, timeout=10)
            return self.ok({'success': True, 'http_status': resp.status, 'url': url})
        except Exception as e:
            return self.ok({'success': False, 'error': str(e), 'url': url})

    def docs(self):
        return {
            'name': 'Controva Platform API',
            'version': API_VER,
            'base': BASE,
            'port': API_PORT,
            'auth': {
                'header': 'X-API-Key: YOUR_KEY',
                'create_key': f'POST {BASE}/keys  (body: master_secret, name, scopes)'
            },
            'scopes': {
                'read':  'List leads, get lead, analytics, export, poll jobs',
                'write': 'Trigger search, trigger enrich, update lead',
                'admin': 'Delete lead, manage keys, test webhooks'
            },
            'rate_limit': f'{RATE_LIMIT} req/min per key',
            'endpoints': {
                f'GET  {BASE}/health':              'Health check — no auth',
                f'GET  {BASE}/docs':                'This reference',
                f'POST {BASE}/keys':                'Create API key [master_secret]',
                f'GET  {BASE}/keys':                'List keys [admin]',
                f'DELETE {BASE}/keys/:id':          'Revoke key [admin]',
                f'GET  {BASE}/leads':               'List leads (page, per_page, niche, city, status, has_email, min_score, sort_by, sort_dir)',
                f'GET  {BASE}/leads/:id':           'Get lead + contacts + email copy',
                f'PUT  {BASE}/leads/:id':           'Update lead status/notes/score [write]',
                f'DELETE {BASE}/leads/:id':         'Delete lead [admin]',
                f'POST {BASE}/leads/export':        'Export JSON or CSV (niche, city, status, limit, format)',
                f'POST {BASE}/search':              'Start discovery search [write] (query, filter_mode, density)',
                f'GET  {BASE}/jobs':                'List recent search jobs',
                f'GET  {BASE}/jobs/:id':            'Poll job status & results',
                f'POST {BASE}/enrich':              'Trigger enrichment [write]',
                f'GET  {BASE}/analytics':           'Platform stats',
                f'GET  {BASE}/analytics/searches':  'Search history',
                f'POST {BASE}/webhooks/test':       'Test a webhook URL [admin]',
            },
            'quick_examples': {
                'create_key':   f'curl -X POST http://localhost:{API_PORT}{BASE}/keys -H "Content-Type: application/json" -d \'{{"master_secret":"{MASTER_KEY}","name":"my-app","scopes":["read","write"]}}\'',
                'search':       f'curl -X POST http://localhost:{API_PORT}{BASE}/search -H "X-API-Key: YOUR_KEY" -H "Content-Type: application/json" -d \'{{"query":"plumbers in Dallas USA"}}\'',
                'list_leads':   f'curl "http://localhost:{API_PORT}{BASE}/leads?city=dallas&per_page=20" -H "X-API-Key: YOUR_KEY"',
                'export_csv':   f'curl -X POST http://localhost:{API_PORT}{BASE}/leads/export -H "X-API-Key: YOUR_KEY" -H "Content-Type: application/json" -d \'{{"format":"csv","niche":"plumber"}}\' -o leads.csv',
                'analytics':    f'curl http://localhost:{API_PORT}{BASE}/analytics -H "X-API-Key: YOUR_KEY"',
            }
        }


# ─────────────────────────────────────────────────────────
#  Server
# ─────────────────────────────────────────────────────────
class Server(ThreadingMixIn, HTTPServer):
    daemon_threads = True

if __name__ == '__main__':
    ensure_tables()
    srv = Server(('0.0.0.0', API_PORT), H)
    print('=' * 62)
    print('  Controva Platform Public API  v1.0')
    print('=' * 62)
    print(f'  Listening  : http://0.0.0.0:{API_PORT}')
    print(f'  Health     : http://localhost:{API_PORT}{BASE}/health')
    print(f'  Docs       : http://localhost:{API_PORT}{BASE}/docs')
    print(f'  Platform   : {PLATFORM}')
    print()
    print('  Create first API key:')
    print(f'  curl -X POST http://localhost:{API_PORT}{BASE}/keys \\')
    print(f'       -H "Content-Type: application/json" \\')
    print(f'       -d \'{{"master_secret":"{MASTER_KEY}","name":"my-app","scopes":["read","write"]}}\'')
    print('=' * 62)
    srv.serve_forever()
