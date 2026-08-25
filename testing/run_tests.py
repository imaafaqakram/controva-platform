#!/usr/bin/env python3
"""
Controva Platform — Minimum-Cost Test Driver
Runs one shallow discovery search, limits the downstream pipeline to 3 leads,
chains every other tool against them. Estimated spend ~$0.20–0.40 total.
"""
import json, time, urllib.request, urllib.parse, sys, os, subprocess
from datetime import datetime

API = 'http://127.0.0.1:8080'
REPORT = {
    'started_at': datetime.utcnow().isoformat() + 'Z',
    'platform_url': API,
    'tests': [],
    'summary': {},
}

def http(method, path, body=None, timeout=240):
    url = API + path
    data = None
    headers = {'Content-Type': 'application/json'}
    if body is not None:
        data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode('utf-8', errors='replace')
            dt = round((time.time() - t0) * 1000)
            try:
                return r.status, json.loads(body), dt
            except Exception:
                return r.status, body, dt
    except urllib.error.HTTPError as e:
        dt = round((time.time() - t0) * 1000)
        try:
            return e.code, json.loads(e.read().decode()), dt
        except Exception:
            return e.code, str(e), dt
    except Exception as e:
        dt = round((time.time() - t0) * 1000)
        return 0, f'ERROR: {e}', dt

def record(name, method, path, status, response, ms, expected_status=200, snippet=True, cost_note=''):
    ok = (status == expected_status)
    if isinstance(response, dict):
        keys = list(response.keys())[:10]
        preview = {k: (response[k] if not isinstance(response[k], list) else f'<list len={len(response[k])}>')
                   for k in keys}
        if isinstance(response.get('leads'), list) and response['leads']:
            preview['_first_lead'] = response['leads'][0]
        if isinstance(response.get('results'), list) and response['results']:
            preview['_first_result'] = response['results'][0]
    else:
        preview = str(response)[:300]
    REPORT['tests'].append({
        'test': name,
        'endpoint': f'{method} {path}',
        'status_code': status,
        'duration_ms': ms,
        'pass': ok,
        'cost_note': cost_note,
        'response_preview': preview if snippet else 'omitted',
    })
    flag = 'PASS' if ok else 'FAIL'
    print(f'[{flag}] {name:<42} {status} {ms}ms  {cost_note}')
    return ok, response

def sql(query):
    """Run a SQL query as postgres for setup tasks."""
    r = subprocess.run(['sudo', '-u', 'postgres', 'psql', '-d', 'leadgen_db', '-tAc', query],
                       capture_output=True, text=True)
    return r.stdout.strip(), r.stderr.strip()

print('='*78)
print('CONTROVA PLATFORM — MINIMUM-COST FUNCTIONAL TEST')
print('='*78)

# ── PHASE 1: FREE health/auth/config ──────────────────────────────────────
print('\n--- PHASE 1: free endpoints (health, auth, config) ---')
record('health check', 'GET', '/health', *http('GET', '/health'), cost_note='FREE')
record('auth login', 'POST', '/auth/login',
       *http('POST', '/auth/login', {'username': 'admin', 'password': 'CHANGE_ME_BEFORE_DEPLOY'}), cost_note='FREE')
record('config read', 'GET', '/config', *http('GET', '/config'), cost_note='FREE')
record('api-keys masked view', 'GET', '/api-keys', *http('GET', '/api-keys'), cost_note='FREE')

# ── PHASE 2: BASELINE ANALYTICS (FREE) ────────────────────────────────────
print('\n--- PHASE 2: baseline analytics (DB only, free) ---')
record('stats (pre-search)', 'GET', '/stats', *http('GET', '/stats'), cost_note='FREE')
record('leads list (pre-search)', 'GET', '/leads', *http('GET', '/leads'), cost_note='FREE')

# ── PHASE 3: ONE PAID DISCOVERY (only Google Places spend) ───────────────
print('\n--- PHASE 3: ONE discovery search (~$0.085 Google Places) ---')
s, r, ms = http('POST', '/search', {
    'query': 'dental clinics in Cambridge UK',
    'density': 'low',
    'filter_mode': 'all',
})
ok, search_resp = record('natural-language search', 'POST', '/search', s, r, ms,
                         cost_note='~$0.085 (5 Places + 1 Gemini parse)')

