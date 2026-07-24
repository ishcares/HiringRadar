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
from supabase.lib.client_options import SyncClientOptions
import httpx

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singleton Supabase client — import `supabase` from this module everywhere
# ---------------------------------------------------------------------------
_url: str = os.getenv("SUPABASE_URL", "")
_key: str = os.getenv("SUPABASE_KEY", "")

if not _url or not _key:
    logger.warning("SUPABASE_URL or SUPABASE_KEY not set — DB calls will fail.")

# Disable HTTP/2 to prevent HTTP/2 socket / Errno 11 connection pooling bugs
httpx_client = httpx.Client(http2=False)
options = SyncClientOptions(httpx_client=httpx_client)
supabase: Client = create_client(_url, _key, options=options) if (_url and _key) else None  # type: ignore


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _url_hash(url: str) -> str:
    """Normalizes and returns a stable 10-char MD5 hash of a job URL."""
    # Remove common tracking parameters to prevent duplicate alerts from minor URL changes
    clean_url = url.split("?")[0]
    # Keep greenhouse/lever IDs if they are in the query parameters
    if "gh_jid=" in url:
        jid = url.split("gh_jid=")[1].split("&")[0]
        clean_url += f"?gh_jid={jid}"
    elif "gh_src=" in url:
        src = url.split("gh_src=")[1].split("&")[0]
        clean_url += f"?gh_src={src}"
        
    return hashlib.md5(clean_url.encode()).hexdigest()[:10]


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
# referral + premium — viral growth system
#
# HOW IT WORKS:
#   1. Every student gets a unique 8-char referral_code when they sign up.
#   2. /share gives them: t.me/Bot?start=ref_<code>
#   3. When someone joins via that link, we store referred_by = their code.
#   4. When referrer hits 3 successful referrals → auto-upgrade to premium 7 days.
#   5. Premium users: instant alerts. Free users: 2-hour delayed alerts.
# ---------------------------------------------------------------------------

def generate_referral_code(chat_id: int) -> str:
    """
    Deterministic 8-char code from chat_id.
    Same chat_id always produces same code — safe to call repeatedly.
    """
    return hashlib.md5(str(chat_id).encode()).hexdigest()[:8]


def ensure_referral_code(chat_id: int) -> str:
    """
    Make sure a student has a referral_code. Creates one if missing.
    Returns the code.
    """
    code = generate_referral_code(chat_id)
    try:
        supabase.table("students").update({"referral_code": code}).eq("chat_id", chat_id).is_("referral_code", "null").execute()
    except Exception as e:
        logger.error("ensure_referral_code failed: %s", e)
    return code


def record_referral(new_chat_id: int, referrer_code: str) -> bool:
    """
    Called when a new user joins via a referral link.
    Stores who referred them, then checks if referrer earned premium.
    Returns True if referrer was upgraded to premium.
    """
    try:
        # Store the referral on the new user's profile
        supabase.table("students").update({"referred_by": referrer_code}).eq("chat_id", new_chat_id).execute()

        # Count how many people the referrer has successfully brought in
        count_res = (
            supabase.table("students")
            .select("chat_id", count="exact")
            .eq("referred_by", referrer_code)
            .execute()
        )
        referral_count = count_res.count or 0

        # Every 3 referrals → 7 days of premium
        if referral_count % 3 == 0:
            from datetime import datetime, timezone, timedelta
            premium_until = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
            supabase.table("students").update({
                "is_premium": True,
                "premium_until": premium_until,
            }).eq("referral_code", referrer_code).execute()
            logger.info("Upgraded referrer %s to premium (7 days)", referrer_code)
            return True
    except Exception as e:
        logger.error("record_referral failed: %s", e)
    return False


