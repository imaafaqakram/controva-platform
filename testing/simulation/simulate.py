#!/usr/bin/env python3
"""Multi-tenant simulation / isolation test for server/leads_api.py.

Stdlib only. Creates two fresh client companies (+ a second user in company A)
with random suffixes, seeds data through the API (and psql for leads), then
runs an isolation matrix, admin-only checks, secret-leak scans and functional
checks.  Prints a PASS/FAIL table, writes last_report.json, exit 1 on any FAIL.

    python3 simulate.py --base http://127.0.0.1:8080 --admin-user admin --admin-pass localdev123
"""
import argparse
import hashlib, hmac, json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
MASK = "••••"
WEBHOOK_SECRET = "s3cret-value"
IMAP_SECRET = "imap-topsecret-"   # + suffix

RESULTS = []            # {section, name, status, detail}
CLIENT_RESPONSES = []   # (who, method, path, status, text) for every authenticated client call
ARGS = None


# --------------------------------------------------------------------------- http
def http(method, path, token=None, body=None, raw=False, timeout=60):
    url = ARGS.base.rstrip("/") + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, text = r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status, text = e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # connection problems
        status, text = 0, "CONNECTION ERROR: %s" % e
    js = None
    if not raw:
        try:
            js = json.loads(text)
        except Exception:
            js = None
    return status, text, js


class Client:
    def __init__(self, name, username, password, token=None):
        self.name, self.username, self.password, self.token = name, username, password, token
        self.log = []

    def call(self, method, path, body=None):
        st, text, js = http(method, path, self.token, body, raw=path.split("?")[0].endswith(".csv"))
        self.log.append((method, path, body, st, text[:600]))
        CLIENT_RESPONSES.append((self.name, method, path, st, text))
        return st, text, js

    def get(self, path):
        return self.call("GET", path)

    def post(self, path, body=None):
        return self.call("POST", path, {} if body is None else body)


def psql(sql):
    cmd = ["su", "postgres", "-c", 'psql -d leadgen_db -Atc "%s"' % sql.replace('"', '\\"')]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("psql failed: %s\n%s" % (sql, p.stderr))
    return p.stdout.strip()


def sq(s):
    return "'" + str(s).replace("'", "''") + "'"


# --------------------------------------------------------------------------- results
def check(section, name, ok, detail=""):
    RESULTS.append({"section": section, "name": name, "status": "PASS" if ok else "FAIL",
                    "detail": "" if ok else str(detail)[:1500]})
    return ok


def req_detail(client, idx=-1):
    m, p, b, st, text = client.log[idx]
    return "%s %s body=%s -> HTTP %s %s" % (m, p, json.dumps(b) if b is not None else "-", st, text[:400])


def refused(st, js):
    """A write/action counts as refused: 4xx, or JSON success:false / error without success."""
    if st in (400, 401, 403, 404, 409, 422):
        return True
    if st == 200 and isinstance(js, dict):
        if js.get("success") is False:
            return True
        if js.get("status") in ("not_found",):
            return True
    return False


# --------------------------------------------------------------------------- setup
def setup(sfx):
    ctx = {"sfx": sfx}
    S = "setup"
    st, _, js = http("POST", "/auth/login", None, {"username": ARGS.admin_user, "password": ARGS.admin_pass})
    if not check(S, "admin login", st == 200 and js and js.get("token"), "HTTP %s %s" % (st, js)):
        raise SystemExit("cannot continue without admin login")
    admin = Client("admin", ARGS.admin_user, ARGS.admin_pass, js["token"])
    ctx["admin"] = admin

    pw = "Pw-%s-xyz!" % sfx
    ua, ub, ua2 = "simA_%s" % sfx, "simB_%s" % sfx, "simA2_%s" % sfx
    ctx["companyA"], ctx["companyB"] = "AlphaCo-A-%s" % sfx, "BetaCo-B-%s" % sfx
    ctx.update(ua=ua, ub=ub, ua2=ua2, pw=pw)

    for u, comp in ((ua, ctx["companyA"]), (ub, ctx["companyB"])):
        st, _, js = admin.post("/users/create", {"username": u, "password": pw, "company_name": comp})
        check(S, "create user %s (company %s)" % (u, comp), st == 200 and js and js.get("success"), req_detail(admin))
    st, _, js = admin.get("/companies")
    comps = {c["name"]: c for c in (js or {}).get("companies", [])}
    ok = ctx["companyA"] in comps and ctx["companyB"] in comps
    check(S, "GET /companies lists both new companies", ok, req_detail(admin))
    if not ok:
        raise SystemExit("companies missing")
    ctx["tidA"], ctx["tidB"] = comps[ctx["companyA"]]["id"], comps[ctx["companyB"]]["id"]
    st, _, js = admin.post("/users/create", {"username": ua2, "password": pw, "tenant_id": ctx["tidA"]})
    check(S, "create second user in company A", st == 200 and js and js.get("success"), req_detail(admin))

    clients = {}
    for key, u in (("A", ua), ("B", ub), ("A2", ua2)):
        st, _, js = http("POST", "/auth/login", None, {"username": u, "password": pw})
        ok = st == 200 and js and js.get("token")
        check(S, "login %s" % u, ok, "HTTP %s %s" % (st, js))
        if not ok:
            raise SystemExit("login failed for " + u)
        clients[key] = Client(key, u, pw, js["token"])
    ctx.update(A=clients["A"], B=clients["B"], A2=clients["A2"])
    return ctx


