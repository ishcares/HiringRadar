import logging
import os
import requests

from db import (
    load_seen_jobs,
    save_seen_jobs,
    has_student_seen_job,
    mark_student_seen_jobs,
    count_subscribers,
)

logger = logging.getLogger(__name__)

def is_india_location(location: str) -> bool:
    if not location:
        return True

    location_lower = location.lower()

    # Locations that are always blocked, even if "remote" appears alongside them
    hard_blocklist = [
        "malaysia", "singapore", "united states", "us, ", " usa",
        "london", "uk,", "europe", "australia", "canada",
        "new york", "san francisco", "seattle",
        # Turkey — ASCII and Unicode variants
        "turkiye", "türkiye", "turkey", "ankara", "istanbul",
        # Other non-India countries
        "berlin", "amsterdam", "dubai", "uae", "japan", "china",
        "brazil", "mexico", "france", "germany", "poland", "romania",
    ]
    if any(b in location_lower for b in hard_blocklist):
        return False

    # Pure remote (no country = India-accessible) ✅
    # e.g. "Remote", "Remote - Worldwide", "Work from Anywhere"
    remote_keywords = ["remote", "work from anywhere", "worldwide", "wfh"]
    if any(r in location_lower for r in remote_keywords):
        return True

    # Explicit India cities / country
    india_keywords = [
        "india", "bangalore", "bengaluru", "mumbai", "delhi",
        "hyderabad", "pune", "chennai", "noida", "gurgaon",
        "gurugram", "kolkata",
    ]
    return any(k in location_lower for k in india_keywords)


def is_relevant(title):
    """Filters core tech roles (SDE, ML, DevOps, etc.)"""
    keywords = [
        "engineer", "developer", "sde", "software", "backend", "frontend",
        "fullstack", "full-stack", "devops", "mobile", "android", "ios",
        "infra", "infrastructure", "platform", "security", "cloud",
        "engineering manager", "tech lead", "sde-2", "sde-3",
        "staff engineer", "principal engineer", "senior engineer",
        "senior developer", "senior software", "lead engineer",
        "senior data", "senior ml", "senior ai",
        "data scientist", "data engineer", "machine learning",
        "ml engineer", "ai engineer", "deep learning", "nlp",
        "research engineer", "research intern", "applied scientist",
        "computer vision", "generative ai", "llm", "prompt engineer",
        "data science intern", "ml intern", "ai intern",
    ]
    blocklist = [
        "customer success", "customer support", "sales", "marketing",
        "business development", "account manager", "account executive",
        "human resources", "hr ", "recruiter", "talent", "legal",
        "finance", "accounting", "operations manager", "program manager",
        "content", "copywriter", "brand", "growth manager",
        "associate, ", "associate -",
    ]
    title_lower = title.lower()
    if any(bad in title_lower for bad in blocklist):
        return False
    return any(keyword in title_lower for keyword in keywords)


def is_business_relevant(title: str) -> bool:
    """Filters MBA/Business roles (PM, APM, Analyst, Consulting, etc.)"""
    keywords = [
        "product manager", "apm", "associate product manager", "associate pm",
        "product analyst", "product intern", "product management",
        "business analyst", "operations analyst", "strategy analyst",
        "consultant", "management consultant", "management trainee",
        "growth manager", "growth analyst", "marketing analyst",
        "financial analyst", "investment analyst", "corporate finance",
        "business development", "program manager", "data analyst",
    ]
    blocklist = [
        "customer support", "customer success", "sales representative",
        "account executive", "human resources", "recruiter", "legal",
        "copywriter", "content writer", "seo", "social media",
    ]
    t = title.lower()
    if any(b in t for b in blocklist):
        return False
    return any(k in t for k in keywords)


def is_design_relevant(title: str) -> bool:
    """Filters Design roles (UX/UI, Product Design, etc.)"""
    keywords = [
        "design", "ux", "ui designer", "product design", "figma",
        "interaction designer", "visual designer", "creative director",
    ]
    blocklist = [
        "engineering", "developer", "sde", "writer",
    ]
    t = title.lower()
    if any(b in t for b in blocklist):
        return False
    return any(k in t for k in keywords)


def check_job_relevance_and_category(title: str) -> str | None:
    """Classifies job titles into target categories or returns None if not relevant."""
    if is_relevant(title):
        return "tech"
    if is_business_relevant(title):
        return "business"
    if is_design_relevant(title):
        return "design"
    return None

_WORKDAY_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

