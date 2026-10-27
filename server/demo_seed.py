#!/usr/bin/env python3
"""
Demo data for showing the platform to a prospective client.

Creates ONE clearly labelled company, "Demo Company (sample data)", with a
client login, three ICPs (one per target industry), ~40 fictional prospects,
research, emails, replies, meetings, deals and channel figures, so every page
has something to show. All addresses use the reserved .example domain, so
nothing here can ever really be emailed.

Runs automatically in Docker when DEMO_DATA=1 (the default in
docker-compose.yml); safe to re-run — it does nothing if the demo company
already exists. Remove it any time by deleting that company's rows, or start
fresh with `docker compose down -v`.

    python server/demo_seed.py
"""
import json, os, random, sys, hashlib
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import leads_api as L  # noqa: E402

DEMO_COMPANY = 'Demo Company (sample data)'
DEMO_USER = os.environ.get('DEMO_USER', 'demo')
DEMO_PASSWORD = os.environ.get('DEMO_PASSWORD', 'demo12345!')
rnd = random.Random(42)
NOW = datetime.now(timezone.utc)

ICPS = [
    {'name': 'Dental & aesthetic clinics — Austin TX', 'template': 'healthcare_clinics',
     'industries': 'dental clinics, aesthetic clinics', 'geos': 'Austin US', 'city': 'Austin',
     'offer': 'An AI front-desk assistant that answers every call, books new patients 24/7 and refills cancelled slots',
     'criteria': 'Independent practices with 2+ chairs, taking new patients, offering cosmetic or implant work',
     'require_email': True, 'n': 18,
     'names': ['Lakeside Family Dentistry', 'Barton Creek Smiles', 'Hill Country Dental Studio', 'South Lamar Dental',
               'Mueller Dental Care', 'Riverside Aesthetics', 'Zilker Skin & Laser', 'Domain Dental Group',
               'Cedar Park Orthodontics', 'Bee Cave Family Dental', 'Eastside Smile Center', 'Travis Heights Dentistry',
               'Westlake Cosmetic Dental', 'Round Rock Dental Arts', 'Pflugerville Smiles', 'Lamar Aesthetic Clinic',
               'Northloop Dental', 'Bluebonnet Dental Care'],
     'titles': ['Practice Owner', 'Practice Manager', 'Clinic Manager'],
     'pains': [('Missed calls after hours', 'Several reviews mention voicemail and slow callbacks', 4),
               ('Empty appointment slots', 'Online booking shows same-week availability on most days', 3),
               ('Front-desk workload', 'Hiring post for a second receptionist', 3),
               ('Patient acquisition cost', 'Running paid search ads on implant keywords', 2)],
     'subject': 'Every missed call at {name}',
     'body': "Hi {first},\\n\\nI noticed a few {name} reviews mention calls going to voicemail. Our AI front desk answers every call, books new patients straight into your calendar and fills cancelled slots, day or night.\\n\\nPractices your size usually recover 15–25 appointments a month.\\n\\nWorth a 15-minute look next week?\\n\\nAlex"},
    {'name': 'Commercial contractors — Dallas TX', 'template': 'construction_real_estate',
     'industries': 'general contractors, commercial contractors', 'geos': 'Dallas US', 'city': 'Dallas',
     'offer': 'Estimating software that turns drawings into priced bids in hours instead of days',
     'criteria': 'Commercial or multifamily work, 20+ employees, actively bidding public or private projects',
     'require_email': False, 'n': 12,
     'names': ['Trinity Build Group', 'Lone Star Commercial Builders', 'Oak Cliff Construction', 'Deep Ellum Contractors',
               'Preston Ridge Builders', 'Mesquite Commercial Co', 'Irving Structural Group', 'Garland Build Partners',
               'Uptown Renovation Co', 'Red Oak Contracting', 'Plano Commercial Works', 'Frisco Site Builders'],
     'titles': ['Owner', 'Operations Director', 'Chief Estimator'],
     'pains': [('Slow bid turnaround', 'Hiring two estimators; posts mention bid deadlines', 4),
               ('Uneven project pipeline', 'Project gallery shows long gaps between completions', 3),
               ('Subcontractor coordination', 'Reviews mention schedule slips', 2)],
     'subject': 'Bids out the same day at {name}',
     'body': "Hi {first},\\n\\nSaw {name} is hiring estimators — usually a sign bids are piling up. Our estimating tool turns drawings into priced takeoffs in hours, so your current team can bid more jobs without adding headcount.\\n\\nCould I show you a 15-minute demo on one of your recent projects?\\n\\nAlex"},
    {'name': 'Independent insurance agencies — Houston TX', 'template': 'banking_insurance',
     'industries': 'insurance agencies, insurance brokers', 'geos': 'Houston US', 'city': 'Houston',
     'offer': 'A renewal-retention service that contacts every policyholder 60 days before renewal',
     'criteria': 'Independent agencies writing commercial lines, 5+ producers',
     'require_email': False, 'n': 8,
     'names': ['Bayou City Insurance Group', 'Galleria Risk Partners', 'Heights Insurance Agency', 'Katy Commercial Insurance',
               'Sugar Land Insurance Brokers', 'Westchase Benefits & Risk', 'Memorial Insurance Advisors', 'Clear Lake Agency'],
     'titles': ['Agency Principal', 'Managing Director', 'Head of Sales'],
     'pains': [('Renewal churn', 'Reviews mention not hearing from the agent until renewal', 4),
               ('Lead quality from aggregators', 'Listed on three quote-comparison sites', 3)],
     'subject': 'Renewals at {name}',
     'body': "Hi {first},\\n\\nMost independent agencies lose 8–12% of commercial policies at renewal, often because the first contact comes too late. We reach every policyholder 60 days out so your producers only handle the conversations that matter.\\n\\nOpen to a short call to see if it fits {name}?\\n\\nAlex"},
]
FIRST = ['Maria', 'James', 'Priya', 'Daniel', 'Sofia', 'Michael', 'Aisha', 'Robert', 'Elena', 'David', 'Grace', 'Carlos']
LAST = ['Nguyen', 'Patel', 'Garcia', 'Johnson', 'Kim', 'Rivera', 'Thompson', 'Ali', 'Brooks', 'Chen', 'Morales', 'Wright']
REPLIES = [('interested', 'Asked for a demo next week'), ('interested', 'Wants pricing and a case study'),
           ('objection', 'Already using a competitor, open to compare at renewal'),
           ('not_interested', 'Not a priority this quarter'), ('ooo', 'Out of office until Monday')]


