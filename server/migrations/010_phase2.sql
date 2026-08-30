-- Migration 010: Phase-2 suite (M10) — reply classification, meeting booking

ALTER TABLE outreach_log ADD COLUMN IF NOT EXISTS reply_classification VARCHAR(30);
ALTER TABLE outreach_log ADD COLUMN IF NOT EXISTS reply_digest TEXT;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS meeting_booked BOOLEAN DEFAULT FALSE;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS meeting_booked_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_outreach_reply_class ON outreach_log(reply_classification);
