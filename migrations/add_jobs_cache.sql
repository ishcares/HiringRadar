-- Migration: Create jobs_cache table for decoupled scrape/alert architecture
-- Run once in Supabase SQL Editor (Dashboard → SQL Editor → New Query)
--
-- Purpose: The scraper writes all live jobs here every 5 min.
--          The alert sender reads from here (fast DB read, no HTTP).
--          The Phase 2 web dashboard reads from here too.

CREATE TABLE IF NOT EXISTS jobs_cache (
    id          TEXT PRIMARY KEY,        -- hash(company + title + url)
    company     TEXT NOT NULL,
    title       TEXT NOT NULL,
    location    TEXT,
    url         TEXT NOT NULL,
    scraped_at  TIMESTAMPTZ DEFAULT now(),
    is_active   BOOLEAN DEFAULT true     -- false = job was removed from ATS
);

-- Index for fast queries by company or active status
CREATE INDEX IF NOT EXISTS idx_jobs_cache_active    ON jobs_cache (is_active);
CREATE INDEX IF NOT EXISTS idx_jobs_cache_company   ON jobs_cache (company);
CREATE INDEX IF NOT EXISTS idx_jobs_cache_scraped   ON jobs_cache (scraped_at DESC);

-- seen_jobs: migrate from url TEXT → url_hash TEXT PRIMARY KEY
-- (db.py now stores hashes, not full URLs)
CREATE TABLE IF NOT EXISTS seen_jobs (
    url_hash    TEXT PRIMARY KEY,
    seen_at     TIMESTAMPTZ DEFAULT now()
);
