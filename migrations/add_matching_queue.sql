-- Create matching_queue table to track pending Wizard of Oz resume checks
CREATE TABLE IF NOT EXISTS public.matching_queue (
    chat_id BIGINT PRIMARY KEY,
    job_url_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Enable RLS and make public for upserts
ALTER TABLE public.matching_queue ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow public read/write access to matching_queue" 
ON public.matching_queue FOR ALL USING (true) WITH CHECK (true);
