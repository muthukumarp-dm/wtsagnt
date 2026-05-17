-- Add a column for the standalone MCQ-quiz PDF URL.
-- Existing rows get NULL; the pipeline writes the signed URL alongside
-- pptx_url / pdf_url / worksheet_url in cas_to_awaiting_approval().
--
-- Apply via Supabase dashboard SQL editor before deploying. Idempotent.

ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS mcq_url TEXT;