# Fetch leads from DB
s, r, ms = http('GET', '/leads')
record('leads list (post-search)', 'GET', '/leads', s, r, ms, cost_note='FREE')
db_leads = r.get('leads', []) if isinstance(r, dict) else []
print(f'  -> {len(db_leads)} leads persisted in DB')

if not db_leads:
    print('No leads to drive downstream tests; aborting.')
    open('/tmp/leadgen-test/test_report.json', 'w').write(json.dumps(REPORT, indent=2, default=str))
    sys.exit(1)

# ── PHASE 4: limit enrichment scope to 3 leads (SQL setup) ───────────────
print('\n--- PHASE 4: limit pipeline scope to 3 leads (SQL setup) ---')
# Pick 3 leads without websites (the high-value targets), mark the rest as 'rejected'
out, err = sql("""
    WITH targets AS (
        SELECT id FROM leads WHERE has_website = FALSE LIMIT 3
    )
    UPDATE leads SET status='rejected'
    WHERE id NOT IN (SELECT id FROM targets) AND status='discovered'
    RETURNING id;
""")
not_targets = out.count('\n') + 1 if out else 0
print(f'  -> kept 3 leads as discovered, marked {not_targets} others as rejected (test isolation)')

out, err = sql("""
    SELECT id::text, business_name, city
    FROM leads WHERE status='discovered' LIMIT 3
""")
targets = [line.split('|') for line in out.split('\n') if line]
sample_ids = [t[0] for t in targets]
print(f'  -> target leads: {[t[1] for t in targets]}')

# ── PHASE 5: ENRICHMENT (Serper, 3 leads × ~$0.005 = ~$0.015) ────────────
print('\n--- PHASE 5: enrichment on 3 leads (~$0.015 Serper) ---')
s, r, ms = http('POST', '/enrich', {'provider': 'serper_only'}, timeout=240)
record('enrich (serper-only, 3 leads)', 'POST', '/enrich', s, r, ms,
       cost_note='~$0.015 Serper (3 leads)')

# ── PHASE 6: AI SCORING (Gemini batched, ~$0.005) ────────────────────────
print('\n--- PHASE 6: AI scoring (Gemini batched) ---')
s, r, ms = http('POST', '/score', {}, timeout=120)
record('Gemini scoring (enriched leads)', 'POST', '/score', s, r, ms,
       cost_note='~$0.005 Gemini')

# Look at one scored lead
out, _ = sql("SELECT business_name, ai_score, COALESCE(LEFT(score_reason,80),'') FROM leads WHERE ai_score IS NOT NULL LIMIT 1")
print(f'  -> example scored lead: {out}')

# ── PHASE 7: EMAIL COPY GENERATION (Claude, ~$0.01 per lead, no image) ───
print('\n--- PHASE 7: email copy generation (Claude, NO image) ---')
s, r, ms = http('POST', '/generate-assets', {
    'min_score': 0,            # generate for any scored lead
    'image_provider': 'none',  # do NOT spend on image generation
}, timeout=240)
record('generate email copy (no image)', 'POST', '/generate-assets', s, r, ms,
       cost_note='~$0.01-0.03 Claude (no image gen)')

out, _ = sql("SELECT asset_type, LEFT(content, 100) FROM assets ORDER BY created_at DESC LIMIT 3")
print(f'  -> latest assets:\n{out}')

# ── PHASE 8: HUNTER ALTERNATIVE — domain email finder ────────────────────
print('\n--- PHASE 8: email finder (Hunter alternative) ---')
# Pick a known public domain so we get reasonable results
s, r, ms = http('POST', '/find-emails', {'domain': 'stripe.com'})
record('find emails (stripe.com)', 'POST', '/find-emails', s, r, ms,
       cost_note='~$0.005 Serper')

# ── PHASE 9: APOLLO ALTERNATIVE — decision-maker finder ──────────────────
print('\n--- PHASE 9: people finder (Apollo alternative) ---')
s, r, ms = http('POST', '/find-people', {
    'company_name': 'Stripe',
    'titles': ['founder', 'ceo'],
}, timeout=60)
record('find decision-makers', 'POST', '/find-people', s, r, ms,
       cost_note='~$0.005 Serper')