def get_referral_stats(chat_id: int) -> dict:
    """Return referral code and how many people have joined via it."""
    try:
        res = supabase.table("students").select("referral_code, is_premium, premium_until").eq("chat_id", chat_id).execute()
        if not res.data:
            return {"code": None, "count": 0, "is_premium": False}
        row = res.data[0]
        code = row.get("referral_code") or ensure_referral_code(chat_id)
        count_res = supabase.table("students").select("chat_id", count="exact").eq("referred_by", code).execute()
        return {
            "code": code,
            "count": count_res.count or 0,
            "is_premium": row.get("is_premium", False),
            "premium_until": row.get("premium_until"),
        }
    except Exception as e:
        logger.error("get_referral_stats failed: %s", e)
        return {"code": None, "count": 0, "is_premium": False}


def is_student_premium(chat_id: int) -> bool:
    """
    Check if a student has active premium.
    Handles expiry: if premium_until is in the past, treats as free.
    """
    try:
        from datetime import datetime, timezone
        res = supabase.table("students").select("is_premium, premium_until").eq("chat_id", chat_id).execute()
        if not res.data:
            return False
        row = res.data[0]
        if not row.get("is_premium"):
            return False
        premium_until = row.get("premium_until")
        if premium_until is None:
            return True  # no expiry = lifetime
        return datetime.fromisoformat(premium_until) > datetime.now(timezone.utc)
    except Exception as e:
        logger.error("is_student_premium failed: %s", e)
        return False


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
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "id":         _job_id(job),
            "company":    job["company"],
            "title":      job["title"],
            "location":   job.get("location", "Not specified"),
            "description": job.get("description", ""),
            "url":        job["url"],
            "category":   job.get("category", "tech"),
            "is_active":  True,
            "remote_class": job.get("remote_class", "india"),
            "scraped_at": now_iso,
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


def get_cached_jobs(delay_hours: int = 0) -> list[dict]:
    """
    Read all currently active jobs from the cache.
    If delay_hours is specified, only returns jobs scraped at least delay_hours ago.
    """
    try:
        query = supabase.table("jobs_cache").select("id, company, title, location, url, scraped_at, category, description, remote_class, min_years_experience, required_skills, preferred_skills").eq("is_active", True)
        res = query.execute()
        jobs = res.data or []
        
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        
        # Enforce a hard 36-hour maximum age limit for ALL alerts to prevent sending stale jobs
        max_age_cutoff = now - timedelta(hours=36)
        
        # Enforce minimum delay cutoff if delay_hours is specified
        delay_cutoff = now - timedelta(hours=delay_hours) if delay_hours > 0 else None
        
        filtered = []
        for j in jobs:
            scraped_at_str = j.get("scraped_at")
            if scraped_at_str:
                try:
                    t_str = scraped_at_str.replace("Z", "+00:00")
                    t_val = datetime.fromisoformat(t_str)
                    
                    # Job must be fresher than 36 hours
                    if t_val < max_age_cutoff:
                        continue
                        
                    # For free tier, job must also be older than the delay cutoff
                    if delay_cutoff and t_val > delay_cutoff:
                        continue
                        
                    filtered.append(j)
                except ValueError:
                    # If date parsing fails, default to include it
                    filtered.append(j)
            else:
                filtered.append(j)
        return filtered
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


def check_and_deactivate_dead_link(job_id: str, url: str) -> bool:
    """
    Check if a job link is still live.
    If it is closed/inactive, we update 'is_active = False' in Supabase and return False.
    """
    import requests
    try:
        resp = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        if resp.status_code in [404, 410]:
            raise ValueError(f"HTTP {resp.status_code} Page Closed")
            
        text = resp.text.lower()
        closed_signals = [
            "no longer available",
            "job posting not found",
            "this job is closed",
            "position is closed",
            "no longer accepting applications",
            "this posting has expired"
        ]
        for signal in closed_signals:
            if signal in text:
                raise ValueError(f"Found closed signal: '{signal}'")
                
        return True
    except Exception as e:
        logger.warning("check_and_deactivate_dead_link: deactivating %s because of error: %s", url, e)
        try:
            supabase.table("jobs_cache").update({"is_active": False}).eq("id", job_id).execute()
        except Exception as db_err:
            logger.error("Failed to update jobs_cache deactivation: %s", db_err)
        return False

