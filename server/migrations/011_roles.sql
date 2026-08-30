-- Migration 011: role-based access — client/test-user accounts with
-- restricted access (no Settings, no API keys, no CRM connection management)

ALTER TABLE auth_users ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'admin';
