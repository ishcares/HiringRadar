"""
db.py — Single Supabase client for the entire HiringRadar application.

Both scraper.py and bot.py import from here.
No psycopg2. No raw SQL. One connection pattern.

Tables used:
  students    — user profiles (chat_id, name, skills, roles, etc.)
  jobs_cache  — live job listings written by scraper, read by alert job + web app
  seen_jobs   — global channel broadcast deduplication (url_hash TEXT PK)
  sent_jobs   — per-student alert deduplication (chat_id + url_hash composite PK)
  job_feedback — thumbs up/down feedback from students
"""


import hashlib
import logging
import os

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singleton Supabase client — import `supabase` from this module everywhere
# ---------------------------------------------------------------------------
_url: str = os.getenv("SUPABASE_URL", "")
_key: str = os.getenv("SUPABASE_KEY", "")

if not _url or not _key:
    logger.warning("SUPABASE_URL or SUPABASE_KEY not set — DB calls will fail.")

supabase: Client = create_client(_url, _key) if (_url and _key) else None  # type: ignore


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _url_hash(url: str) -> str:
    """Stable 10-char MD5 hash of a job URL — used as dedup key."""
    return hashlib.md5(url.encode()).hexdigest()[:10]


# ---------------------------------------------------------------------------
# seen_jobs — global channel broadcast deduplication
# ---------------------------------------------------------------------------

def load_seen_jobs() -> set[str]:
    """Return the set of job URL hashes already broadcast to the channel."""
    try:
        res = supabase.table("seen_jobs").select("url_hash").execute()
        return {row["url_hash"] for row in (res.data or [])}
    except Exception as e:
        logger.error("load_seen_jobs failed: %s", e)
        return set()


def save_seen_jobs(new_urls: list[str]) -> None:
    """Persist newly-broadcast job URLs so they are not re-sent."""
    if not new_urls:
        return
    rows = [{"url_hash": _url_hash(url)} for url in new_urls]
    try:
        supabase.table("seen_jobs").upsert(rows, on_conflict="url_hash").execute()
    except Exception as e:
        logger.error("save_seen_jobs failed: %s", e)


# ---------------------------------------------------------------------------
# sent_jobs — per-student alert deduplication
# ---------------------------------------------------------------------------

def has_student_seen_job(chat_id: int, job_url: str) -> bool:
    """Return True if this student already received an alert for this job."""
    h = _url_hash(job_url)
    try:
        res = (
            supabase.table("sent_jobs")
            .select("job_url_hash")
            .eq("chat_id", chat_id)
            .eq("job_url_hash", h)
            .execute()
        )
        return bool(res.data)
    except Exception as e:
        logger.error("has_student_seen_job failed: %s", e)
        return False


def mark_student_seen_jobs(chat_id: int, job_urls: list[str]) -> None:
    """Record that a student was sent alerts for these jobs."""
    if not job_urls:
        return
    rows = [{"chat_id": chat_id, "job_url_hash": _url_hash(url)} for url in job_urls]
    try:
        supabase.table("sent_jobs").upsert(rows, on_conflict="chat_id,job_url_hash").execute()
    except Exception as e:
        logger.error("mark_student_seen_jobs failed: %s", e)


# ---------------------------------------------------------------------------
# students — subscriber management
# ---------------------------------------------------------------------------

def get_all_students() -> list[dict]:
    """Return all active (non-paused) student profiles."""
    try:
        res = (
            supabase.table("students")
            .select("*")
            .eq("paused", False)
            .execute()
        )
        return res.data or []
    except Exception as e:
        logger.error("get_all_students failed: %s", e)
        return []


def count_subscribers() -> int:
    """Count active students in the students table."""
    try:
        res = supabase.table("students").select("chat_id", count="exact").eq("paused", False).execute()
        return res.count or 0
    except Exception as e:
        logger.error("count_subscribers failed: %s", e)
        return 0


# ---------------------------------------------------------------------------
# jobs_cache — decoupled scrape / alert architecture
#
# WHY THIS EXISTS:
#   The old code called get_all_jobs() (36 HTTP requests, ~20s) inside the
#   same function that delivered Telegram alerts. One slow ATS = zero alerts.
#
#   Now the scraper writes jobs here every 5 min (Producer).
#   The alert job reads from here every 2 min (Consumer).
#   The Phase 2 web dashboard reads from here too — no scraping on page load.
# ---------------------------------------------------------------------------

import hashlib as _hashlib  # already imported above, alias avoids redeclaration


def _job_id(job: dict) -> str:
    """
    Stable unique ID for a job: hash of company + title + url.
    Using hash means the same job scraped twice gets the same ID → safe upsert.
    """
    raw = f"{job['company']}|{job['title']}|{job['url']}"
    return _hashlib.md5(raw.encode()).hexdigest()


def upsert_jobs_cache(jobs: list[dict]) -> int:
    """
    Write the current batch of live jobs to jobs_cache.

    Uses upsert (insert-or-update) so re-scraping the same job just
    refreshes its scraped_at timestamp — no duplicates ever.

    Returns the number of jobs upserted.
    """
    if not jobs:
        return 0
    rows = [
        {
            "id":         _job_id(job),
            "company":    job["company"],
            "title":      job["title"],
            "location":   job.get("location", "Not specified"),
            "url":        job["url"],
            "is_active":  True,
        }
        for job in jobs
    ]
    try:
        supabase.table("jobs_cache").upsert(rows, on_conflict="id").execute()
        logger.info("upsert_jobs_cache: wrote %d jobs", len(rows))
        return len(rows)
    except Exception as e:
        logger.error("upsert_jobs_cache failed: %s", e)
        return 0


def get_cached_jobs() -> list[dict]:
    """
    Read all currently active jobs from the cache.

    Called by the alert job — returns instantly from DB,
    no HTTP scraping involved.
    """
    try:
        res = (
            supabase.table("jobs_cache")
            .select("company, title, location, url")
            .eq("is_active", True)
            .execute()
        )
        return res.data or []
    except Exception as e:
        logger.error("get_cached_jobs failed: %s", e)
        return []


def deactivate_stale_jobs(live_job_ids: set[str]) -> int:
    """
    Mark jobs as inactive if they no longer appear in the latest scrape.

    WHY: When a company closes a posting, Greenhouse/Lever removes it from
    their API. We don't delete it from our cache (audit trail) — we just
    set is_active=False so the alert job stops recommending it.

    Returns count of jobs deactivated.
    """
    try:
        # Get all currently active job IDs
        res = supabase.table("jobs_cache").select("id").eq("is_active", True).execute()
        all_active_ids = {row["id"] for row in (res.data or [])}

        stale_ids = all_active_ids - live_job_ids
        if not stale_ids:
            return 0

        # Deactivate in batches of 100 (Supabase IN filter limit)
        stale_list = list(stale_ids)
        for i in range(0, len(stale_list), 100):
            batch = stale_list[i:i + 100]
            supabase.table("jobs_cache").update({"is_active": False}).in_("id", batch).execute()

        logger.info("deactivate_stale_jobs: marked %d jobs inactive", len(stale_ids))
        return len(stale_ids)
    except Exception as e:
        logger.error("deactivate_stale_jobs failed: %s", e)
        return 0