def scrape_workday(company_name, tenant, job_board, wd_num=1):
    """
    Scrape jobs from Workday's internal CXS JSON endpoint (POST-based).
    tenant   : subdomain, e.g. 'flipkart'
    job_board: board path, e.g. 'Flipkart_Careers'
    wd_num   : Workday instance number (usually 1, sometimes 3 or 5)
    """
    base_url = f"https://{tenant}.wd{wd_num}.myworkdayjobs.com"
    api_url  = f"{base_url}/wday/cxs/{tenant}/{job_board}/jobs"
    apply_base = f"{base_url}/en-US/{job_board}"

    relevant = []
    offset, limit, max_pages = 0, 20, 3   # cap at 60 jobs per company

    for _ in range(max_pages):
        payload = {
            "appliedFacets": {},
            "limit": limit,
            "offset": offset,
            "searchText": "",
        }
        for attempt in range(2):
            try:
                resp = requests.post(
                    api_url, json=payload,
                    headers=_WORKDAY_HEADERS, timeout=15
                )
                break
            except requests.exceptions.Timeout:
                if attempt == 0:
                    import time; time.sleep(2)
                    continue
                print(f"Failed to fetch {company_name} (Workday): timed out")
                return relevant
            except Exception as e:
                print(f"Failed to fetch {company_name} (Workday): {e}")
                return relevant

        if resp.status_code != 200:
            print(f"Failed to fetch {company_name} (Workday): HTTP {resp.status_code}")
            return relevant

        data = resp.json()
        postings = data.get("jobPostings", [])
        if not postings:
            break

        for job in postings:
            title = job.get("title", "")
            category = check_job_relevance_and_category(title)
            if not category:
                continue
            location = job.get("locationsText", "Not specified")
            if not is_india_location(location):
                continue
            external_path = job.get("externalPath", "")
            job_url = f"{apply_base}{external_path}"
            relevant.append({
                "company": company_name,
                "title": title,
                "location": location,
                "url": job_url,
                "category": category,
            })

        # Stop paginating if we got fewer results than the page size
        if len(postings) < limit:
            break
        offset += limit

    return relevant


def scrape_smartrecruiters(company_name: str, company_id: str):
    """
    Scrape jobs from SmartRecruiters public postings API.
    company_id : exact company identifier as it appears in SmartRecruiters URLs,
                 e.g. 'Freshworks', 'BrowserStack', 'Swiggy'
    API docs   : https://dev.smartrecruiters.com/customer-api/posting-api/
    """
    base_url = f"https://api.smartrecruiters.com/v1/companies/{company_id}/postings"
    relevant = []
    offset, limit = 0, 100

    while True:
        try:
            resp = requests.get(
                base_url,
                params={"limit": limit, "offset": offset},
                timeout=15,
            )
        except Exception as e:
            print(f"Failed to fetch {company_name} (SmartRecruiters): {e}")
            break

        if resp.status_code != 200:
            print(f"Failed to fetch {company_name} (SmartRecruiters): HTTP {resp.status_code}")
            break

        data = resp.json()
        postings = data.get("content", [])
        if not postings:
            break

        for job in postings:
            title = job.get("name", "")
            category = check_job_relevance_and_category(title)
            if not category:
                continue

            # Location — SmartRecruiters nests it under job.location
            loc = job.get("location", {})
            location = ", ".join(filter(None, [
                loc.get("city", ""),
                loc.get("country", ""),
                "Remote" if job.get("location", {}).get("remote") else "",
            ])) or "Not specified"
            if not is_india_location(location):
                continue

            job_id = job.get("id", "")
            job_url = (
                f"https://jobs.smartrecruiters.com/{company_id}/{job_id}"
            )
            relevant.append({
                "company": company_name,
                "title": title,
                "location": location,
                "url": job_url,
                "category": category,
            })

        # Paginate until exhausted
        if len(postings) < limit:
            break
        offset += limit

    return relevant


def scrape_greenhouse_json(company_name, board_token):
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
    for attempt in range(2):
        try:
            response = requests.get(url, timeout=15)
            break
        except requests.exceptions.Timeout:
            if attempt == 0:
                import time; time.sleep(2)
                continue
            print(f"Failed to fetch {company_name}: timed out after retrying")
            return []
        except Exception as e:
            print(f"Failed to fetch {company_name}: {e}")
            return []

    if response.status_code != 200:
        print(f"Failed to fetch {company_name}: {response.status_code}")
        return []

    payload = response.json()
    jobs = payload.get("jobs", [])
    relevant = []

    for job in jobs:
        title = job.get("title", "")
        category = check_job_relevance_and_category(title)
        if not category:
            continue
        location = job.get("location", {}).get("name", "Not specified")
        if not is_india_location(location):
            continue
        job_url = job.get("absolute_url", "")
        relevant.append({
            "company": company_name,
            "title": title,
            "location": location,
            "url": job_url,
            "category": category,
        })
    return relevant

