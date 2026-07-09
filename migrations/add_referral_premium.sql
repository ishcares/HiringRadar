-- Migration: Add referral system + premium tier columns
-- Run in Supabase SQL Editor

-- Add referral & premium columns to students table
ALTER TABLE students
    ADD COLUMN IF NOT EXISTS referral_code   TEXT UNIQUE,
    ADD COLUMN IF NOT EXISTS referred_by     TEXT,          -- referral_code of who invited them
    ADD COLUMN IF NOT EXISTS is_premium      BOOLEAN DEFAULT false,
    ADD COLUMN IF NOT EXISTS premium_until   TIMESTAMPTZ;   -- NULL = no expiry if lifetime

-- Backfill referral codes for existing 50 users
-- Each user gets a unique 8-char code based on their chat_id
UPDATE students
SET referral_code = LOWER(SUBSTRING(MD5(chat_id::TEXT), 1, 8))
WHERE referral_code IS NULL;

-- Index for fast referral lookups
CREATE INDEX IF NOT EXISTS idx_students_referral_code ON students (referral_code);
CREATE INDEX IF NOT EXISTS idx_students_referred_by   ON students (referred_by);
