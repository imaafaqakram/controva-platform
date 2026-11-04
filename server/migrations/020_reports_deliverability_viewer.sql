-- Migration 020: results report, deliverability check, viewer role (M19).
-- Mirrors ensure_deliverability_columns() in leads_api.py, which runs this at
-- startup. The monthly report and the viewer role need no schema: the report
-- is switched on per company in tenant_settings (monthly_report_enabled), and a
-- viewer is an auth_users row with role = 'viewer'.
ALTER TABLE sending_domains ADD COLUMN IF NOT EXISTS dns_report JSONB;           -- last SPF/DKIM/DMARC/MX check
ALTER TABLE sending_domains ADD COLUMN IF NOT EXISTS dns_checked_at TIMESTAMPTZ;
