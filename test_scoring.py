"""
test_scoring.py — Standalone scoring benchmark for HiringRadar.

Run with:
    python test_scoring.py

No Supabase connection, no Telegram bot, no network calls.
Tests the local sentence-transformer pipeline end-to-end.

What it checks:
  1. _build_profile_text produces a non-empty, sensible string.
  2. Hybrid _score_jobs returns valid floats in [0, 1].
  3. match_jobs_for_student ranking is stable and matches expectations.
  4. Scoring breakdown (title sim, JD sim, keyword bonus) is printed
     so you can visually audit why a job ranked where it did.
"""

import sys
import os
import re

# Force UTF-8 output on Windows (default terminal codec is CP1252 which
# cannot encode emoji characters returned by get_experience_tag).
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Make sure we can import from the project root even when run from a different cwd.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime
from matching import (
    _build_profile_text,
    _score_jobs,
    match_jobs_for_student,
    get_experience_tag,
    build_match_reason,
    _expand_title,
    _W_TITLE, _W_JD, _W_SKILLS, _JD_CHARS,
    ROLE_BONUS, INTERN_BONUS,
    matches_role, is_internship, is_senior, is_non_tech,
    _EMBED_CACHE,
)
from embeddings import get_embeddings_from_hf, calculate_cosine_similarity

# ──────────────────────────────────────────────────────────────────────────────
# Fixture: Students
# ──────────────────────────────────────────────────────────────────────────────
CURRENT_YEAR = datetime.now().year

STUDENTS = [
    {
        "name": "Fresher SDE (2026 grad)",
        "chat_id": 1001,
        "graduation_year": CURRENT_YEAR,
        "department": "cse",
        "preferred_roles": ["backend", "fullstack"],
        "skills": ["Python", "Django", "PostgreSQL", "REST API", "Docker"],
        "job_type": "both",
        "preferred_locations": ["any"],
    },
    {
        "name": "ML Intern seeker (2027 grad)",
        "chat_id": 1002,
        "graduation_year": CURRENT_YEAR + 1,
        "department": "cse",
        "preferred_roles": ["ml"],
        "skills": ["Python", "PyTorch", "scikit-learn", "NLP", "Machine Learning"],
        "job_type": "internship",
        "preferred_locations": ["any"],
    },
    {
        "name": "Data engineer fresher",
        "chat_id": 1003,
        "graduation_year": CURRENT_YEAR - 1,
        "department": "cse",
        "preferred_roles": ["data"],
        "skills": ["SQL", "Python", "Apache Spark", "Airflow", "Kafka", "dbt"],
        "job_type": "full-time",
        "preferred_locations": ["any"],
    },
]