def seed_company(ctx, key):
    """Seed one company through the API; returns dict of what was created."""
    sfx, c = ctx["sfx"], ctx[key]
    S = "seed"
    tid = ctx["tid" + key]
    d = {"key": key, "tid": tid, "company": ctx["company" + key]}
    today = date.today()
    ps, pe = (today - timedelta(days=5)).isoformat(), today.isoformat()
    d["ps"], d["pe"] = ps, pe

    # ICP
    d["icp_name"] = "ICP-%s-%s" % (key, sfx)
    st, _, js = c.post("/icp/save", {
        "name": d["icp_name"], "industries": "dental clinics", "geos": "Austin, TX", "keywords": "", "exclusions": "",
        "source_mix": "all", "min_lead_score": 60, "is_active": False, "push_to_crm": False,
        "offer": "Offer-%s-%s" % (key, sfx), "industry_template": "healthcare_clinics"})
    check(S, "%s: /icp/save" % key, st == 200 and js and js.get("success"), req_detail(c))
    d["icp_id"] = (js or {}).get("id")

    # Performance entries (hand-calculable)
    if key == "A":
        entries = [
            dict(channel="meta_ads", label="MetaA1-%s" % sfx, spend=500.00, leads=50, qualified_leads=20,
                 meetings_booked=8, meetings_attended=5, customers=2, revenue=4000),
            dict(channel="meta_ads", label="MetaA2-%s" % sfx, spend=250.50, leads=30, qualified_leads=10,
                 meetings_booked=4, meetings_attended=3, customers=1, revenue=1500),
            dict(channel="google_ads", label="GoogleA-%s" % sfx, spend=300, leads=10, qualified_leads=4,
                 meetings_booked=2, meetings_attended=1, customers=1, revenue=900),
            dict(channel="prospecting_costs", label="ExtraA-%s" % sfx, spend=120),
        ]
    else:
        entries = [dict(channel="meta_ads", label="MetaB-%s" % sfx, spend=999.99, leads=77, qualified_leads=33,
                        meetings_booked=9, meetings_attended=7, customers=5, revenue=77777)]
    d["perf_ids"] = []
    d["perf_labels"] = [e["label"] for e in entries]
    for e in entries:
        e.update(period_start=ps, period_end=pe)
        st, _, js = c.post("/performance/save", e)
        check(S, "%s: /performance/save %s" % (key, e["channel"]), st == 200 and js and js.get("success"), req_detail(c))
        d["perf_ids"].append((js or {}).get("id"))
    d["perf_entries"] = entries

    # Company settings
    d["imap_pass"] = IMAP_SECRET + key + sfx
    d["settings_company_name"] = "SettingsCo-%s-%s" % (key, sfx)
    st, _, js = c.post("/company/settings/save", {"settings": {
        "company_name": d["settings_company_name"], "company_address": "1 %s Street, Testville" % key,
        "from_name": "From-%s-%s" % (key, sfx), "brand_name": "Brand-%s-%s" % (key, sfx),
        "imap_pass": d["imap_pass"]}})
    check(S, "%s: /company/settings/save" % key, st == 200 and js and js.get("success"), req_detail(c))

    # CRM webhook connection
    d["crm_name"] = "CRM-%s-%s" % (key, sfx)
    st, _, js = c.post("/crm/connections/save", {"type": "webhook", "name": d["crm_name"], "config": {
        "webhook_url": "https://8.8.8.8/hook", "webhook_secret": WEBHOOK_SECRET}})
    check(S, "%s: /crm/connections/save" % key, st == 200 and js and js.get("success"), req_detail(c))
    d["crm_id"] = (js or {}).get("id")

    # Workflow
    d["wf_name"] = "WF-%s-%s" % (key, sfx)
    st, _, js = c.post("/workflows/save", {"name": d["wf_name"], "graph": {"nodes": [], "edges": []}})
    check(S, "%s: /workflows/save" % key, st == 200 and js and js.get("success"), req_detail(c))
    d["wf_id"] = (js or {}).get("id")

    # Leads via psql
    d["leads"] = []
    specs = [("Alpha" if key == "A" else "Beta", 80, "ready"), ("Alpha" if key == "A" else "Beta", 70, "scored"),
             ("Alpha" if key == "A" else "Beta", 40, "discovered")]
    batch = "batch-%s-%s" % (key, sfx)
    d["batch_id"] = batch
    for i, (pref, score, status) in enumerate(specs):
        name = "%sBiz-%s-%d-%s" % (pref, key, i, sfx)
        sql = ("INSERT INTO leads (place_id,business_name,niche,city,status,tenant_id,icp_id,icp_score,search_batch_id,country) "
               "VALUES (%s,%s,'dental',%s,%s,%s,%s,%s,%s,'US') RETURNING id" %
               (sq("pid-%s-%d-%s" % (key, i, sfx)), sq(name), sq("City%s" % key), sq(status), sq(tid),
                d["icp_id"], score, sq(batch)))
        lid = psql(sql).split("\n")[0].strip()
        psql("INSERT INTO contacts (lead_id, full_name, email, email_status) VALUES (%s,%s,%s,'valid')" %
             (sq(lid), sq("Contact %s%d %s" % (key, i, sfx)), sq("contact%s%d.%s@example-%s.test" % (key.lower(), i, sfx, key.lower()))))
        d["leads"].append({"id": lid, "name": name, "email": "contact%s%d.%s@example-%s.test" % (key.lower(), i, sfx, key.lower()),
                           "score": score})
    if key == "B":   # an 'enriched', unscored lead with an unverified email: target for the bulk jobs
        name = "BetaBiz-B-enriched-%s" % sfx
        lid = psql("INSERT INTO leads (place_id,business_name,niche,city,status,tenant_id,icp_id,country) VALUES (%s,%s,'dental','CityB','enriched',%s,%s,'US') RETURNING id"
                   % (sq("pid-B-enr-" + sfx), sq(name), sq(tid), d["icp_id"])).split("\n")[0].strip()
        em = "enr.%s@example-b.test" % sfx
        psql("INSERT INTO contacts (lead_id, full_name, email) VALUES (%s,%s,%s)" % (sq(lid), sq("Enr Contact " + sfx), sq(em)))
        d["leads"].append({"id": lid, "name": name, "email": em, "score": 0})
    # an intent (demand) lead, for /intent-leads
    iname = "Intent%s-%s" % (key, sfx)
    iid = psql("INSERT INTO leads (place_id,business_name,niche,city,status,tenant_id,lead_type) VALUES (%s,%s,'plumber','Town','discovered',%s,'demand') RETURNING id"
               % (sq("intent-%s-%s" % (key, sfx)), sq(iname), sq(tid))).split("\n")[0].strip()
    d["intent"] = {"id": iid, "name": iname}
    # outreach_log row on first lead
    d["outreach_subject"] = "Subject-%s-%s" % (key, sfx)
    psql("INSERT INTO outreach_log (tenant_id, lead_id, email_to, email_subject, status, sent_at) VALUES (%s,%s,%s,%s,'sent',NOW())"
         % (sq(tid), sq(d["leads"][0]["id"]), sq(d["leads"][0]["email"]), sq(d["outreach_subject"])))
    # active enrollment on 2nd lead (needs an existing sequence)
    seq = psql("SELECT id FROM sequences ORDER BY id LIMIT 1")
    d["enroll_lead"] = d["leads"][1]["id"]
    if seq:
        psql("INSERT INTO enrollments (lead_id, sequence_id, status, next_send_at) VALUES (%s,%s,'active', NOW() + INTERVAL '1 day')"
             % (sq(d["enroll_lead"]), seq))
    return d


# --------------------------------------------------------------------------- snapshots
def snapshot(tid, leads):
    """Everything belonging to company `tid`, straight from the DB."""
    ids = ",".join(sq(l["id"]) for l in leads)
    q = {
        "leads": "SELECT COALESCE(json_agg(t ORDER BY id),'[]') FROM (SELECT * FROM leads WHERE tenant_id=%s) t" % sq(tid),
        "contacts": "SELECT COALESCE(json_agg(t ORDER BY id),'[]') FROM (SELECT * FROM contacts WHERE lead_id IN (%s)) t" % ids,
        "icp": "SELECT COALESCE(json_agg(t ORDER BY id),'[]') FROM (SELECT * FROM icp_profiles WHERE tenant_id=%s) t" % sq(tid),
        "workflows": "SELECT COALESCE(json_agg(t ORDER BY id),'[]') FROM (SELECT * FROM workflows WHERE tenant_id=%s) t" % sq(tid),
        "crm": "SELECT COALESCE(json_agg(t ORDER BY id),'[]') FROM (SELECT * FROM crm_connections WHERE tenant_id=%s) t" % sq(tid),
        "perf": "SELECT COALESCE(json_agg(t ORDER BY id),'[]') FROM (SELECT * FROM channel_benchmarks WHERE tenant_id=%s) t" % sq(tid),
        "settings": "SELECT COALESCE(json_agg(t),'[]') FROM (SELECT * FROM tenant_settings WHERE tenant_id=%s) t" % sq(tid),
        "tenant": "SELECT COALESCE(json_agg(t),'[]') FROM (SELECT * FROM tenants WHERE id=%s) t" % sq(tid),
        "enrollments": "SELECT COALESCE(json_agg(t ORDER BY id),'[]') FROM (SELECT * FROM enrollments WHERE lead_id IN (%s)) t" % ids,
        "outreach": "SELECT COALESCE(json_agg(t ORDER BY id),'[]') FROM (SELECT * FROM outreach_log WHERE tenant_id=%s) t" % sq(tid),
    }
    return {k: json.loads(psql(v) or "[]") for k, v in q.items()}


