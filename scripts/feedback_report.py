#!/usr/bin/env python3
"""
Summarize 👍/👎 feedback from Supabase job_feedback table.

Usage:
    python scripts/feedback_report.py
"""

import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv()


def main():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        print("❌ Set SUPABASE_URL and SUPABASE_KEY in .env")
        sys.exit(1)

    from supabase import create_client
    supabase = create_client(url, key)

    res = supabase.table("job_feedback").select("*").execute()
    rows = res.data or []

    if not rows:
        print("No feedback recorded yet. Users need to tap 👍/👎 on job alerts.")
        return

    total = len(rows)
    counts = Counter(r["feedback"] for r in rows)
    relevant = counts.get("relevant", 0)
    skipped = counts.get("skip", 0)

    print(f"\n{'='*50}")
    print(f"HiringRadar Feedback Report")
    print(f"{'='*50}")
    print(f"Total feedback entries : {total}")
    print(f"👍 Relevant             : {relevant} ({100*relevant/total:.1f}%)")
    print(f"👎 Not for me            : {skipped} ({100*skipped/total:.1f}%)")

    # Per-user breakdown
    user_counts = Counter(r["chat_id"] for r in rows)
    print(f"\nUnique users who gave feedback: {len(user_counts)}")

    # Recent entries
    print(f"\nMost recent feedback (last 10):")
    for row in rows[-10:]:
        emoji = "👍" if row["feedback"] == "relevant" else "👎"
        print(f"  {emoji} chat_id={row['chat_id']} hash={row.get('job_url_hash', '?')}")


if __name__ == "__main__":
    main()