def ago(days, hours=0):
    return NOW - timedelta(days=days, hours=hours)


def past(ts):
    """Sample events never land in the future."""
    return min(ts, NOW - timedelta(hours=1))


def slug(name):
    return ''.join(ch for ch in name.lower() if ch.isalnum())[:24]


def main():
    L.migrate_all()
    conn = L.db_conn(); cur = conn.cursor()
    cur.execute("SELECT id FROM tenants WHERE name = %s", (DEMO_COMPANY,))
    if cur.fetchone():
        print(f'[demo] "{DEMO_COMPANY}" already exists — nothing to do')
        return

    # Company + client login
    cur.execute("INSERT INTO tenants (name) VALUES (%s) RETURNING id", (DEMO_COMPANY,))
    tid = str(cur.fetchone()[0])
    cur.execute("SELECT 1 FROM auth_users WHERE username = %s", (DEMO_USER,))
    if not cur.fetchone():
        salt = L._h_secrets.token_hex(16)
        cur.execute("INSERT INTO auth_users (username, salt, pwhash, role, tenant_id) VALUES (%s,%s,%s,'client',%s)",
                    (DEMO_USER, salt, L.auth_hash(DEMO_PASSWORD, salt), tid))
    cur.execute("""INSERT INTO sending_domains (domain, from_email, from_name, daily_cap, is_active, tenant_id)
                   VALUES ('brightline.example', 'alex@brightline.example', 'Alex at Brightline', 40, TRUE, %s)
                   RETURNING id""", (tid,))
    domain_id = cur.fetchone()[0]
    cur.execute("""INSERT INTO crm_connections (type, name, config, is_active, tenant_id)
                   VALUES ('webhook', 'Sales CRM (via Zapier)', %s, TRUE, %s)""",
                (json.dumps({'webhook_url': 'https://hooks.example/catch/demo'}), tid))
    conn.commit()
    L.save_tenant_settings(tid, {
        'from_name': 'Alex at Brightline', 'from_email': 'alex@brightline.example',
        'reply_to': 'sales@brightline.example', 'company_name': 'Brightline Growth (demo)',
        'company_address': '500 Congress Ave, Austin TX 78701', 'brand_name': 'Brightline Growth (demo)',
        'brand_color': '#0f766e', 'calendly_url': 'https://calendly.com/brightline-demo/intro',
        'digest_enabled': False, 'digest_email': 'alex@brightline.example'})

    stats = {'leads': 0, 'sent': 0, 'replies': 0, 'meetings': 0, 'won': 0}
    for icp in ICPS:
        tpl = L.INDUSTRY_TEMPLATES[icp['template']]
        cur.execute("""INSERT INTO icp_profiles (name, industries, geos, keywords, exclusions, source_mix, min_lead_score,
                         push_to_crm, is_active, last_run_at, tenant_id, created_by, offer, industry_template,
                         require_email, qualification_notes)
                       VALUES (%s,%s,%s,'','','all',%s,FALSE,FALSE,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (icp['name'], icp['industries'], icp['geos'], tpl['min_lead_score'], ago(1), tid, DEMO_USER,
                     icp['offer'], icp['template'], icp['require_email'], icp['criteria']))
        icp_id = cur.fetchone()[0]
        cur.execute("""INSERT INTO icp_runs (icp_id, started_at, finished_at, leads_found, leads_new, status)
                       VALUES (%s,%s,%s,%s,%s,'completed')""", (icp_id, ago(1), ago(1), icp['n'] + 6, icp['n']))
        niche = icp['industries'].split(',')[0].strip()
        for i, name in enumerate(icp['names'][:icp['n']]):
            created = ago(rnd.randint(2, 27), rnd.randint(0, 20))
            rating = round(rnd.uniform(3.7, 4.9), 1)
            reviews = rnd.randint(18, 260)
            score = rnd.choice([34, 41, 46, 52, 55, 58, 61, 64, 68, 72, 77, 83, 88])
            # Funnel position: earlier names travel further
            stage = 'sent' if i < icp['n'] * 0.55 else ('ready' if i < icp['n'] * 0.7 else
                     ('enriched' if i < icp['n'] * 0.85 else 'discovered'))
            first, last = rnd.choice(FIRST), rnd.choice(LAST)
            domain = slug(name) + '.example'
            cur.execute("""INSERT INTO leads (place_id, business_name, niche, city, country, address, phone, website,
                             google_rating, review_count, status, source, tenant_id, icp_id, icp_score, ai_score,
                             score_reason, score_breakdown, created_at, updated_at, domain, search_batch_id)
                           VALUES (%s,%s,%s,%s,'US',%s,%s,%s,%s,%s,%s,'demo',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                           RETURNING id""",
                        (f'demo_{tid[:8]}_{slug(name)}', name, niche, icp['city'],
                         f'{rnd.randint(100, 9800)} {rnd.choice(["Main", "Oak", "Lamar", "Commerce", "Elm"])} St, {icp["city"]} TX',
                         f'(512) 555-{rnd.randint(1000, 9999)}', f'https://{domain}', rating, reviews,
                         stage, tid, icp_id, score if stage != 'discovered' else None,
                         round(score / 10) if stage != 'discovered' else None,
                         'Strong fit for the ICP with a visible, specific need' if score >= 70 else 'Partial fit',
                         json.dumps({'icp_fit': 30, 'pain_severity': min(30, score - 45), 'intent_signals': 10,
                                     'quality': max(0, score - 30 - min(30, score - 45) - 10), 'total': score}),
                         created, created, domain, f'job_demo_{icp_id}'))
            lead_id = cur.fetchone()[0]
            stats['leads'] += 1
            if stage == 'discovered':
                continue
            title = rnd.choice(icp['titles'])
            email = f'{first.lower()}@{domain}'
            cur.execute("""INSERT INTO contacts (lead_id, first_name, last_name, full_name, job_title, email, source,
                             confidence, email_status, email_checked_at, email_method)
                           VALUES (%s,%s,%s,%s,%s,%s,'demo',90,'deliverable',%s,'smtp')""",
                        (lead_id, first, last, f'{first} {last}', title, email, created + timedelta(hours=2)))
            pains = rnd.sample(icp['pains'], k=min(2, len(icp['pains'])))
            cur.execute("""INSERT INTO lead_research (lead_id, status, pain_points, needs_summary, recommended_angle,
                             reviews_summary, tech_stack, hiring_signals, sources, researched_at)
                           VALUES (%s,'completed',%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (lead_id, json.dumps([{'pain': p, 'evidence': e, 'severity': s} for p, e, s in pains]),
                         f'{name} would benefit most from fixing: {pains[0][0].lower()}.',
                         f'Lead with {pains[0][0].lower()} and a concrete monthly number.',
                         'Not stored: review text can contain patient information.' if tpl.get('minimize_personal_data')
                         else 'Mostly positive; a few mention slow responses.',
                         ['WordPress', 'Google Analytics'], [], json.dumps([f'https://{domain}', 'review search snippets']),
                         created + timedelta(hours=3)))
            if stage in ('ready', 'sent'):
                subj = icp['subject'].format(name=name)
                body = icp['body'].format(name=name, first=first).replace('\\n', '\n')
                cur.execute("INSERT INTO assets (lead_id, asset_type, content, model_used) VALUES (%s,'email_subject',%s,'claude'), (%s,'email_body',%s,'claude')",
                            (lead_id, subj, lead_id, body))
            if stage != 'sent':
                continue
            sent_at = past(created + timedelta(days=1, hours=rnd.randint(1, 8)))
            reply = REPLIES[i % len(REPLIES)] if i % 2 == 0 else None
            opened = past(sent_at + timedelta(hours=rnd.randint(1, 30)))
            cur.execute("""INSERT INTO outreach_log (tenant_id, lead_id, email_to, email_subject, email_body, sent_at,
                             opened_at, replied_at, status, reply_content, reply_classification, reply_digest,
                             resend_message_id, sending_domain_id)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (tid, lead_id, email, icp['subject'].format(name=name), 'Sample outreach email', sent_at, opened,
                         past(opened + timedelta(hours=3)) if reply else None, 'replied' if reply else 'opened',
                         reply[1] if reply else None, reply[0] if reply else None, reply[1] if reply else None,
                         f'demo_{lead_id}', domain_id))
            stats['sent'] += 1
            if reply:
                stats['replies'] += 1
                cur.execute("UPDATE leads SET status='replied' WHERE id=%s", (lead_id,))
            if reply and reply[0] == 'interested':
                booked = past(opened + timedelta(days=1))
                attended = i % 4 != 2
                won = attended and i % 3 == 0
                cur.execute("""UPDATE leads SET meeting_booked=TRUE, meeting_booked_at=%s, meeting_attended=%s,
                                 deal_stage=%s, deal_value=%s, deal_closed_at=%s, outcome_updated_at=NOW()
                               WHERE id=%s""",
                            (booked, attended, 'won' if won else 'open', rnd.choice([4800, 6000, 7200]) if won else None,
                             past(booked + timedelta(days=5)) if won else None, lead_id))
                stats['meetings'] += 1
                stats['won'] += int(won)
    # API spend for the prospecting column, and the client's other channels
    for d in range(28):
        cur.execute("INSERT INTO api_usage (provider, endpoint, cost, meta, username, created_at) VALUES (%s,%s,%s,'demo',%s,%s)",
                    (rnd.choice(['serper', 'google_places', 'claude', 'replicate']), 'demo', round(rnd.uniform(0.6, 2.2), 2),
                     DEMO_USER, ago(d)))
    start, end = (NOW - timedelta(days=29)).date(), NOW.date()
    for ch, label, spend, leads, q, mb, ma, cust, rev in [
            ('meta_ads', 'Lead-gen campaign', 2400, 85, 22, 6, 4, 1, 4800),
            ('google_ads', 'Search campaign', 1800, 40, 15, 5, 4, 1, 6000),
            ('website', 'Contact form', 600, 30, 6, 2, 1, 0, 0),
            ('prospecting_costs', 'Platform subscription', 299, 0, None, 0, 0, 0, 0)]:
        cur.execute("""INSERT INTO channel_benchmarks (tenant_id, channel, label, period_start, period_end, spend, leads,
                         qualified_leads, meetings_booked, meetings_attended, customers, revenue, notes, created_by)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'sample data',%s)""",
                    (tid, ch, label, start, end, spend, leads, q, mb, ma, cust, rev, DEMO_USER))
    conn.commit(); cur.close(); conn.close()
    print(f'[demo] created "{DEMO_COMPANY}": {stats["leads"]} leads, {stats["sent"]} emailed, '
          f'{stats["replies"]} replies, {stats["meetings"]} meetings, {stats["won"]} won — '
          f'log in as {DEMO_USER} / {DEMO_PASSWORD}')


if __name__ == '__main__':
    main()
