"""
stage_test.py — Staged test harness for HiringRadar

Runs 4 stages in order. Each stage must pass before the next runs.
Nothing touches the production bot or Supabase until you explicitly
run bot.py yourself.

Stage 1: Unit — scoring engine (no network, no DB)
Stage 2: Scraper smoke test — scrape 3 fast companies, check structure
Stage 3: DB read-only — read jobs_cache, check schema
Stage 4: Matching pipeline — pull real cached jobs, run match for 1 student

Usage:
    python stage_test.py            # run all stages
    python stage_test.py --stage 2  # run only stage 2
    python stage_test.py --stage 1 2 3  # run stages 1-3

Requires:
    .env with SUPABASE_URL and SUPABASE_KEY (for stages 3 & 4)
    sentence-transformers installed
    requests installed
"""

import sys
import os
import argparse
import traceback
import time

# ── Force UTF-8 output on Windows ────────────────────────────────────────────
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── Make sure imports resolve from project root ───────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"


def section(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def ok(msg: str):
    print(f"  [PASS] {msg}")


def fail(msg: str):
    print(f"  [FAIL] {msg}")


def info(msg: str):
    print(f"  [INFO] {msg}")


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 1 — Unit: scoring engine (no network, no DB, no Supabase import)
# ─────────────────────────────────────────────────────────────────────────────

def stage1_scoring():
    section("Stage 1 — Scoring Engine (no network)")
    from datetime import datetime

    try:
        from matching import (
            _build_profile_text, _score_jobs, match_jobs_for_student,
            get_experience_tag, is_senior, is_non_tech, _EMBED_CACHE,
            _W_TITLE, _W_JD, _W_KWORD,
        )
        from embeddings import get_embeddings_from_hf
        ok("matching + embeddings imported successfully")
    except Exception as e:
        fail(f"Import failed: {e}")
        return False

    current_year = datetime.now().year

    student = {
        "graduation_year": current_year,
        "department": "cse",
        "preferred_roles": ["backend"],
        "skills": ["Python", "Django", "PostgreSQL"],
        "job_type": "both",
        "preferred_locations": ["any"],
    }

    # Check profile text
    text = _build_profile_text(student)
    assert len(text) > 50, f"Profile text too short: {text!r}"
    ok(f"_build_profile_text: {len(text)} chars")
    info(f'  "{text[:100]}..."')

    # Check embedding
    embs = get_embeddings_from_hf([text])
    assert embs and len(embs[0]) == 384, "Expected 384-dim embeddings"
    ok(f"Embedding: dim={len(embs[0])}")

    # Score a small batch
    jobs = [
        {"company": "TestCo", "title": "Backend Software Engineer", "location": "Bangalore",
         "url": "https://test.io/1", "category": "tech",
         "description": "Build REST APIs with Python Django PostgreSQL"},
        {"company": "TestCo", "title": "Senior Staff Engineer", "location": "Bangalore",
         "url": "https://test.io/2", "category": "tech", "description": "10+ years required"},
        {"company": "TestCo", "title": "Customer Success Manager", "location": "Mumbai",
         "url": "https://test.io/3", "category": "business", "description": ""},
    ]
    _EMBED_CACHE.clear()
    scores, fallback = _score_jobs(jobs, student, ["backend"], get_embeddings_from_hf)

    assert not fallback, "Fell back to keyword-only — model not loaded?"
    assert len(scores) == 3
    assert all(0.0 <= s <= 1.0 for s in scores), f"Score out of range: {scores}"
    ok(f"_score_jobs: {[f'{s:.3f}' for s in scores]}  (fallback={fallback})")

    # Non-tech must be 0
    assert scores[2] == 0.0, f"Non-tech should be 0, got {scores[2]}"
    ok(f"Non-tech penalty: 0.0 (correct)")

    # Senior should score lower than junior match
    assert scores[1] < scores[0], (
        f"Senior ({scores[1]:.3f}) should score lower than junior match ({scores[0]:.3f})"
    )
    ok(f"Senior penalty: {scores[1]:.3f} < {scores[0]:.3f} (correct)")

    info(f"Weights: title={_W_TITLE}, jd={_W_JD}, kword={_W_KWORD}")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 2 — Scraper smoke test (live HTTP, 3 fast companies only)
# ─────────────────────────────────────────────────────────────────────────────

def stage2_scraper():
    section("Stage 2 — Scraper Smoke Test (3 companies, live HTTP)")

    try:
        from scraper import (
            scrape_greenhouse_json, scrape_lever,
            is_india_location, check_job_relevance_and_category,
        )
        ok("scraper imported")
    except Exception as e:
        fail(f"Import failed: {e}")
        return False

    # 1. is_india_location unit tests
    cases = [
        ("Bangalore, India", True),
        ("Remote / India",   True),
        ("San Francisco, CA", False),
        ("Toronto, Canada",  False),
        ("Remote",           True),
        ("New York, Remote", True),   # blocklisted city but has Remote
        ("Hyderabad",        True),
    ]
    for loc, expected in cases:
        result = is_india_location(loc)
        if result == expected:
            ok(f"is_india_location({loc!r}) = {result}")
        else:
            fail(f"is_india_location({loc!r}) expected {expected}, got {result}")
            return False

    # 2. Scrape 2 small Greenhouse boards (fast, confirmed working)
    for name, token in [("Postman", "postman"), ("Glean", "gleanwork")]:
        t0 = time.time()
        try:
            jobs = scrape_greenhouse_json(name, token)
            elapsed = time.time() - t0
            ok(f"Greenhouse/{name}: {len(jobs)} India jobs in {elapsed:.1f}s")
            if jobs:
                j = jobs[0]
                assert "company" in j and "title" in j and "url" in j and "category" in j
                assert "description" in j, "description key missing from job dict"
                info(f"  Sample: {j['title']} @ {j['location']}")
        except Exception as e:
            fail(f"Greenhouse/{name}: {e}")
            return False

    # 3. Scrape 1 Lever board
    for name, slug in [("CRED", "cred")]:
        t0 = time.time()
        try:
            jobs = scrape_lever(name, slug)
            elapsed = time.time() - t0
            ok(f"Lever/{name}: {len(jobs)} India jobs in {elapsed:.1f}s")
            if jobs:
                j = jobs[0]
                assert "description" in j
                info(f"  Sample: {j['title']} (desc len={len(j.get('description',''))})")
        except Exception as e:
            fail(f"Lever/{name}: {e}")
            return False

    return True


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 3 — DB read-only: check jobs_cache schema
# ─────────────────────────────────────────────────────────────────────────────

def stage3_db():
    section("Stage 3 — DB Read-Only (jobs_cache schema check)")

    try:
        from db import supabase, get_cached_jobs
        if supabase is None:
            fail("Supabase client is None — check SUPABASE_URL and SUPABASE_KEY in .env")
            return False
        ok("Supabase client initialised")
    except Exception as e:
        fail(f"DB import failed: {e}")
        return False

    # Check jobs_cache has expected columns
    try:
        res = supabase.table("jobs_cache").select(
            "id, company, title, location, url, description, category, is_active, scraped_at"
        ).limit(5).execute()
        rows = res.data or []
        ok(f"jobs_cache schema OK — {len(rows)} sample rows fetched")
        if rows:
            r = rows[0]
            missing = [k for k in ["id","company","title","url","description","category"] if k not in r]
            if missing:
                fail(f"Missing columns in jobs_cache: {missing}")
                return False
            ok(f"All required columns present")
            desc = r.get('description') or ''
            ok(f"Sample: {r.get('company')} -- {r.get('title')} | desc_len={len(desc)}")
            # Count NULLs vs empty string — both mean no JD, but NULL = schema gap
            null_descs = sum(1 for row in rows if row.get('description') is None)
            if null_descs:
                info(f"  {null_descs}/{len(rows)} sample rows have NULL description (not empty string)")
                info("  This is fine — hybrid scorer falls back to title-only for these jobs")
    except Exception as e:
        fail(f"jobs_cache read failed: {e}")
        return False

    # Count active jobs
    try:
        count_res = supabase.table("jobs_cache").select("id", count="exact").eq("is_active", True).execute()
        count = count_res.count or 0
        ok(f"Active jobs in cache: {count}")
        if count == 0:
            info("  WARNING: 0 active jobs — run scraper.py first to populate cache")
    except Exception as e:
        fail(f"Count query failed: {e}")
        return False

    return True


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 4 — End-to-end matching: pull cached jobs, match for a test student
# ─────────────────────────────────────────────────────────────────────────────

def stage4_matching():
    section("Stage 4 — End-to-End Matching Pipeline")

    from datetime import datetime

    try:
        from db import get_cached_jobs
        from matching import match_jobs_for_student, build_match_reason, _EMBED_CACHE
        from embeddings import get_embeddings_from_hf
        ok("All modules imported")
    except Exception as e:
        fail(f"Import failed: {e}")
        return False

    jobs = get_cached_jobs(delay_hours=0)
    if not jobs:
        fail("No jobs in cache — run scraper.py first")
        return False
    ok(f"Fetched {len(jobs)} active jobs from cache")

    # Check description is flowing through
    with_desc = sum(1 for j in jobs if j.get("description"))
    info(f"  Jobs with description: {with_desc}/{len(jobs)} "
         f"({100*with_desc//len(jobs)}%)")

    current_year = datetime.now().year
    student = {
        "graduation_year": current_year,
        "department": "cse",
        "preferred_roles": ["backend", "fullstack"],
        "skills": ["Python", "Django", "REST API", "PostgreSQL"],
        "job_type": "both",
        "preferred_locations": ["any"],
    }

    _EMBED_CACHE.clear()
    t0 = time.time()
    matches = match_jobs_for_student(student, jobs, top_n=5, embed_fn=get_embeddings_from_hf)
    elapsed = time.time() - t0

    if not matches:
        fail("match_jobs_for_student returned 0 results — check threshold or job pool")
        return False

    ok(f"Matched {len(matches)} jobs in {elapsed:.1f}s")
    print()
    print(f"  {'Rank':<5} {'Company':<16} {'Title':<36} {'Score':<8} Reason")
    print(f"  {'----':<5} {'-------':<16} {'-----':<36} {'-----':<8} ------")
    for rank, (job, score) in enumerate(matches, 1):
        reason = build_match_reason(job, student)
        print(f"  {rank:<5} {job['company']:<16} {job['title'][:35]:<36} {score:<8.3f} {reason}")

    return True


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

STAGES = {
    1: ("Scoring Engine",        stage1_scoring),
    2: ("Scraper Smoke Test",    stage2_scraper),
    3: ("DB Schema Check",       stage3_db),
    4: ("End-to-End Matching",   stage4_matching),
}


def main():
    parser = argparse.ArgumentParser(description="HiringRadar staged test harness")
    parser.add_argument("--stage", nargs="+", type=int,
                        help="Which stages to run (default: all)")
    args = parser.parse_args()

    stages_to_run = args.stage if args.stage else list(STAGES.keys())

    results = {}
    for s in stages_to_run:
        if s not in STAGES:
            print(f"Unknown stage {s}. Valid: 1-4")
            continue
        name, fn = STAGES[s]
        try:
            passed = fn()
            results[s] = PASS if passed else FAIL
        except AssertionError as e:
            print(f"\n  [FAIL] Assertion: {e}")
            results[s] = FAIL
        except Exception as e:
            print(f"\n  [FAIL] Unexpected: {e}")
            traceback.print_exc()
            results[s] = FAIL

        # Stop if a stage fails (stages are sequential dependencies)
        if results[s] == FAIL:
            print(f"\n  Stage {s} FAILED — skipping remaining stages.")
            for remaining in stages_to_run:
                if remaining > s and remaining not in results:
                    results[remaining] = SKIP
            break

    # Summary
    print(f"\n{'='*70}")
    print("  RESULTS")
    print(f"{'='*70}")
    for s in stages_to_run:
        name, _ = STAGES[s]
        status = results.get(s, SKIP)
        icon = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}[status]
        print(f"  {icon}  Stage {s}: {name}")

    all_passed = all(v == PASS for v in results.values())
    print()
    if all_passed:
        print("  All stages passed. Safe to deploy.")
    else:
        print("  Fix failures above before deploying to production bot.")
    print(f"{'='*70}\n")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
