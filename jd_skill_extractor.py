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
Extract technical skills and experience requirements from this job description. Return raw JSON only — no markdown, no explanation.

Schema:
{{
  "required_skills": [...],
  "preferred_skills": [...],
  "min_experience_years": <int or 0>
}}

Rules:
- Extract SPECIFIC, ATOMIC skills — not category summaries. For example:
  * BAD: "Full Stack Development", "Distributed Systems"
  * GOOD: "C++", "Python", "Java", "Go", "JIRA", "GDB", "Microservices", "SaaS Architecture", "Linux", "Windows", "Agile/Scrum"
- If a sentence or bullet point lists multiple items separated by commas, slashes, or conjunctions (e.g. "C++, Python / Java / Go"), extract each item as its own separate atomic skill string.
- required_skills: skills and technologies explicitly stated as expectations/must-haves or mandatory requirements (e.g., under headers like "HOW YOU'LL SPEND YOUR TIME" or direct requirement statements).
- preferred_skills: skills and technologies listed as "plus", "nice to have", "preferred", "bonus", or under soft-ask/nice-to-have framing (e.g., "we'd love if you have", "exposure to").
- min_experience_years: the minimum number of years of experience required for the role (as an integer). For example, if it says "2+ years of experience" extract 2. If it says "minimum 3 years" extract 3. If a range is given (e.g. "3-5 years"), extract the lower bound (3). If not specified, default to 0.
- Include tools (e.g. JIRA, Github, GDB, Testrail), environments/platforms (e.g. Linux, Windows), and methodologies (e.g. Agile, Scrum) as atomic skills — do not omit them as "not technical enough."
- Exclude general/soft skills (e.g., "communication", "teamwork", "problem solving").
- Skill names should be short and standard.

Job Description:
{description}
"""


def extract_skills_from_jd(title: str, company: str, description: str) -> dict:
    """
    Extract structured skills and experience from a job description using Gemini.
    Includes exponential backoff to handle 429 Resource Exhausted rate limits.
    First checks Supabase jobs_cache to avoid duplicate API calls.

    Returns:
        {"required_skills": [...], "preferred_skills": [...], "min_experience_years": int}
    or an empty dict on failure.
    """
    client = _get_client()
    if not client or not description:
        return {}

    # 1. Check Supabase cache first
    sb = _get_supabase()
    matched_row_id = None
    should_update_description = False
    if sb is not None:
        try:
            res = (
                sb.table("jobs_cache")
                .select("id, required_skills, preferred_skills, description, min_years_experience")
                .eq("title", title)
                .eq("company", company)
                .execute()
            )
            for row in (res.data or []):
                db_desc = (row.get("description") or "").strip()
                # Match if descriptions match, or if the DB description is empty/missing
                if not description or not db_desc or db_desc[:500].strip() == description[:500].strip():
                    matched_row_id = row.get("id")
                    should_update_description = not db_desc
                    req = row.get("required_skills")
                    pref = row.get("preferred_skills")
                    min_exp = row.get("min_years_experience")
                    if req or pref or min_exp is not None:
                        logger.info("Found cached skills in Supabase for '%s' @ %s", title, company)
                        return {
                            "required_skills": req or [],
                            "preferred_skills": pref or [],
                            "min_experience_years": min_exp or 0
                        }
                    break
        except Exception as e:
            logger.warning("Cache lookup failed for '%s' @ %s: %s", title, company, e)

    # 2. Extract via Gemini if not cached
    prompt = _EXTRACT_PROMPT.format(description=description[:15000])

    import time
    max_retries = 3
    delay = 5.0

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
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
            min_exp   = result.get("min_experience_years", 0)
            if not isinstance(required, list) or not isinstance(preferred, list):
                raise ValueError("Invalid structure")

            # 3. Store newly extracted skills back in Supabase cache
            if sb is not None and matched_row_id:
                try:
                    update_payload = {
                        "required_skills": required,
                        "preferred_skills": preferred,
                        "min_years_experience": min_exp
                    }
                    if should_update_description:
                        update_payload["description"] = description
                    
                    sb.table("jobs_cache").update(update_payload).eq("id", matched_row_id).execute()
                    logger.info("Saved extracted skills to Supabase cache for '%s' @ %s (id: %s)", title, company, matched_row_id)
                except Exception as update_err:
                    logger.warning("Failed to update cache for id=%s: %s", matched_row_id, update_err)

            return {
                "required_skills": required,
                "preferred_skills": preferred,
                "min_experience_years": min_exp
            }

        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "exhausted" in err_str.lower() or "limit" in err_str.lower():
                logger.warning(
                    "Gemini API rate limit (429) on attempt %d/%d for '%s' @ %s. Retrying in %.1fs...",
                    attempt + 1, max_retries, title, company, delay
                )
                time.sleep(delay)
                delay *= 2.5  # exponential backoff
                continue
            
            logger.warning("JD skill extraction failed for '%s' @ %s: %s", title, company, e)
            return {}

    logger.error("Gemini API rate limit exceeded after %d retries for '%s' @ %s.", max_retries, title, company)
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
            .or_("required_skills.is.null,required_skills.eq.[]")
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
