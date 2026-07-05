-- Migration: add job_url_hash column to job_feedback
-- Run this in the Supabase SQL Editor

-- Create the table if it doesn't exist yet (safe to run multiple times)
CREATE TABLE IF NOT EXISTS job_feedback (
    id          BIGSERIAL PRIMARY KEY,
    chat_id     BIGINT NOT NULL,
    job_url_hash TEXT NOT NULL,
    feedback    TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- If the table already exists but is missing job_url_hash, add it:
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'job_feedback' AND column_name = 'job_url_hash'
    ) THEN
        ALTER TABLE job_feedback ADD COLUMN job_url_hash TEXT NOT NULL DEFAULT '';
    END IF;
END
$$;
