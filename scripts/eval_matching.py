#!/usr/bin/env python3
"""
Offline matching evaluation — run personas against job fixtures or live scrape.

Usage:
    python scripts/eval_matching.py                  # fixtures only (offline)
    python scripts/eval_matching.py --live           # scrape live jobs (needs network)
    python scripts/eval_matching.py --threshold 0.30 # sweep threshold
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from matching import match_jobs_for_student, build_match_reason, group_jobs


def load_json(name: str) -> list:
    path = ROOT / "tests" / "fixtures" / name
    with open(path) as f:
        return json.load(f)


def mock_embed_fn(texts):
    """Deterministic mock — no HF API needed."""
    vectors = []
    for i, text in enumerate(texts):
        if i == 0:
            vectors.append([1.0, 0.0, 0.0])
        else:
            vectors.append([0.85, 0.1 * i, 0.05])
    return vectors


def print_persona_report(student: dict, jobs: list, threshold: float, use_mock: bool):
    embed_fn = mock_embed_fn if use_mock else None
    kwargs = {"threshold": threshold, "top_n": 5}
    if use_mock:
        kwargs["embed_fn"] = mock_embed_fn

    matched = match_jobs_for_student(student, jobs, **kwargs)
    print(f"\n{'='*60}")
    print(f"Persona: {student['name']}")
    print(f"  Roles: {student['preferred_roles']} | Type: {student['job_type']} | Grad: {student['graduation_year']}")
    print(f"  Skills: {', '.join(student['skills'])}")
    print(f"  Threshold: {threshold} | Matches: {len(matched)}")
    print(f"{'-'*60}")

    if not matched:
        print("  (no matches)")
        return

    for job, score in matched:
        reason = build_match_reason(job, student)
        print(f"  [{round(score * 100):>3}%] {job['company']} — {job['title']}")
        print(f"         {reason}")


def main():
    parser = argparse.ArgumentParser(description="Evaluate HiringRadar matching offline")
    parser.add_argument("--live", action="store_true", help="Scrape live jobs instead of fixtures")
    parser.add_argument("--threshold", type=float, default=0.25, help="Match threshold (default 0.25)")
    parser.add_argument("--mock", action="store_true", default=True, help="Use mock embeddings (default)")
    parser.add_argument("--real-embeddings", action="store_true", help="Call HF API for real embeddings")
    args = parser.parse_args()

    use_mock = not args.real_embeddings
    students = load_json("sample_students.json")

    if args.live:
        from scraper import get_all_jobs
        print("Scraping live jobs...")
        jobs = group_jobs(get_all_jobs())
        print(f"Loaded {len(jobs)} open roles")
    else:
        jobs = load_json("sample_jobs.json")
        print(f"Using {len(jobs)} fixture jobs (offline)")

    if use_mock:
        print("Embedding mode: MOCK (offline)")
    else:
        print("Embedding mode: LIVE HF API")

    for student in students:
        print_persona_report(student, jobs, args.threshold, use_mock)

    # Threshold sweep
    if args.threshold == 0.25:
        print(f"\n{'='*60}")
        print("Threshold sweep (2026 Backend Intern persona, mock embeddings):")
        student = students[0]
        for t in [0.15, 0.20, 0.25, 0.30, 0.35]:
            matched = match_jobs_for_student(student, jobs, threshold=t, embed_fn=mock_embed_fn)
            print(f"  threshold={t:.2f} -> {len(matched)} matches")


if __name__ == "__main__":
    main()