def diff_snapshots(a, b):
    out = []
    for k in a:
        if a[k] != b[k]:
            if isinstance(a[k], list) and len(a[k]) != len(b[k]):
                out.append("%s: row count %d -> %d" % (k, len(a[k]), len(b[k])))
            else:
                for ra, rb in zip(a[k], b[k]):
                    if ra != rb:
                        ch = {f: (ra.get(f), rb.get(f)) for f in ra if ra.get(f) != rb.get(f)}
                        out.append("%s: changed %s" % (k, json.dumps(ch, default=str)[:300]))
    return out


# --------------------------------------------------------------------------- tests
def markers_of(B):
    m = {"B lead name %d" % i: l["name"] for i, l in enumerate(B["leads"])}
    m.update({"B lead id %d" % i: l["id"] for i, l in enumerate(B["leads"])})
    m.update({"B lead email %d" % i: l["email"] for i, l in enumerate(B["leads"])})
    m.update({
        "B intent lead name": B["intent"]["name"], "B intent lead id": B["intent"]["id"],
        "B ICP name": B["icp_name"], "B ICP offer": "Offer-B-" + B["sfx"],
        "B workflow name": B["wf_name"], "B CRM name": B["crm_name"],
        "B company name": B["company"], "B settings company_name": B["settings_company_name"],
        "B brand": "Brand-B-" + B["sfx"], "B from_name": "From-B-" + B["sfx"],
        "B tenant id": B["tid"], "B batch id": B["batch_id"], "B outreach subject": B["outreach_subject"],
        "B imap pass": B["imap_pass"], "B username": B["username"],
    })
    for i, l in enumerate(B["perf_labels"]):
        m["B channel label %d" % i] = l
    if B.get("job_id"):
        m["B job id"] = B["job_id"]
    return m


def test_isolation_reads(ctx, A, B):
    S = "isolation-read"
    cA = ctx["A"]
    marks = markers_of(B)
    own = {
        "/leads": A["leads"][0]["name"], "/leads.csv": A["leads"][0]["name"],
        "/stats": None, "/stats-chart": None,
        "/outreach": A["leads"][0]["name"],
        "/batches": A["batch_id"], "/icp": A["icp_name"], "/workflows": A["wf_name"],
        "/sequences": A["leads"][1]["name"], "/performance": A["perf_labels"][0],
        "/company/settings": A["settings_company_name"], "/crm/connections": A["crm_name"],
        "/intent-leads": A["intent"]["name"], "/intent-stats": None,
    }
    paths = ["/leads", "/leads.json", "/leads.csv", "/stats", "/stats-chart", "/outreach", "/batches", "/icp",
             "/workflows", "/sequences", "/performance", "/company/settings", "/crm/connections",
             "/intent-leads", "/intent-leads.csv", "/intent-stats", "/config",
             "/lead/" + B["leads"][0]["id"], "/lead/" + B["intent"]["id"],
             "/company/settings?tenant_id=" + B["tid"], "/performance?tenant_id=" + B["tid"],
             "/leads?tenant_id=" + B["tid"], "/icp?tenant_id=" + B["tid"],
             "/crm/connections?tenant_id=" + B["tid"]]
    if B.get("job_id"):
        paths.append("/job/" + B["job_id"])
    for p in paths:
        st, text, js = cA.get(p)
        leaked = [k for k, v in marks.items() if v and v in text]
        # B's imap pass masked form is not a leak; only flag the clear value (already in markers)
        check(S, "A GET %s hides all B data" % p, not leaked,
              "leaked %s :: %s" % (leaked, req_detail(cA)))
        base = p.split("?")[0]
        if p == base and base in own and own[base]:
            check(S, "A GET %s shows A's own data (control)" % p, own[base] in text,
                  "expected %r :: %s" % (own[base], req_detail(cA)))
    # direct B lead fetch must be 404 and not 200
    st, text, js = cA.get("/lead/" + B["leads"][0]["id"])
    check(S, "A GET /lead/<B id> is 404", st == 404, req_detail(cA))
    st, text, js = cA.get("/lead/" + B["intent"]["id"])
    check(S, "A GET /lead/<B intent id> is 404", st == 404, req_detail(cA))
    if B.get("job_id"):
        st, text, js = cA.get("/job/" + B["job_id"])
        check(S, "A GET /job/<B job> reports not_found (no log/progress)",
              st in (403, 404) or (isinstance(js, dict) and js.get("status") == "not_found" and "log" not in js),
              req_detail(cA))
    # settings must be A's own even when tenant_id=B is requested
    st, text, js = cA.get("/company/settings?tenant_id=" + B["tid"])
    check(S, "A GET /company/settings?tenant_id=B returns A's own tenant",
          st == 200 and js and js.get("tenant_id") == A["tid"], req_detail(cA))
    # counts agree with DB
    st, _, js = cA.get("/leads")
    got = {l.get("id") for l in (js or {}).get("leads", [])}
    want = {l["id"] for l in A["leads"]}
    check(S, "A /leads returns exactly A's non-intent leads",
          want <= got and not (got - want - {A["intent"]["id"]}), "extra=%s missing=%s" % (got - want, want - got))
    # B sanity: B sees B's data (control that the markers are real)
    cB = ctx["B"]
    st, text, js = cB.get("/leads")
    check(S, "B GET /leads shows B's leads (control)", all(l["name"] in text for l in B["leads"]), req_detail(cB))
    st, text, js = cB.get("/icp")
    check(S, "B GET /icp shows B's ICP (control)", B["icp_name"] in text, req_detail(cB))
    # A2 (same company as A) should see A's data
    cA2 = ctx["A2"]
    st, text, js = cA2.get("/leads")
    check(S, "A2 (same company) sees A's leads", all(l["name"] in text for l in A["leads"]), req_detail(cA2))
    check(S, "A2 (same company) does not see B", not any(v in text for v in marks.values() if v), req_detail(cA2))
    st, text, js = cA2.get("/crm/connections")
    check(S, "A2 /crm/connections hides B", B["crm_name"] not in text, req_detail(cA2))


