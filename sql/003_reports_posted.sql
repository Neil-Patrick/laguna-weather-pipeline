-- 003_reports_posted.sql: remember whether a weekly report reached Discord.
-- Idempotent. A re-run of the weekly job skips weeks whose report was already
-- posted (posted_at set), so Discord never gets the same week twice.
-- Order in report.py: generate -> save (posted_at NULL) -> post -> set posted_at.

ALTER TABLE reports ADD COLUMN IF NOT EXISTS posted_at TIMESTAMPTZ;
