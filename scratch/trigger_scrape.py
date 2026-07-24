from db import upsert_jobs_cache
from scraper import get_all_jobs
from scratch.github_tracker import run_tracker_and_alert

print("Starting full scrape...")
jobs = get_all_jobs()
print(f"Total scraped: {len(jobs)} jobs")

interns = [j for j in jobs if any(k in j["title"].lower() for k in ["intern", "internship", "trainee"])]
print(f"Internship roles found: {len(interns)}")
for j in interns[:10]:
    print(f"  {j['company']} — {j['title']} [{j.get('location','')}]")

print("\nUploading to cache...")
upsert_jobs_cache(jobs)
print("Done! Cache updated.")

print("\nRunning GitHub SimplifyJobs tracker check...")
try:
    run_tracker_and_alert()
    print("GitHub SimplifyJobs tracker check completed successfully.")
except Exception as e:
    print(f"GitHub SimplifyJobs tracker check failed: {e}")