def test_isolation_writes(ctx, A, B):
    S = "isolation-write"
    cA = ctx["A"]
    before = snapshot(B["tid"], B["leads"] + [{"id": B["intent"]["id"]}])
    bl = B["leads"][0]["id"]
    bl2 = B["leads"][1]["id"]
    bl3 = B["leads"][2]["id"]
    cases = [
        ("POST", "/lead/%s/send" % bl, {}),
        ("POST", "/lead/%s/approve" % bl, {}),
        ("POST", "/lead/%s/reject" % bl, {}),
        ("POST", "/lead/%s/outcome" % bl, {"meeting_booked": True, "deal_stage": "won", "deal_value": 1}),
        ("POST", "/lead/%s/erase" % bl3, {}),
        ("POST", "/lead/%s/regenerate-email" % bl, {"instructions": "x"}),
        ("POST", "/lead/%s/research" % bl, {}),
        ("POST", "/lead/%s/generate-mockup" % bl, {}),
        ("POST", "/leads/delete", {"lead_ids": [bl2, bl3, B["intent"]["id"]]}),
        ("POST", "/icp/save", {"id": B["icp_id"], "name": "HACKED-ICP", "industries": "x", "geos": "x", "keywords": "",
                               "exclusions": "", "source_mix": "all", "min_lead_score": 1, "is_active": True,
                               "push_to_crm": False, "offer": "HACKED", "industry_template": "healthcare_clinics"}),
        ("POST", "/icp/delete", {"id": B["icp_id"]}),
        ("POST", "/icp/run", {"id": B["icp_id"]}),
        ("POST", "/workflows/save", {"id": B["wf_id"], "name": "HACKED-WF", "graph": {"nodes": [{"x": 1}], "edges": []}}),
        ("POST", "/workflows/%s/delete" % B["wf_id"], {}),
        ("POST", "/workflows/run", {"id": B["wf_id"]}),
        ("POST", "/crm/connections/save", {"id": B["crm_id"], "type": "webhook", "name": "HACKED-CRM",
                                           "config": {"webhook_url": "https://8.8.4.4/evil", "webhook_secret": "evil"}}),
        ("POST", "/crm/connections/%s/delete" % B["crm_id"], {}),
        ("POST", "/crm/push", {"connection_id": B["crm_id"]}),
        ("POST", "/crm/push", {"connection_id": B["crm_id"], "lead_ids": [bl]}),
        ("POST", "/crm/push", {"connection_id": A["crm_id"], "lead_ids": [bl]}),   # A's conn, B's lead
        ("POST", "/performance/delete", {"id": B["perf_ids"][0]}),
        ("POST", "/performance/save", dict(B["perf_entries"][0], id=B["perf_ids"][0], label="HACKED-PERF", spend=1)),
        ("POST", "/sequence/enroll", {"lead_id": bl}),
        ("POST", "/sequence/enroll", {"lead_ids": [bl, bl3]}),
        ("POST", "/sequence/stop", {"lead_id": B["enroll_lead"]}),
        ("POST", "/batch/%s/delete" % B["batch_id"], {}),
        ("POST", "/intent-leads/%s/delete" % B["intent"]["id"], {}),
        ("POST", "/company/settings/save?tenant_id=" + B["tid"], {"tenant_id": B["tid"], "settings": {
            "company_name": "HACKED-CO", "brand_name": "HACKED-BRAND", "from_name": "HACKED"},
            "company_display_name": "HACKED-DISPLAY"}),
    ]
    if B.get("job_id"):
        cases.append(("POST", "/job/%s/cancel" % B["job_id"], {}))
    for m, p, b in cases:
        st, text, js = cA.call(m, p, b)
        ok = refused(st, js)
        # settings/save is "refused" by design if it acts on A's own company; handled below
        if p.startswith("/company/settings/save"):
            continue
        # these endpoints answer success:true with deleted:0 for non-owned ids (batch delete / leads delete)
        if p.startswith("/batch/") or p == "/leads/delete":
            ok = ok or (st == 200 and js and (js.get("deleted") in (0, [], None)))
        if p == "/sequence/enroll":
            ok = ok or (st == 200 and js and js.get("enrolled") == 0)
        if p == "/crm/push":
            ok = ok or (st == 200 and js and js.get("count", 0) == 0)
        if p == "/intent-leads/%s/delete" % B["intent"]["id"]:
            ok = ok or (st == 200 and js and js.get("success") is False)
        check(S, "A %s %s refused" % (m, re.sub(r"[0-9a-f]{8}-[0-9a-f-]{27}", "<id>", p)[:70]), ok, req_detail(cA))

    # company settings: tenant_id=B must act on A's own company only and leave B untouched
    snap_after = snapshot(B["tid"], B["leads"] + [{"id": B["intent"]["id"]}])
    # By design a client's tenant_id is ignored: the save lands on the CALLER's own company.
    # Assert exactly that (A's own company changed, B's did not), then restore A.
    st, text, js = ctx["A"].get("/company/settings")
    check(S, "settings/save with tenant_id=B acted only on A's own company (A shows the new values)",
          js and js.get("tenant_id") == A["tid"] and js.get("company_name") == "HACKED-DISPLAY"
          and (js.get("settings") or {}).get("brand_name") == "HACKED-BRAND", req_detail(ctx["A"]))
    ctx["A"].post("/company/settings/save", {"company_display_name": A["company"], "settings": {
        "company_name": A["settings_company_name"], "brand_name": "Brand-A-" + A["sfx"], "from_name": "From-A-" + A["sfx"]}})
    diffs = diff_snapshots(before, snap_after)
    check(S, "B's data unchanged in DB after all cross-tenant write attempts (leads, contacts, ICP, workflow, CRM, perf, settings, tenant, enrollments, outreach)",
          not diffs, "; ".join(diffs))
    # also confirm through B's own API
    cB = ctx["B"]
    st, text, js = cB.get("/icp")
    check(S, "B re-read /icp: name intact, no HACKED", B["icp_name"] in text and "HACKED" not in text, req_detail(cB))
    st, text, js = cB.get("/workflows")
    check(S, "B re-read /workflows: intact", B["wf_name"] in text and "HACKED" not in text, req_detail(cB))
    st, text, js = cB.get("/crm/connections")
    check(S, "B re-read /crm/connections: intact", B["crm_name"] in text and "HACKED" not in text and "evil" not in text, req_detail(cB))
    st, text, js = cB.get("/company/settings")
    check(S, "B re-read /company/settings: intact", B["settings_company_name"] in text and "HACKED" not in text, req_detail(cB))
    st, text, js = cB.get("/leads")
    check(S, "B re-read /leads: all 3 leads present", all(l["name"] in text for l in B["leads"]), req_detail(cB))
    st, text, js = cB.get("/performance")
    check(S, "B re-read /performance: label intact, no HACKED", B["perf_labels"][0] in text and "HACKED" not in text, req_detail(cB))
    if B.get("job_id"):
        st, text, js = cB.get("/job/" + B["job_id"])
        check(S, "B's job not cancelled by A", js and js.get("status") != "cancelled" and not js.get("cancelled"), req_detail(cB))
    # A's data also unchanged by its own failed attempts
    st, text, js = ctx["A"].get("/icp")
    check(S, "A's ICP not modified by cross-tenant attempts", A["icp_name"] in text and "HACKED" not in text, req_detail(ctx["A"]))


def test_bulk_jobs(ctx, A, B):
    """Client-triggered bulk jobs must only touch the caller's company."""
    S = "bulk-jobs"
    cA = ctx["A"]
    before = snapshot(B["tid"], B["leads"] + [{"id": B["intent"]["id"]}])
    jobs = []
    for p, b in [("/enrich", {}), ("/score", {}), ("/verify-emails", {}), ("/reenrich-missing-emails", {}),
                 ("/research/queue", {"min_score": 0}), ("/generate-assets", {"min_score": 0}), ("/check-replies", {})]:
        st, text, js = cA.post(p, b)
        check(S, "A POST %s accepted (200, job or nothing_to_do)" % p, st == 200, req_detail(cA))
        if js and js.get("job_id"):
            jobs.append((p, js["job_id"]))
    deadline = time.time() + 60
    for p, jid in jobs:
        while time.time() < deadline:
            st, _, js = cA.get("/job/" + jid)
            if js and js.get("status") not in ("running", "queued", None):
                break
            time.sleep(0.5)
        # job logs/results returned to A must not name B's leads
        st, text, js = cA.get("/job/" + jid)
        leaked = [v for v in (l["name"] for l in B["leads"]) if v in text] + [e["email"] for e in B["leads"] if e["email"] in text]
        check(S, "A's job %s output does not mention B's leads" % p, not leaked, "%s :: %s" % (leaked, req_detail(cA)))
    time.sleep(1.0)
    after = snapshot(B["tid"], B["leads"] + [{"id": B["intent"]["id"]}])
    diffs = diff_snapshots(before, after)
    check(S, "B's data unchanged after A ran /enrich /score /verify-emails /reenrich-missing-emails /research/queue /generate-assets /check-replies",
          not diffs, "; ".join(diffs))


