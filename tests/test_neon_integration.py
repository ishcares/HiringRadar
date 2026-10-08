import pytest
import os
import sys
from datetime import datetime, timezone

# Ensure project root in sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from db import (
    supabase,
    load_seen_jobs,
    save_seen_jobs,
    get_cached_jobs,
    has_student_seen_job,
    mark_student_seen_jobs,
    count_subscribers
)
from matching import (
    _build_profile_text,
    _build_job_text,
    match_jobs_for_student,
    build_match_reason
)

@pytest.fixture
def sample_student():
    return {
        "chat_id": 999999999,
        "name": "Test User",
        "skills": ["Java", "Spring Boot", "Python", "FastAPI", "SQL"],
        "preferred_roles": ["backend"],
        "graduation_year": 2026,
        "department": "cse",
        "job_type": "both",
        "paused": False
    }

def test_neon_connection():
    """Verify that Neon client is initialized and healthy."""
    assert supabase is not None, "Database client should be initialized"
    res = supabase.table("jobs_cache").select("id").limit(1).execute()
    assert isinstance(res.data, list)

def test_student_crud(sample_student):
    """Test full CRUD lifecycle of student profile in Neon."""
    chat_id = sample_student["chat_id"]
    
    # 1. Upsert Student
    res = supabase.table("students").upsert(sample_student, on_conflict="chat_id").execute()
    assert len(res.data) > 0

    # 2. Read Student
    fetch_res = supabase.table("students").select("*").eq("chat_id", chat_id).execute()
    assert len(fetch_res.data) == 1
    student = fetch_res.data[0]
    assert student["chat_id"] == chat_id
    assert "Java" in student["skills"]

    # 3. Update Student (Pause)
    supabase.table("students").update({"paused": True}).eq("chat_id", chat_id).execute()
    check_paused = supabase.table("students").select("paused").eq("chat_id", chat_id).execute()
    assert check_paused.data[0]["paused"] is True

    # 4. Clean up
    supabase.table("students").delete().eq("chat_id", chat_id).execute()
    verify_del = supabase.table("students").select("chat_id").eq("chat_id", chat_id).execute()
    assert len(verify_del.data) == 0

def test_seen_jobs_lifecycle():
    """Test global and per-student job deduplication in Neon."""
    test_hash = f"test_hash_{int(datetime.now().timestamp())}"
    
    # Save seen job
    save_seen_jobs([test_hash])
    seen_set = load_seen_jobs()
    from db import _url_hash
    assert _url_hash(test_hash) in seen_set

    # Test per-student seen
    test_chat = 888888888
    fake_url = "https://example.com/jobs/123"
    assert not has_student_seen_job(test_chat, fake_url)
    
    mark_student_seen_jobs(test_chat, [fake_url])
    assert has_student_seen_job(test_chat, fake_url)

    # Clean up test rows
    supabase.table("seen_jobs").delete().eq("url_hash", test_hash).execute()
    supabase.table("sent_jobs").delete().eq("chat_id", test_chat).execute()

def test_jobs_cache_queries():
    """Verify querying active jobs from Neon cache."""
    jobs = get_cached_jobs(delay_hours=0)
    assert isinstance(jobs, list)
    # Ensure all returned jobs have required keys
    if jobs:
        sample = jobs[0]
        assert "title" in sample
        assert "company" in sample
        assert "url" in sample

def test_structured_matching_with_live_db(sample_student):
    """Test running semantic matching against live Neon jobs."""
    jobs = get_cached_jobs(delay_hours=0)
    if not jobs:
        pytest.skip("No jobs in jobs_cache to match against.")
        
    matches = match_jobs_for_student(sample_student, jobs[:30], top_n=3, threshold=0.10)
    assert isinstance(matches, list)
    
    for job, score in matches:
        assert 0.0 <= score <= 1.0
        reason = build_match_reason(job, sample_student)
        assert len(reason) > 0
