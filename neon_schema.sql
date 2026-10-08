-- ==============================================================================
-- HiringRadar Neon PostgreSQL Production Schema
-- Compatible with PostgreSQL 15+ & Neon Serverless
-- ==============================================================================

-- 1. Students / Candidates Table
CREATE TABLE IF NOT EXISTS students (
    chat_id BIGINT PRIMARY KEY,
    name TEXT,
    skills TEXT[] DEFAULT '{}',
    preferred_roles TEXT[] DEFAULT '{}',
    graduation_year INT DEFAULT 2026,
    department TEXT DEFAULT 'cse',
    job_type TEXT DEFAULT 'both',
    years_of_experience INT DEFAULT 0,
    preferred_locations TEXT[] DEFAULT '{}',
    paused BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    resume_text TEXT,
    referral_code TEXT UNIQUE,
    referred_by TEXT,
    is_premium BOOLEAN DEFAULT FALSE,
    premium_until TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Jobs Cache Table
CREATE TABLE IF NOT EXISTS jobs_cache (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT,
    url TEXT UNIQUE,
    scraped_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    category TEXT DEFAULT 'tech',
    description TEXT,
    remote_class TEXT,
    min_years_experience INT DEFAULT 0,
    required_skills TEXT[] DEFAULT '{}',
    preferred_skills TEXT[] DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE
);

-- 3. Seen Jobs Table (Global Deduplication)
CREATE TABLE IF NOT EXISTS seen_jobs (
    url_hash TEXT PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. Sent Jobs Table (Per-Student Tracking)
CREATE TABLE IF NOT EXISTS sent_jobs (
    chat_id BIGINT NOT NULL,
    job_url_hash TEXT NOT NULL,
    sent_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (chat_id, job_url_hash)
);

-- 5. Job Feedback Table
CREATE TABLE IF NOT EXISTS job_feedback (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    job_id TEXT,
    is_relevant BOOLEAN,
    feedback_time TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 6. Matching Queue Table
CREATE TABLE IF NOT EXISTS matching_queue (
    chat_id BIGINT PRIMARY KEY,
    status TEXT DEFAULT 'pending',
    generated_report TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for high-speed queries
CREATE INDEX IF NOT EXISTS idx_jobs_cache_active ON jobs_cache(is_active);
CREATE INDEX IF NOT EXISTS idx_students_active ON students(paused);
