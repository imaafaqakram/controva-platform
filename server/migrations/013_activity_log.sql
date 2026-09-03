-- Migration 013: attribute api_usage rows to the user who triggered them (M12)
-- Powers the admin Activity Log — who used which tool/API, when, and at
-- what cost. NULL means system-initiated (a scheduler loop, not a user click).

ALTER TABLE api_usage ADD COLUMN IF NOT EXISTS username VARCHAR(80);
CREATE INDEX IF NOT EXISTS idx_api_usage_username ON api_usage(username);
