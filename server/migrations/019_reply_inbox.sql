-- Migration 019: reply inbox (M18). Mirrors ensure_inbox_columns() in
-- leads_api.py, which runs this at startup. A reply is "handled" once someone
-- answered it or recorded an outcome; our answers point at the reply they answer.
ALTER TABLE outreach_log ADD COLUMN IF NOT EXISTS reply_handled_at TIMESTAMPTZ;
ALTER TABLE outreach_log ADD COLUMN IF NOT EXISTS reply_handled_by VARCHAR(80);
ALTER TABLE outreach_log ADD COLUMN IF NOT EXISTS reply_outcome VARCHAR(30);   -- replied | meeting_booked | not_interested | leadhunter | done
ALTER TABLE outreach_log ADD COLUMN IF NOT EXISTS parent_id UUID REFERENCES outreach_log(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_outreach_inbox ON outreach_log(replied_at DESC) WHERE replied_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_outreach_parent ON outreach_log(parent_id) WHERE parent_id IS NOT NULL;
