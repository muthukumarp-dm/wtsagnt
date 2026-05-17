-- Add a column for the student-worksheet PDF URL.
-- Existing rows get NULL; the pipeline writes the signed URL alongside the
-- other artifact URLs in cas_to_awaiting_approval().
--
-- Apply via Supabase dashboard SQL editor before deploying the worksheet
-- feature. Idempotent: re-running is a no-op thanks to IF NOT EXISTS.

ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS worksheet_url TEXT;