def scrape_lever(company_name, company_slug):
    url = f"https://api.lever.co/v0/postings/{company_slug}?mode=json"
    for attempt in range(2):
        try:
            response = requests.get(url, timeout=15)
            break
        except requests.exceptions.Timeout:
            if attempt == 0:
                import time; time.sleep(2)
                continue
            print(f"Failed to fetch {company_name}: timed out after retrying")
            return []
        except Exception as e:
            print(f"Failed to fetch {company_name}: {e}")
            return []

    if response.status_code != 200:
        print(f"Failed to fetch {company_name}: {response.status_code}")
        return []

    jobs = response.json()
    relevant = []

    for job in jobs:
        title = job["text"]
        category = check_job_relevance_and_category(title)
        if not category:
            continue
        location = job["categories"].get("location", "Not specified")
        if not is_india_location(location):
            continue
        relevant.append({
            "company": company_name,
            "title": title,
            "location": location,
            "url": job["hostedUrl"],
            "category": category,
        })
    return relevant

def get_all_jobs():
    all_jobs = []

    for name, token in [
        # ── Existing ──────────────────────────────────────────
        ("Razorpay",  "razorpaysoftwareprivatelimited"),
        ("PhonePe",   "phonepe"),
        ("Groww",     "groww"),
        ("Postman",   "postman"),
        ("Coinbase",  "coinbase"),
        ("Rubrik",    "rubrik"),
        ("Tekion",    "tekion"),
        ("InMobi",    "inmobi"),
        ("DeepMind",  "deepmind"),
        ("Glean",     "gleanwork"),
        ("Stripe",    "stripe"),
        # ── Newly verified ────────────────────────────────────
        ("Samsara",   "samsara"),       # IoT/fleet tech, India R&D hub
        ("Mixpanel",  "mixpanel"),      # product analytics, India eng team
        ("Zscaler",   "zscaler"),       # cloud security, large India office
        ("PagerDuty", "pagerduty"),     # DevOps/SRE platform, India team
        ("YugabyteDB","yugabyte"),      # distributed SQL DB, India dev team
        ("Vercel",    "vercel"),        # frontend infra, remote-friendly
        ("Brex",      "brex"),          # fintech, India eng presence
        ("Figma",     "figma"),         # design tool, India team
        ("Airtable",  "airtable"),      # no-code platform, remote roles
    ]:

        try:
            all_jobs += scrape_greenhouse_json(name, token)
        except Exception as e:
            print(f"Error scraping Greenhouse for {name}: {e}")

    for name, slug in [
        ("CRED", "cred"),
        ("Meesho", "meesho"),
        ("Paytm", "paytm"),
        ("Hevo Data", "hevodata"),
        ("Stable Money", "stable-money1"),
        ("Zeta", "zeta"),
        ("Sprinto", "Sprinto"),
        ("Mindtickle", "mindtickle"),
        ("fi.money", "epifi"),
        ("FamPay", "fampay"),          # fintech for students, hires interns
        ("JumpCloud", "jumpcloud"),
    ]:
        try:
            all_jobs += scrape_lever(name, slug)
        except Exception as e:
            print(f"Error scraping Lever for {name}: {e}")

    # ── Workday (plain HTTP — no session needed) ───────────────────────────────
    # HTTP 200 = works | HTTP 422 = wrong board slug | Cloudflare = use playwright
    for name, tenant, board, wd in [
        ("Salesforce", "salesforce", "External_Career_Site", 12),  # verified
    ]:
        try:
            all_jobs += scrape_workday(name, tenant, board, wd)
        except Exception as e:
            print(f"Error scraping Workday for {name}: {e}")

    # ── SmartRecruiters (public postings API) ──────────────────────────────────
    # Verified via api.smartrecruiters.com/v1/companies/{id}/postings
    for name, company_id in [
        ("Freshworks",   "Freshworks"),    # 114 jobs verified — CRM/SaaS, India HQ
        ("BrowserStack", "BrowserStack"),  # board exists — testing platform, India HQ
        ("Chargebee",    "Chargebee"),     # board exists — billing SaaS, India team
        ("Zomato",       "zomato"),        # foodtech giant
    ]:
        try:
            all_jobs += scrape_smartrecruiters(name, company_id)
        except Exception as e:
            print(f"Error scraping SmartRecruiters for {name}: {e}")

    return all_jobs





def get_new_jobs() -> list[dict]:
    seen = load_seen_jobs()
    all_jobs = get_all_jobs()
    new_jobs = [job for job in all_jobs if job["url"] not in seen]
    if new_jobs:
        new_urls = [job["url"] for job in new_jobs]
        save_seen_jobs(new_urls)
    return new_jobs


if __name__ == "__main__":
    jobs = get_new_jobs()
    if not jobs:
        print("No new relevant jobs tracked in this run.")
    else:
        print(f"Detected {len(jobs)} new postings:")
        for job in jobs:
            print(f"  {job['company']} - {job['title']}")
            print(f"  Location: {job['location']}")
            print(f"  Link: {job['url']}")
