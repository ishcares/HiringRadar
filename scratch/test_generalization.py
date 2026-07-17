import logging
from jd_skill_extractor import _get_supabase, extract_skills_from_jd

# Enable logging to see details
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_generalization():
    sb = _get_supabase()
    if not sb:
        print("Supabase client not available.")
        return
        
    try:
        # Fetch 3 active jobs that have descriptions and are NOT Cohesity
        res = (
            sb.table("jobs_cache")
            .select("id, title, company, description")
            .eq("is_active", True)
            .neq("company", "Cohesity")
            .neq("description", "")
            .not_.is_("description", "null")
            .limit(3)
            .execute()
        )
        
        jobs = res.data or []
        if not jobs:
            print("No jobs found in jobs_cache matching criteria.")
            return
            
        print(f"Found {len(jobs)} jobs to test.")
        
        for idx, job in enumerate(jobs, 1):
            title = job["title"]
            company = job["company"]
            description = job["description"]
            
            print("\n" + "="*80)
            print(f"TEST JOB {idx}: {title} @ {company} (ID: {job['id']})")
            print(f"Description length: {len(description)} chars")
            print("="*80)
            
            # Run extraction
            result = extract_skills_from_jd(title, company, description)
            print("Extracted skills:")
            import pprint
            pprint.pprint(result)
            
    except Exception as e:
        print(f"Generalization test failed: {e}")

if __name__ == "__main__":
    test_generalization()
