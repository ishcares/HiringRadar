-- migrations/add_skill_gap_snapshots.sql
-- Stores weekly skill gap snapshots for trend tracking.

CREATE TABLE IF NOT EXISTS skill_gap_snapshots (
    chat_id BIGINT NOT NULL REFERENCES students(chat_id) ON DELETE CASCADE,
    week_start DATE NOT NULL,
    readiness_score NUMERIC(4, 2) NOT NULL,
    top_gaps JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (chat_id, week_start)
);

-- Index for fast trend queries
CREATE INDEX IF NOT EXISTS idx_skill_gap_snapshots_trend ON skill_gap_snapshots(chat_id, week_start DESC);