def test_admin_only(ctx, A, B):
    S = "admin-only"
    cA, cB = ctx["A"], ctx["B"]
    for p in ["/users", "/companies", "/api-keys", "/sending-domains", "/cost-stats", "/admin/activity", "/n8n/workflows"]:
        st, text, js = cA.get(p)
        check(S, "client GET %s refused (403)" % p, st == 403, req_detail(cA))
    posts = [("/users/create", {"username": "evil%s" % ctx["sfx"], "password": "longenough123", "company_name": "evil"}),
             ("/api-keys/update", {"key": "serper_key", "value": "x"}),
             ("/api-keys/bulk-update", {"pairs": {"serper_key": "x"}}),
             ("/sending-domains/save", {"domain": "evil.test", "from_email": "a@evil.test"}),
             ("/test-email", {"to": "a@example.com"}),
             ("/sequence/run", {}),
             ("/send-email", {"to": "a@example.com", "subject": "s", "body": "b"}),
             ("/config", {"client_brand_name": "HACKED"}),
             ("/users/%s/delete" % ctx["ub"], {}),
             ("/users/%s/reset-password" % ctx["ub"], {"password": "hackedpassword1"})]
    for p, b in posts:
        st, text, js = cA.post(p, b)
        check(S, "client POST %s refused (403)" % p, st == 403, req_detail(cA))
    # evil user should not exist / B's password unchanged
    st, _, js = http("POST", "/auth/login", None, {"username": "evil" + ctx["sfx"], "password": "longenough123"})
    check(S, "client-created user does not exist", st != 200, "HTTP %s %s" % (st, js))
    st, _, js = http("POST", "/auth/login", None, {"username": ctx["ub"], "password": ctx["pw"]})
    check(S, "B can still log in with original password after A's reset attempt", st == 200, "HTTP %s %s" % (st, js))
    # /config GET for client: no internal config
    st, text, js = cA.get("/config")
    check(S, "client GET /config returns only cosmetic keys",
          st == 200 and js and set(js) <= {"client_brand_name", "client_brand_color", "calendly_url", "client_footer_text"},
          req_detail(cA))
    # admin sees both companies (sanity)
    st, text, js = ctx["admin"].get("/companies")
    check(S, "admin GET /companies sees A and B", A["company"] in text and B["company"] in text, req_detail(ctx["admin"]))
    # unauthenticated
    public_get = {"/", "/dashboard", "/index.html", "/health"}
    unauth_gets = ["/leads", "/leads.csv", "/stats", "/stats-chart", "/outreach", "/batches", "/icp", "/workflows",
                   "/sequences", "/performance", "/company/settings", "/crm/connections", "/intent-leads",
                   "/intent-stats", "/config", "/users", "/companies", "/api-keys", "/sending-domains",
                   "/cost-stats", "/admin/activity", "/lead/" + A["leads"][0]["id"], "/job/abc", "/n8n/workflows",
                   "/research-history/1"]
    for p in unauth_gets:
        st, text, js = http("GET", p)
        check(S, "unauthenticated GET %s -> 401" % p, st == 401, "HTTP %s %s" % (st, text[:200]))
    unauth_posts = ["/enrich", "/icp/save", "/lead/%s/outcome" % A["leads"][0]["id"], "/leads/delete", "/users/create",
                    "/config", "/crm/push", "/performance/save", "/workflows/save", "/company/settings/save",
                    "/api-keys/update", "/send-email", "/sequence/run", "/auth/change-password"]
    for p in unauth_posts:
        st, text, js = http("POST", p, None, {})
        check(S, "unauthenticated POST %s -> 401" % p, st == 401, "HTTP %s %s" % (st, text[:200]))
    st, text, js = http("GET", "/leads", "not-a-real-token")
    check(S, "bogus bearer token GET /leads -> 401", st == 401, "HTTP %s %s" % (st, text[:200]))
    for p in public_get:
        st, text, js = http("GET", p, None, None, raw=True)
        check(S, "public GET %s reachable without auth" % p, st == 200, "HTTP %s" % st)
    # logout invalidates a token (use a throwaway login)
    st, _, js = http("POST", "/auth/login", None, {"username": ctx["ua2"], "password": ctx["pw"]})
    if st == 200:
        tmp = js["token"]
        http("POST", "/auth/logout", tmp, {})
        st2, _, _ = http("GET", "/leads", tmp)
        check(S, "token invalid after /auth/logout", st2 == 401, "HTTP %s" % st2)


def walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, path + "." + str(k))
            yield path + "." + str(k), k, v
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, "%s[%d]" % (path, i))


SECRET_KEY_RE = re.compile(r"(imap_pass|trigger_secret|webhook_secret|api_token|_secret$|_password$|passw|api_key|apikey|"
                           r"_key$|secret_key|private_key|access_token|pwhash|salt)", re.I)


def test_secrets(ctx, A, B):
    S = "secrets"
    admin = ctx["admin"]
    # gather real secret values from the admin config
    secret_vals = set()
    st, text, js = admin.get("/config")
    if isinstance(js, dict):
        for k, v in js.items():
            if isinstance(v, str) and len(v) >= 6 and re.search(r"key|pass|secret|token", k, re.I):
                secret_vals.add((k, v))
    st, text, js = admin.get("/crm/connections")
    # crm connection secrets in clear from the DB (admin API masks too)
    for row in psql("SELECT config::text FROM crm_connections").split("\n"):
        try:
            cfg = json.loads(row)
        except Exception:
            continue
        for k, v in cfg.items():
            if isinstance(v, str) and len(v) >= 6 and re.search(r"secret|token|key|pass", k, re.I):
                secret_vals.add(("crm." + k, v))
    for row in psql("SELECT settings->>'imap_pass' FROM tenant_settings WHERE settings ? 'imap_pass'").split("\n"):
        if row and len(row) >= 6:
            secret_vals.add(("tenant.imap_pass", row))
    # ignore generic/short placeholder values
    secret_vals = {(k, v) for k, v in secret_vals if v not in ("", "none", "default")}

    client_calls = [c for c in CLIENT_RESPONSES if c[0] in ("A", "A2", "B") and c[3] != 0]
    check(S, "collected %d client responses to scan" % len(client_calls), len(client_calls) > 20, "too few responses")
    leaked_full = []
    for who, m, p, st, text in client_calls:
        if p.startswith("/auth/login"):
            continue
        if WEBHOOK_SECRET in text:
            leaked_full.append("%s %s %s contains webhook secret in full" % (who, m, p))
        for k, v in secret_vals:
            if v in text:
                leaked_full.append("%s %s %s contains value of %s" % (who, m, p, k))
    check(S, "no client response contains webhook secret '%s' or any server/tenant secret value in clear" % WEBHOOK_SECRET,
          not leaked_full, "; ".join(sorted(set(leaked_full))[:10]))

    # structural: secret-looking keys with non-empty, non-masked values
    bad = []
    for who, m, p, st, text in client_calls:
        if p.startswith("/auth/login") or p.endswith(".csv"):
            continue
        try:
            js = json.loads(text)
        except Exception:
            continue
        for path, k, v in walk(js):
            if k in ("inbound_token", "token"):
                continue
            if SECRET_KEY_RE.search(str(k)) and isinstance(v, str) and v and not v.startswith(MASK):
                bad.append("%s %s %s: %s=%r" % (who, m, p, path, v[:30]))
    check(S, "no secret-named field returned unmasked to a client", not bad, "; ".join(sorted(set(bad))[:10]))

    # explicit: own secrets are masked, not blank-hidden-lost
    st, text, js = ctx["A"].get("/crm/connections")
    cfg = ((js or {}).get("connections") or [{}])[0].get("config", {})
    check(S, "A's own webhook_secret returned masked ('%s...alue')" % MASK,
          cfg.get("webhook_secret", "").startswith(MASK) and WEBHOOK_SECRET not in text, req_detail(ctx["A"]))
    st, text, js = ctx["A"].get("/company/settings")
    check(S, "A's own imap_pass returned masked", A["imap_pass"] not in text and MASK in json.dumps(js, ensure_ascii=False) or
          A["imap_pass"] not in text, req_detail(ctx["A"]))
    # the masked connection round-trip must not clobber the stored secret
    cid = A["crm_id"]
    cfg2 = dict(cfg)
    st, _, js2 = ctx["A"].post("/crm/connections/save", {"id": cid, "type": "webhook", "name": A["crm_name"], "config": cfg2})
    stored = psql("SELECT config->>'webhook_secret' FROM crm_connections WHERE id=%s" % cid)
    check(S, "masked round-trip save keeps A's real webhook_secret", stored == WEBHOOK_SECRET, "stored=%r %s" % (stored, req_detail(ctx["A"])))
    # api keys / ISO: client calls to key endpoints returned 403 with no key material
    for p in ("/api-keys", "/config"):
        st, text, js = ctx["A"].get(p)
        low = text.lower()
        check(S, "client GET %s exposes no imap_pass/trigger_secret/api key fields" % p,
              "imap_pass" not in low and "trigger_secret" not in low and "api_key" not in low and "serper_key" not in low,
              req_detail(ctx["A"]))
    # lead detail of own lead: no secret keys
    st, text, js = ctx["A"].get("/lead/" + A["leads"][0]["id"])
    check(S, "A GET /lead/<own> returns 200 with no secret fields", st == 200 and "imap_pass" not in text and "trigger_secret" not in text,
          req_detail(ctx["A"]))