# ── PHASE 10: EMAIL VERIFICATION (SMTP, FREE) ────────────────────────────
print('\n--- PHASE 10: email verification (SMTP, FREE) ---')
for email in ['support@stripe.com', 'definitely-fake-9k3jh@gmail.com']:
    s, r, ms = http('POST', '/verify-email', {'email': email}, timeout=30)
    record(f'verify {email[:40]}', 'POST', '/verify-email', s, r, ms, cost_note='FREE (SMTP)')

# ── PHASE 11: SEO — keyword research + SERP ──────────────────────────────
print('\n--- PHASE 11: SEO intelligence ---')
s, r, ms = http('POST', '/keywords', {'keyword': 'dental clinic Cambridge', 'location': 'Cambridge, UK'})
record('keyword research', 'POST', '/keywords', s, r, ms, cost_note='~$0.01 Serper')

s, r, ms = http('POST', '/serp', {'keyword': 'best dentist Cambridge', 'location': 'Cambridge, UK'})
record('SERP analysis', 'POST', '/serp', s, r, ms, cost_note='~$0.005 Serper')

# ── PHASE 12: INTENT SEARCH (bidirectional) ──────────────────────────────
print('\n--- PHASE 12: intent search ---')
s, r, ms = http('POST', '/intent-search', {
    'query': 'looking for dental marketing agency',
    'direction': 'demand',
    'recency_days': 30,
    'min_confidence': 55,
}, timeout=180)
record('intent search (demand side)', 'POST', '/intent-search', s, r, ms,
       cost_note='~$0.02 Serper + Gemini')

record('intent stats', 'GET', '/intent-stats', *http('GET', '/intent-stats'), cost_note='FREE')
record('intent leads list', 'GET', '/intent-leads', *http('GET', '/intent-leads'), cost_note='FREE')

# ── PHASE 13: FINAL ANALYTICS (FREE) ─────────────────────────────────────
print('\n--- PHASE 13: final analytics (FREE) ---')
record('stats (final)', 'GET', '/stats', *http('GET', '/stats'), cost_note='FREE')
record('stats-chart', 'GET', '/stats-chart', *http('GET', '/stats-chart'), cost_note='FREE')
record('outreach log', 'GET', '/outreach', *http('GET', '/outreach'), cost_note='FREE')

# ── PHASE 14: WORKFLOW + EXPORTS (FREE) ──────────────────────────────────
print('\n--- PHASE 14: workflow + exports (FREE) ---')
if sample_ids:
    record('approve a lead', 'POST', f'/lead/{sample_ids[0]}/approve',
           *http('POST', f'/lead/{sample_ids[0]}/approve', {}), cost_note='FREE')
    if len(sample_ids) > 1:
        record('reject a lead', 'POST', f'/lead/{sample_ids[1]}/reject',
               *http('POST', f'/lead/{sample_ids[1]}/reject', {}), cost_note='FREE')
    record('lead detail read-back', 'GET', f'/lead/{sample_ids[0]}',
           *http('GET', f'/lead/{sample_ids[0]}'), cost_note='FREE')

record('CSV export', 'GET', '/leads.csv', *http('GET', '/leads.csv'),
       cost_note='FREE', snippet=False)

# ── SUMMARY ──────────────────────────────────────────────────────────────
total = len(REPORT['tests'])
passed = sum(1 for t in REPORT['tests'] if t['pass'])
REPORT['summary'] = {
    'total_tests': total,
    'passed': passed,
    'failed': total - passed,
    'pass_rate_pct': round(passed / total * 100, 1) if total else 0,
    'finished_at': datetime.utcnow().isoformat() + 'Z',
    'estimated_spend_usd_range': '$0.20-0.40',
}
print('\n' + '='*78)
print(f"RESULT: {passed}/{total} passed ({REPORT['summary']['pass_rate_pct']}%)")
print('='*78)

with open('/tmp/leadgen-test/test_report.json', 'w') as f:
    json.dump(REPORT, f, indent=2, default=str)
print('\nReport saved: /tmp/leadgen-test/test_report.json')
