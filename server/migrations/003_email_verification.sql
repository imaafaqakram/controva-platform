-- Migration 003: Email verification pipeline (M2)
-- Adds verification state to contacts so outreach can gate on deliverability.

ALTER TABLE contacts ADD COLUMN IF NOT EXISTS email_status VARCHAR(20);
-- deliverable | risky | undeliverable | unknown   (NULL = legacy, never checked)

ALTER TABLE contacts ADD COLUMN IF NOT EXISTS email_checked_at TIMESTAMPTZ;

ALTER TABLE contacts ADD COLUMN IF NOT EXISTS email_method VARCHAR(60);
-- how the address was found: serper | oxylabs | crawl4ai | permutator | manual

CREATE INDEX IF NOT EXISTS idx_contacts_email_status ON contacts(email_status);
