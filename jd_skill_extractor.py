"""
jd_skill_extractor.py — Background job that extracts required skills from job descriptions.

Runs alongside the scraper cycle. For each job in jobs_cache that has a
description but no required_skills, calls Gemini to extract a structured
skill list, then stores it back in Supabase.

Called from bot.py's scheduler:
    context.job_queue.run_repeating(extract_jd_skills_job, interval=1800, first=60)

Also callable standalone:
    python jd_skill_extractor.py
"""

import asyncio
import json
import logging
import os
import re

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Gemini client (same pattern as ai_agent.py / jd_extractor.py)
# ---------------------------------------------------------------------------
_gemini_client = None

def _get_client():
    global _gemini_client
    if _gemini_client is None:
        try:
            from google import genai
            key = os.getenv("GEMINI_API_KEY")
            if key:
                _gemini_client = genai.Client(api_key=key)
        except Exception as e:
            logger.warning("Gemini client init failed: %s", e)
    return _gemini_client


_EXTRACT_PROMPT = """\
Extract technical skills from this job description. Return raw JSON only — no markdown, no explanation.

Schema:
{{
  "required_skills": [...],
  "preferred_skills": [...]
}}

Rules:
- required_skills: technologies explicitly stated as required/mandatory/must-have
- preferred_skills: listed as "plus", "nice to have", "preferred", "bonus"
- Include: programming languages, frameworks, databases, tools, cloud platforms, protocols
- Exclude: "communication", "teamwork", "problem solving" and other soft skills
- Skill names: short and standard — "Kubernetes" not "container orchestration using Kubernetes"
- If no clear required vs preferred split, put all in required_skills

Job Description:
{description}
"""


def extract_skills_from_jd(title: str, company: str, description: str) -> dict:
    """
    Extract structured skills from a job description using Gemini.

    Returns:
        {"required_skills": [...], "preferred_skills": [...]}
    or an empty dict on failure.
    """
    client = _get_client()
    if not client or not description:
        return {}

    prompt = _EXTRACT_PROMPT.format(description=description[:2500])

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        text = (response.text or "").strip()

        # Strip markdown code fences if present
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        result = json.loads(text)

        # Validate structure
        required  = result.get("required_skills", [])
        preferred = result.get("preferred_skills", [])
        if not isinstance(required, list) or not isinstance(preferred, list):
            raise ValueError("Invalid structure")

        return {"required_skills": required, "preferred_skills": preferred}

    except json.JSONDecodeError as e:
        logger.warning("JD skill extraction JSON error for '%s' @ %s: %s", title, company, e)
        return {}
    except Exception as e:
        logger.warning("JD skill extraction failed for '%s' @ %s: %s", title, company, e)
        return {}


# ---------------------------------------------------------------------------
# DB helpers (avoid importing full db.py to keep this module lightweight)
# ---------------------------------------------------------------------------

def _get_supabase():
    from db import supabase
    return supabase


def get_jobs_pending_extraction(batch_size: int = 40) -> list[dict]:
    """
    Fetch jobs that have a description but no required_skills yet.
    Ordered by newest first so fresh jobs get skills first.
    """
    sb = _get_supabase()
    if sb is None:
        return []
    try:
        res = (
            sb.table("jobs_cache")
            .select("id, title, company, description")
            .eq("is_active", True)
            .is_("required_skills", "null")
            .neq("description", "")
            .not_.is_("description", "null")
            .order("scraped_at", desc=True)
            .limit(batch_size)
            .execute()
        )
        return res.data or []
    except Exception as e:
        logger.error("get_jobs_pending_extraction failed: %s", e)
        return []


def store_job_skills(job_id: str, skills: dict) -> None:
    """Write extracted skills back to jobs_cache."""
    sb = _get_supabase()
    if sb is None or not skills:
        return
    try:
        sb.table("jobs_cache").update({
            "required_skills":  skills.get("required_skills", []),
            "preferred_skills": skills.get("preferred_skills", []),
        }).eq("id", job_id).execute()
    except Exception as e:
        logger.error("store_job_skills failed for id=%s: %s", job_id, e)


# ---------------------------------------------------------------------------
# Main extraction loop — called by scheduler or CLI
# ---------------------------------------------------------------------------

async def run_extraction_batch(batch_size: int = 40) -> int:
    """
    Extract skills for up to `batch_size` pending jobs.
    Returns number of jobs successfully processed.
    """
    jobs = await asyncio.to_thread(get_jobs_pending_extraction, batch_size)
    if not jobs:
        logger.info("[jd_extractor] No pending jobs to extract")
        return 0

    logger.info("[jd_extractor] Extracting skills for %d jobs...", len(jobs))
    processed = 0

    for job in jobs:
        desc = (job.get("description") or "").strip()
        if not desc:
            continue

        skills = await asyncio.to_thread(
            extract_skills_from_jd,
            job["title"], job["company"], desc
        )

        if skills:
            await asyncio.to_thread(store_job_skills, job["id"], skills)
            processed += 1
            logger.debug(
                "[jd_extractor] %s @ %s → req=%d pref=%d",
                job["title"], job["company"],
                len(skills.get("required_skills", [])),
                len(skills.get("preferred_skills", [])),
            )

        # Rate limit: Gemini free tier allows ~2 req/s
        await asyncio.sleep(0.6)

    logger.info("[jd_extractor] Done. Extracted skills for %d/%d jobs.", processed, len(jobs))
    return processed


# bot.py scheduler hook
async def extract_jd_skills_job(context) -> None:
    """Called by APScheduler every 30 min from bot.py."""
    try:
        count = await run_extraction_batch(batch_size=40)
        if count:
            logger.info("[jd_extractor] Batch complete: %d jobs updated", count)
    except Exception as e:
        logger.error("[jd_extractor] Batch failed: %s", e)


# ---------------------------------------------------------------------------
# CLI entry point — python jd_skill_extractor.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    batch = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    print(f"Running JD skill extraction for up to {batch} jobs...")
    count = asyncio.run(run_extraction_batch(batch))
    print(f"Done. {count} jobs updated.")
