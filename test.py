"""
Backfill script: extract required_skills, experience_level, etc.
from existing job postings using Gemini 2.5 Flash.

SETUP:
    pip install google-generativeai supabase --break-system-packages

    Set these environment variables before running:
        SUPABASE_URL
        SUPABASE_KEY   (use service_role key, not anon, so you can UPDATE rows)
        GEMINI_API_KEY

RUN:
    python backfill_job_skills.py
"""

import os
import json
import time
from supabase import create_client
import google.generativeai as genai
from dotenv import load_dotenv
load_dotenv()  # loads from .env file in the same directory
# -----------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

EXTRACTION_PROMPT = """Extract structured data from this job posting. Output ONLY valid JSON, no markdown, no preamble.

JOB POSTING:
{jd_text}

Output this exact schema:
{{
  "required_skills": ["skill1", "skill2"],
  "nice_to_have_skills": ["skill1"],
  "experience_level": "fresher" | "0-1_years" | "1-3_years" | "3+_years" | "not_specified",
  "min_years_experience": <int or null>
}}

Rules:
- Only include skills explicitly stated as required, not inferred
- If experience isn't mentioned, use "not_specified" - don't guess
- Keep skill names normalized (e.g. "React.js" not "React JS" or "ReactJS")
"""


def extract_job_fields(jd_text: str) -> dict:
    """Call Gemini to extract structured fields from a job description."""
    prompt = EXTRACTION_PROMPT.format(jd_text=jd_text)
    response = model.generate_content(prompt)
    text = response.text.strip()

    # Strip markdown fences if Gemini adds them despite instructions
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    return json.loads(text)


def main():
    # Pull jobs that haven't been processed yet
    # Adjust column name "description" if yours is named differently
    result = (
        supabase.table("jobs_cache")
        .select("id, description")
        .eq("required_skills", "[]")  # only unprocessed rows
        .execute()
    )

    jobs = result.data
    print(f"Found {len(jobs)} jobs to process.")

    for i, job in enumerate(jobs):
        job_id = job["id"]
        jd_text = job.get("description", "")

        if not jd_text or not jd_text.strip():
            print(f"[{i+1}/{len(jobs)}] Skipping job {job_id} - no description text")
            continue

        try:
            fields = extract_job_fields(jd_text)

            supabase.table("jobs_cache").update({
                "required_skills": fields.get("required_skills", []),
                "nice_to_have_skills": fields.get("nice_to_have_skills", []),
                "experience_level": fields.get("experience_level", "not_specified"),
                "min_years_experience": fields.get("min_years_experience"),
            }).eq("id", job_id).execute()

            print(f"[{i+1}/{len(jobs)}] Updated job {job_id}: "
                  f"{fields.get('required_skills')} | {fields.get('experience_level')}")

        except Exception as e:
            print(f"[{i+1}/{len(jobs)}] FAILED job {job_id}: {e}")

        # small delay to avoid hitting rate limits
        time.sleep(0.5)

    print("Backfill complete.")


if __name__ == "__main__":
    main()