def test_hardening(ctx, A, B):
    """The fixes from the security audit stay fixed."""
    S = "hardening"
    cA = ctx["A"]
    # tokens only in headers (CSV links excepted); stored hashed; PBKDF2 passwords
    st, _, _ = http("GET", "/leads?token=" + cA.token)
    check(S, "?token= refused on a normal route", st == 401, "HTTP %s" % st)
    st, _, _ = http("GET", "/leads.csv?token=" + cA.token, raw=True)
    check(S, "?token= still works for CSV download", st == 200, "HTTP %s" % st)
    raw = psql("SELECT COUNT(*) FROM auth_sessions WHERE token = %s" % sq(cA.token))
    check(S, "session token not stored in clear", raw == "0", "rows with raw token: %s" % raw)
    h = psql("SELECT pwhash FROM auth_users WHERE username = %s" % sq(ctx["ua"].lower()))
    check(S, "new passwords stored as PBKDF2", h.startswith("pbkdf2_sha256$"), h[:20])
    # Calendly: shared URL retired; company URL honours its signing key
    st, _, _ = http("POST", "/webhook/calendly", None, {"payload": {"invitee": {"email": "x@y.example"}}})
    check(S, "legacy unauthenticated Calendly webhook retired", st == 410, "HTTP %s" % st)
    cA.post("/company/settings/save", {"settings": {"calendly_signing_key": "sim-cal-key"}})
    st, _, js = cA.get("/company/settings")
    tok = ((js or {}).get("calendly_webhook_url") or "").rsplit("/", 1)[-1]
    body = json.dumps({"payload": {"invitee": {"email": "nobody@sim.example"}}}).encode()
    def cal(sig):
        req = urllib.request.Request(ARGS.base.rstrip("/") + "/webhook/calendly/" + tok, data=body, method="POST",
                                     headers=dict({"Content-Type": "application/json"}, **sig))
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()
    st, text = cal({})
    check(S, "company Calendly webhook refuses an unsigned booking", st == 401, "HTTP %s %s" % (st, text))
    t = str(int(time.time()))
    sig = hmac.new(b"sim-cal-key", t.encode() + b"." + body, hashlib.sha256).hexdigest()
    st, text = cal({"Calendly-Webhook-Signature": "t=%s,v1=%s" % (t, sig)})
    check(S, "signed booking accepted, reply reveals no match count",
          st == 200 and "matched" not in text, "HTTP %s %s" % (st, text))
    # clients don't see admin-only settings; theme validated
    st, _, js = cA.get("/company/settings")
    keys = set(((js or {}).get("settings") or {}).keys())
    check(S, "client sees no admin-only company settings", not keys & {"daily_send_limit", "monthly_spend_limit"}, keys)
    st, _, js = cA.post("/company/settings/save", {"settings": {"theme": "neon"}})
    check(S, "unknown theme refused", st == 400, req_detail(cA))
    cA.post("/company/settings/save", {"settings": {"theme": "emerald"}})
    st, _, js = cA.get("/config")
    check(S, "company theme reaches its users (/config)", (js or {}).get("client_theme") == "emerald", js)
    # outbound requests stay public
    st, _, js = cA.post("/crm/connections/save", {"type": "webhook", "name": "metadata",
                                                  "config": {"webhook_url": "https://169.254.169.254/latest"}})
    check(S, "client webhook to cloud metadata refused", refused(st, js), req_detail(cA))
    # raw server errors are not shown to clients
    st, text, _ = cA.get("/research-history/notanumber")
    check(S, "client 5xx shows a generic message", st >= 500 and "invalid literal" not in text, "HTTP %s %s" % (st, text))
    # paid-API guards: CSV size, rate, monthly budget
    st, _, js = cA.post("/enrich-csv", {"rows": [{"company_name": "c%d" % i} for i in range(501)]})
    check(S, "CSV enrich over 500 rows refused", st == 400, req_detail(cA))
    codes = [cA.post("/keywords", {"keyword": ""})[0] for _ in range(25)]
    check(S, "paid actions rate-limited per company", 429 in codes, codes)
    psql("INSERT INTO api_usage (provider, endpoint, cost, username) VALUES ('serper', 'sim_budget', 5000, %s)" % sq(ctx["ua"].lower()))
    try:
        st, _, js = cA.post("/keywords", {"keyword": "roofers"})
        check(S, "company over its monthly API budget is stopped", st == 402, req_detail(cA))
        st, _, js = ctx["B"].post("/keywords", {"keyword": ""})
        check(S, "another company's budget is unaffected", st != 402, req_detail(ctx["B"]))
    finally:
        psql("DELETE FROM api_usage WHERE endpoint = 'sim_budget'")