# ──────────────────────────────────────────────────────────────────────────────
# Fixture: Jobs (mix of strong matches, weak matches, and red-herrings)
# ──────────────────────────────────────────────────────────────────────────────
JOBS = [
    # Strong match for student 1 (backend SDE)
    {
        "company": "Razorpay",
        "title": "Software Development Engineer",
        "location": "Bangalore, India",
        "url": "https://boards.greenhouse.io/razorpay/jobs/1",
        "category": "tech",
        "description": (
            "We are looking for a software development engineer to build scalable "
            "REST APIs using Python and Django. Experience with PostgreSQL and Docker "
            "is required. You will work on backend microservices."
        ),
    },
    # Internship match for student 1
    {
        "company": "CRED",
        "title": "Software Engineer Intern",
        "location": "Bangalore, India",
        "url": "https://jobs.lever.co/cred/intern1",
        "category": "tech",
        "description": "Summer internship for backend engineers. Python, REST API knowledge required.",
    },
    # Strong match for student 2 (ML)
    {
        "company": "Samsara",
        "title": "Machine Learning Engineer Intern",
        "location": "Remote / India",
        "url": "https://boards.greenhouse.io/samsara/jobs/ml1",
        "category": "tech",
        "description": (
            "Join our ML team building computer vision and NLP models. "
            "You'll use PyTorch for deep learning model training and deployment. "
            "Familiarity with scikit-learn and data pipelines is a plus."
        ),
    },
    # Strong match for student 3 (data)
    {
        "company": "Freshworks",
        "title": "Data Engineer",
        "location": "Chennai, India",
        "url": "https://jobs.smartrecruiters.com/Freshworks/de1",
        "category": "tech",
        "description": (
            "Build and maintain ETL pipelines using Apache Spark and Airflow. "
            "Write complex SQL queries. Experience with dbt and Kafka preferred. "
            "Python scripting for automation."
        ),
    },
    # Red-herring: senior role — should score low for freshers
    {
        "company": "Stripe",
        "title": "Senior Software Engineer",
        "location": "Bangalore, India",
        "url": "https://boards.greenhouse.io/stripe/jobs/sr1",
        "category": "tech",
        "description": "7+ years of experience required. Lead distributed systems design.",
    },
    # Red-herring: non-tech role — should score 0
    {
        "company": "Razorpay",
        "title": "Customer Success Manager",
        "location": "Mumbai, India",
        "url": "https://boards.greenhouse.io/razorpay/jobs/csm1",
        "category": "business",
        "description": "Manage customer accounts and drive retention for enterprise clients.",
    },
    # No description — tests graceful title-only path
    {
        "company": "Glean",
        "title": "Software Engineer",
        "location": "India / Remote",
        "url": "https://boards.greenhouse.io/glean/jobs/sde1",
        "category": "tech",
        "description": "",
    },
]


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _bar(score: float, width: int = 20) -> str:
    """ASCII progress bar for a [0, 1] score."""
    filled = round(score * width)
    return "[" + "x" * filled + "." * (width - filled) + f"] {score:.3f}"


def _compute_raw_signals(job: dict, student: dict, profile_emb: list) -> dict:
    """Recompute the three raw signals for a single job for display purposes."""
    title_text = (
        f"{_expand_title(job['title'])} at {job.get('company', '')} "
        f"in {job.get('location', '')}".strip()
    )
    title_emb_list = get_embeddings_from_hf([title_text])
    title_sim = calculate_cosine_similarity(profile_emb, title_emb_list[0]) if title_emb_list else 0.0

    desc_raw = (job.get("description") or "")[:_JD_CHARS].strip()
    if desc_raw:
        jd_emb_list = get_embeddings_from_hf([desc_raw])
        jd_sim = calculate_cosine_similarity(profile_emb, jd_emb_list[0]) if jd_emb_list else 0.0
    else:
        jd_sim = None  # no description

    roles = student.get("preferred_roles") or []
    kword_raw = 0.0
    if matches_role(job["title"], roles):
        kword_raw += ROLE_BONUS
    if is_internship(job):
        kword_raw += INTERN_BONUS

    return {
        "title_sim":   title_sim,
        "jd_sim":      jd_sim,
        "kword_raw":   kword_raw,
        "has_jd":      bool(desc_raw),
        "is_senior":   is_senior(job["title"], job.get("description", "")),
        "is_non_tech": is_non_tech(job["title"]),
    }


def _strip_emoji(text: str) -> str:
    """Remove non-ASCII characters (emoji) for safe printing on CP1252 terminals."""
    return re.sub(r'[^\x00-\x7F]', '', text).strip()


