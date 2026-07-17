-- Migration: Add resume_text column to students table
-- Run in Supabase SQL Editor

ALTER TABLE public.students 
    ADD COLUMN IF NOT EXISTS resume_text TEXT;