def perf_expected(A, with_outcome=False):
    """Hand-calculated expectations from what was seeded for company A."""
    e = [x for x in A["perf_entries"] if x["channel"] == "meta_ads"]
    spend = sum(x["spend"] for x in e)           # 750.50
    leads = sum(x["leads"] for x in e)           # 80
    qual = sum(x["qualified_leads"] for x in e)  # 30
    mb = sum(x["meetings_booked"] for x in e)    # 12
    ma = sum(x["meetings_attended"] for x in e)  # 8
    cust = sum(x["customers"] for x in e)        # 3
    rev = sum(x["revenue"] for x in e)           # 5500
    meta = {"entries": len(e), "spend": round(spend, 2), "leads": leads, "qualified_leads": qual,
            "meetings_booked": mb, "meetings_attended": ma, "customers": cust, "revenue": float(rev),
            "cost_per_lead": round(spend / leads, 2), "cost_per_qualified_lead": round(spend / qual, 2),
            "icp_match_pct": round(qual / leads * 100, 2), "attendance_rate": round(ma / mb * 100, 2),
            "lead_to_customer_rate": round(cust / qual * 100, 2), "customer_acquisition_cost": round(spend / cust, 2),
            "revenue_per_spend": round(rev / spend, 2)}
    g = [x for x in A["perf_entries"] if x["channel"] == "google_ads"][0]
    google = {"spend": 300.0, "leads": 10, "qualified_leads": 4, "cost_per_lead": 30.0, "cost_per_qualified_lead": 75.0,
              "customer_acquisition_cost": 300.0, "revenue_per_spend": 3.0, "attendance_rate": 50.0,
              "lead_to_customer_rate": 25.0, "icp_match_pct": 40.0}
    extra = 120.0
    n_leads = len(A["leads"])                      # 3 (intent lead excluded)
    n_qual = sum(1 for l in A["leads"] if l["score"] >= 60)   # 2 (80, 70 >= ICP threshold 60)
    pros = {"leads": n_leads, "qualified_leads": n_qual, "spend": extra, "extra_costs": extra, "api_spend": 0.0,
            "cost_per_lead": round(extra / n_leads, 2), "cost_per_qualified_lead": round(extra / n_qual, 2),
            "icp_match_pct": round(n_qual / n_leads * 100, 2)}
    if with_outcome:
        pros.update(meetings_booked=1, customers=1, revenue=1000.0,
                    customer_acquisition_cost=round(extra / 1, 2), revenue_per_spend=round(1000 / extra, 2),
                    lead_to_customer_rate=round(1 / n_qual * 100, 2))
    else:
        pros.update(meetings_booked=0, customers=0, revenue=0.0)
    return meta, google, pros


def cmp_fields(S, label, got, want, c):
    bad = []
    for k, v in want.items():
        g = got.get(k)
        if g is None or abs(float(g) - float(v)) > 0.011:
            bad.append("%s: got %r want %r" % (k, g, v))
    check(S, label, not bad, "; ".join(bad) + " :: " + req_detail(c))


def test_functional(ctx, A, B):
    S = "functional"
    cA = ctx["A"]
    # --- performance math (before the outcome update)
    meta, google, pros = perf_expected(A, with_outcome=False)
    st, text, js = cA.get("/performance")
    ok = st == 200 and js
    check(S, "GET /performance 200", ok, req_detail(cA))
    if ok:
        chans = {c["channel"]: c for c in js.get("channels", [])}
        check(S, "performance lists meta_ads, google_ads; prospecting_costs not a channel",
              "meta_ads" in chans and "google_ads" in chans and "prospecting_costs" not in chans, req_detail(cA))
        if "meta_ads" in chans:
            cmp_fields(S, "meta_ads aggregate math (spend 750.50, leads 80, qual 30, CPL 9.38, CPQL 25.02, ICP% 37.5, attend% 66.67, L2C% 10, CAC 250.17, ROAS 7.33)",
                       chans["meta_ads"], meta, cA)
        if "google_ads" in chans:
            cmp_fields(S, "google_ads math (CPL 30, CPQL 75, CAC 300, ROAS 3)", chans["google_ads"], google, cA)
        cmp_fields(S, "prospecting block: 3 leads, 2 qualified, spend = 120 extra costs, CPL 40, CPQL 60",
                   js.get("prospecting", {}), pros, cA)
        check(S, "entries list == A's 4 seeded entries, none of B's",
              {e["label"] for e in js.get("entries", [])} == set(A["perf_labels"]), req_detail(cA))
        total = len(js.get("entries", []))
        check(S, "performance tenant_id is A's", js.get("tenant_id") == A["tid"], req_detail(cA))
    # --- DB cross-check of meta_ads sums
    sums = psql("SELECT SUM(spend),SUM(leads),SUM(revenue) FROM channel_benchmarks WHERE tenant_id=%s AND channel='meta_ads'" % sq(A["tid"]))
    check(S, "DB sums for A meta_ads match hand calc (750.50|80|5500)", sums.replace(".00", "") in ("750.50|80|5500", "750.5|80|5500"), sums)
    # --- performance validation
    st, _, js = cA.post("/performance/save", {"channel": "meta_ads", "period_start": A["ps"], "period_end": A["pe"], "spend": -5})
    check(S, "negative spend rejected", st == 400, req_detail(cA))
    st, _, js = cA.post("/performance/save", {"channel": "nope", "period_start": A["ps"], "period_end": A["pe"]})
    check(S, "unknown channel rejected", st == 400, req_detail(cA))
    st, _, js = cA.post("/performance/save", {"channel": "meta_ads", "period_start": A["pe"], "period_end": A["ps"]})
    check(S, "period_end before start rejected", st == 400, req_detail(cA))

    # --- own-entry update + delete round-trip
    st, _, js = cA.post("/performance/save", {"channel": "other", "label": "TmpA-" + ctx["sfx"], "period_start": A["ps"],
                                              "period_end": A["pe"], "spend": 10, "leads": 1})
    tmp_id = (js or {}).get("id")
    check(S, "A can create a temp performance entry", st == 200 and tmp_id, req_detail(cA))
    if tmp_id:
        st, _, js = cA.post("/performance/save", {"id": tmp_id, "channel": "other", "label": "TmpA2-" + ctx["sfx"],
                                                  "period_start": A["ps"], "period_end": A["pe"], "spend": 20, "leads": 2})
        check(S, "A can update own performance entry", st == 200 and js and js.get("success"), req_detail(cA))
        st, _, js = cA.post("/performance/delete", {"id": tmp_id})
        check(S, "A can delete own performance entry", st == 200 and js and js.get("success"), req_detail(cA))

    # --- outcome round-trip
    lid = A["leads"][0]["id"]
    st, _, js = cA.post("/lead/%s/outcome" % lid, {"meeting_booked": True, "deal_stage": "won", "deal_value": 1000})
    check(S, "POST /lead/<A>/outcome succeeds", st == 200 and js and js.get("success"), req_detail(cA))
    st, _, js = cA.get("/lead/" + lid)
    ok = st == 200 and js and js.get("meeting_booked") is True and js.get("deal_stage") == "won" and float(js.get("deal_value") or 0) == 1000.0
    check(S, "outcome round-trips via GET /lead/<id> (meeting_booked, won, 1000)", ok, req_detail(cA))
    row = psql("SELECT meeting_booked, deal_stage, deal_value, deal_closed_at IS NOT NULL, meeting_booked_at IS NOT NULL FROM leads WHERE id=%s" % sq(lid))
    check(S, "outcome persisted in DB with closed/booked timestamps", row == "t|won|1000.00|t|t", row)
    st, _, js = cA.post("/lead/%s/outcome" % lid, {"deal_stage": "bogus"})
    check(S, "invalid deal_stage rejected", st == 400, req_detail(cA))
    st, _, js = cA.post("/lead/%s/outcome" % lid, {"deal_value": -3})
    check(S, "negative deal_value rejected", st == 400, req_detail(cA))
    # A2 (same company) can read the outcome
    st, _, js = ctx["A2"].get("/lead/" + lid)
    check(S, "A2 (same company) sees the outcome", st == 200 and js and js.get("deal_stage") == "won", req_detail(ctx["A2"]))
    # performance reflects the outcome
    meta, google, pros = perf_expected(A, with_outcome=True)
    st, text, js = cA.get("/performance")
    if st == 200 and js:
        cmp_fields(S, "prospecting block after outcome: booked 1, customers 1, revenue 1000, CAC 120, ROAS 8.33, L2C 50%",
                   js.get("prospecting", {}), pros, cA)
    # B's performance unaffected by A's outcome
    st, text, js = ctx["B"].get("/performance")
    if st == 200 and js:
        check(S, "B's prospecting revenue unaffected by A's won deal", float(js["prospecting"].get("revenue") or 0) == 0.0, req_detail(ctx["B"]))

    # --- admin can view per-company performance, and platform-wide aggregates
    st, text, js = ctx["admin"].get("/performance?tenant_id=" + A["tid"])
    if st == 200 and js:
        chans = {c["channel"]: c for c in js.get("channels", [])}
        check(S, "admin /performance?tenant_id=A equals A's own view", "meta_ads" in chans and
              abs(chans["meta_ads"]["spend"] - 750.5) < 0.011, req_detail(ctx["admin"]))
    else:
        check(S, "admin /performance?tenant_id=A", False, req_detail(ctx["admin"]))

    # --- ICP / workflow / CRM own CRUD
    st, _, js = cA.post("/icp/save", {"id": A["icp_id"], "name": A["icp_name"] + "-edit", "industries": "x", "geos": "y",
                                      "keywords": "", "exclusions": "", "source_mix": "all", "min_lead_score": 60,
                                      "is_active": False, "push_to_crm": False, "offer": "o", "industry_template": "healthcare_clinics"})
    check(S, "A can update own ICP", st == 200 and js and js.get("success"), req_detail(cA))
    st, text, js = cA.get("/icp")
    check(S, "A's ICP edit visible", A["icp_name"] + "-edit" in text, req_detail(cA))
    st, _, js = cA.post("/workflows/save", {"name": "WFtmp-" + ctx["sfx"], "graph": {"nodes": [], "edges": []}})
    wid = (js or {}).get("id")
    st2, _, js2 = cA.post("/workflows/%s/delete" % wid, {})
    check(S, "A can create and delete own workflow", st == 200 and wid and st2 == 200 and js2 and js2.get("success"), req_detail(cA))
    st, _, js = cA.post("/crm/connections/save", {"type": "webhook", "name": "CRMtmp-" + ctx["sfx"],
                                                  "config": {"webhook_url": "http://127.0.0.1/hook", "webhook_secret": "x"}})
    check(S, "client webhook to non-https/private URL rejected (SSRF guard)", st == 400, req_detail(cA))

    # --- erase own lead
    elead = A["leads"][2]
    mail = elead["email"]
    st, _, js = cA.post("/lead/%s/erase" % elead["id"], {})
    check(S, "erase own lead succeeds", st == 200 and js and js.get("success"), req_detail(cA))
    n = psql("SELECT (SELECT COUNT(*) FROM leads WHERE id=%s)+(SELECT COUNT(*) FROM contacts WHERE lead_id=%s)" % (sq(elead["id"]), sq(elead["id"])))
    check(S, "erased lead and contacts gone from DB", n == "0", "remaining rows=%s" % n)
    st, _, js = cA.get("/lead/" + elead["id"])
    check(S, "erased lead GET -> 404", st == 404, req_detail(cA))
    sup = psql("SELECT COUNT(*) FROM unsubscribes WHERE LOWER(email)=%s" % sq(mail.lower())) if True else "1"
    check(S, "erased contact's email suppressed (right to erasure)", sup not in ("0", ""), "suppression rows=%s" % sup)
    audit = psql("SELECT COUNT(*) FROM data_erasures WHERE tenant_id=%s" % sq(A["tid"]))
    check(S, "erasure audit row written for A's tenant", audit == "1", "rows=%s" % audit)
    st, _, js = cA.post("/lead/%s/erase" % elead["id"], {})
    check(S, "second erase of same lead refused", refused(st, js), req_detail(cA))
    # B unaffected
    st, text, js = ctx["B"].get("/leads")
    check(S, "B's leads untouched by A's erase", all(l["name"] in text for l in B["leads"]), req_detail(ctx["B"]))

    # --- own lead bulk delete: delete one of A's own leads via /leads/delete
    st, _, js = cA.post("/leads/delete", {"lead_ids": [A["leads"][1]["id"]]})
    gone = psql("SELECT COUNT(*) FROM leads WHERE id=%s" % sq(A["leads"][1]["id"]))
    check(S, "A can bulk-delete own lead", st == 200 and gone == "0", "%s gone=%s" % (req_detail(cA), gone))