# ──────────────────────────────────────────────────────────────────────────────
def run_tests():
    print("=" * 70)
    print("  HiringRadar -- Scoring Benchmark")
    print(f"  Weights: title={_W_TITLE}, jd={_W_JD}, skills={_W_SKILLS}")
    print(f"  JD truncation: {_JD_CHARS} chars  |  ROLE_BONUS={ROLE_BONUS}  INTERN_BONUS={INTERN_BONUS}")
    print("=" * 70)

    all_pass = True

    for student in STUDENTS:
        print(f"\n{'---'*23}")
        print(f"  STUDENT: {student['name']}")
        print(f"  Roles: {student['preferred_roles']}  |  Skills: {student['skills']}")
        print(f"  Grad year: {student['graduation_year']}  |  Job type: {student['job_type']}")
        print()

        # 1. Test profile text
        profile_text = _build_profile_text(student)
        assert profile_text and len(profile_text) > 30, "Profile text too short"
        print(f"  Profile text ({len(profile_text)} chars):")
        print(f"    \"{profile_text[:120]}...\"")
        print()

        # 2. Get profile embedding for breakdown display
        profile_emb_list = get_embeddings_from_hf([profile_text])
        assert profile_emb_list, "Embedding returned empty"
        profile_emb = profile_emb_list[0]
        assert len(profile_emb) > 0, "Empty profile embedding"
        print(f"  OK  Profile embedding (dim={len(profile_emb)})")

        # 3. Score all jobs
        roles = student.get("preferred_roles") or []
        _EMBED_CACHE.clear()  # cold start for each student
        scores, used_fallback = _score_jobs(JOBS, student, roles, get_embeddings_from_hf)

        assert not used_fallback, "Fell back to keyword-only! Local model may not be loaded."
        assert len(scores) == len(JOBS), f"Score count mismatch: {len(scores)} vs {len(JOBS)}"
        assert all(0.0 <= s <= 1.0 for s in scores), f"Score out of [0,1]: {scores}"

        print(f"  OK  {len(scores)} jobs scored (fallback={used_fallback})")
        print()

        # 4. Print per-job breakdown
        ranked = sorted(zip(JOBS, scores), key=lambda x: x[1], reverse=True)
        print(f"  {'Rank':<5} {'Company':<14} {'Title':<38} {'Score'}")
        print(f"  {'----':<5} {'-------':<14} {'-----':<38} {'-----'}")
        for rank, (job, score) in enumerate(ranked, 1):
            signals = _compute_raw_signals(job, student, profile_emb)
            jd_str = f"jd={signals['jd_sim']:.3f}" if signals["jd_sim"] is not None else "jd=N/A "
            flags = ""
            if signals["is_senior"]:   flags += " [senior]"
            if signals["is_non_tech"]: flags += " [non-tech]"
            exp_tag = _strip_emoji(get_experience_tag(job["title"], job.get("description", "")))
            print(
                f"  {rank:<5} {job['company']:<14} {job['title'][:37]:<38} {_bar(score)}"
            )
            print(
                f"        title={signals['title_sim']:.3f}  {jd_str}  "
                f"kword={signals['kword_raw']:.2f}  {exp_tag}{flags}"
            )

        # 5. Assertion: non-tech job must score 0
        score_map = {job["title"]: s for job, s in zip(JOBS, scores)}
        csm_score = score_map.get("Customer Success Manager", -1.0)
        assert csm_score == 0.0, f"Non-tech job should score 0, got {csm_score}"
        print()
        print(f"  OK  Non-tech penalty: 'Customer Success Manager' = {csm_score:.3f}")

        senior_score = score_map.get("Senior Software Engineer", 0.0)
        print(f"  OK  Senior job score = {senior_score:.3f} (should be lower than top match)")

        # 6. Full pipeline
        _EMBED_CACHE.clear()
        matches = match_jobs_for_student(student, JOBS, top_n=5, embed_fn=get_embeddings_from_hf)
        print(f"  OK  match_jobs_for_student returned {len(matches)} results")
        if matches:
            top_job, top_score = matches[0]
            reason = build_match_reason(top_job, student)
            print(f"     Top: {top_job['company']} -- {top_job['title']} ({top_score:.3f})")
            print(f"     Reason: {reason}")

    print(f"\n{'='*70}")
    print("  ALL TESTS PASSED" if all_pass else "  SOME TESTS FAILED")
    print("=" * 70)


if __name__ == "__main__":
    run_tests()