def main():
    global ARGS
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://127.0.0.1:8080")
    ap.add_argument("--admin-user", default="admin")
    ap.add_argument("--admin-pass", default="localdev123")
    ap.add_argument("--report", default=os.path.join(HERE, "last_report.json"))
    ARGS = ap.parse_args()

    sfx = uuid.uuid4().hex[:8]
    started = time.time()
    print("Controva multi-tenant simulation  base=%s  suffix=%s" % (ARGS.base, sfx))
    ctx = setup(sfx)
    A = seed_company(ctx, "A")
    B = seed_company(ctx, "B")
    for d in (A, B):
        d["sfx"] = sfx
    A["username"], B["username"] = ctx["ua"], ctx["ub"]

    # a job owned by B
    cB = ctx["B"]
    st, _, js = cB.post("/enrich", {})
    B["job_id"] = (js or {}).get("job_id")
    check("seed", "B: POST /enrich {} starts a job", st == 200 and B["job_id"], req_detail(cB))
    for _ in range(40):                      # let it settle so DB snapshots are stable
        st, _, js = cB.get("/job/" + str(B["job_id"]))
        if js and js.get("status") not in ("running", "queued"):
            break
        time.sleep(0.5)

    # sanity checks on seeding
    st, _, js = ctx["A"].get("/leads")
    ids = {l.get("id") for l in (js or {}).get("leads", [])}
    check("seed", "GET /leads (A) discovers A's seeded lead ids", {l["id"] for l in A["leads"]} <= ids, req_detail(ctx["A"]))

    test_isolation_reads(ctx, A, B)
    test_isolation_writes(ctx, A, B)
    test_bulk_jobs(ctx, A, B)
    test_admin_only(ctx, A, B)
    test_functional(ctx, A, B)
    test_hardening(ctx, A, B)
    test_secrets(ctx, A, B)       # last: scans every client response collected above

    # ------------------------------------------------------------------ report
    fails = [r for r in RESULTS if r["status"] == "FAIL"]
    w = max(len(r["section"]) for r in RESULTS)
    print("\n%-*s  %-4s  %s" % (w, "SECTION", "RES", "CHECK"))
    print("-" * 110)
    for r in RESULTS:
        print("%-*s  %-4s  %s" % (w, r["section"], r["status"], r["name"]))
    print("-" * 110)
    by = {}
    for r in RESULTS:
        by.setdefault(r["section"], [0, 0])[0 if r["status"] == "PASS" else 1] += 1
    for s, (p, f) in by.items():
        print("  %-18s PASS %3d  FAIL %3d" % (s, p, f))
    print("TOTAL: %d checks, %d PASS, %d FAIL  (%.1fs)" % (len(RESULTS), len(RESULTS) - len(fails), len(fails), time.time() - started))
    if fails:
        print("\nFAILURES")
        for r in fails:
            print("* [%s] %s\n    %s" % (r["section"], r["name"], r["detail"]))
    report = {"run_at": datetime.now().astimezone().isoformat(), "base": ARGS.base, "suffix": sfx,
              "companies": {"A": {"tenant_id": A["tid"], "name": A["company"]}, "B": {"tenant_id": B["tid"], "name": B["company"]}},
              "total": len(RESULTS), "passed": len(RESULTS) - len(fails), "failed": len(fails), "results": RESULTS}
    with open(ARGS.report, "w") as fh:
        json.dump(report, fh, indent=2)
    print("report: %s" % ARGS.report)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
