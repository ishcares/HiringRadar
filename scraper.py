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

    # Explicit India cities / country — checked FIRST. Multi-location postings
    # like "San Francisco, Bangalore, Remote" must pass even though a
    # blocklisted city also appears in the same string.
    india_keywords = [
        "india", "bangalore", "bengaluru", "mumbai", "delhi",
        "hyderabad", "pune", "chennai", "noida", "gurgaon",
        "gurugram", "kolkata",
    ]
    has_india = any(k in location_lower for k in india_keywords)
    if has_india:
        return True

    # Check for foreign countries/cities to block them even if they mention 'remote'
    # e.g., "Remote - USA", "Fully remote - Canada", "London (Remote)"
    foreign_blocklist = [
        "usa", "united states", "america", "canada", "london", "uk", "united kingdom",
        "europe", "singapore", "malaysia", "germany", "france", "turkey", "turkiye", "türkiye"
    ]
    # If it lists a foreign country and doesn't explicitly mention India, block it
    if any(f in location_lower for f in foreign_blocklist):
        # Allow only if it is a multi-location post that also includes India
        return False

    # Remote → always India-accessible ✅
    remote_keywords = ["remote", "work from anywhere", "worldwide", "wfh"]
    if any(r in location_lower for r in remote_keywords):
        return True

    # Hard blocklist — only reached if no India keyword and no remote keyword matched above
    hard_blocklist = [
        "malaysia", "singapore", "united states", "us, ", " usa",
        "london", "uk,", "europe", "canada",
        "new york", "san francisco", "seattle",
        "turkiye", "türkiye", "turkey", "ankara", "istanbul",
        # Other non-India, non-remote countries
        "berlin", "amsterdam", "dubai", "uae", "japan", "china",
    ]
    if any(b in location_lower for b in hard_blocklist):
        return False

    return False


INELIGIBLE_PROGRAM_KEYWORDS = [
    "skillbridge", "dod skillbridge", "active duty service member",
    "active duty military", "transitioning service member",
    "military spouse fellowship",
]

def is_program_restricted(title: str, description: str = "") -> bool:
    """Blocks listings tied to eligibility programs Indian candidates can't apply to
    (e.g. DoD SkillBridge, which requires active-duty US military status)."""
    text = f"{title} {description}".lower()
    return any(kw in text for kw in INELIGIBLE_PROGRAM_KEYWORDS)


def get_remote_class(location: str) -> str:
    """
    Classifies a location that already PASSED is_india_location() into:
    - 'india'          : explicit India city/country mentioned
    - 'remote_unclear'  : passed only because it said "remote"/"worldwide"/"wfh"
                          with NO country stated — could be US-only, EU-only, etc.
                          Do not treat as equivalent to a confirmed India role.
    """
    if not location:
        return "remote_unclear"
    loc = location.lower()
    india_keywords = [
        "india", "bangalore", "bengaluru", "mumbai", "delhi",
        "hyderabad", "pune", "chennai", "noida", "gurgaon",
        "gurugram", "kolkata",
    ]
    if any(k in loc for k in india_keywords):
        return "india"
    remote_keywords = ["remote", "work from anywhere", "worldwide", "wfh"]
    if any(r in loc for r in remote_keywords):
        return "remote_unclear"
    return "india"


def is_relevant(title):
    """Filters core tech roles (SDE, DevOps, Cloud, etc.)"""
    keywords = [
        "engineer", "developer", "sde", "software", "backend", "frontend",
        "fullstack", "full-stack", "devops", "mobile", "android", "ios",
        "infra", "infrastructure", "platform", "security", "cloud",
        "engineering manager", "tech lead", "sde-2", "sde-3",
        "staff engineer", "principal engineer", "senior engineer",
        "senior developer", "senior software", "lead engineer",
    ]
    blocklist = [
        "customer success", "customer support", "sales", "marketing",
        "business development", "account manager", "account executive",
        "human resources", "hr ", "recruiter", "talent", "legal",
        "finance", "accounting", "operations manager", "program manager",
        "content", "copywriter", "brand", "growth manager",
        "associate, ", "associate -", "collection", "collections",
        "lending", "credit officer", "operations", "commercial",
        "logistics", "supply chain", "procurement", "dceo", "facilities",
        "hardware", "mechanical", "electrical", "civil", "construction",
        "technician", "support specialist", "specialist,", "specialist -", "specialist ",
        # Senior/Experience blocks — "staff" catches Staff Engineer, Staff PM etc.
        "senior", "sr.", "sr ", "staff ", "staff,", "lead", "manager", "principal",
        "architect", "director", "vp", "chief", "head of", "head,",
        "sde-2", "sde-3", "sde ii", "sde iii",
        "experienced", "mid-level", "mid level",
    ]
    title_lower = title.lower()
    if any(bad in title_lower for bad in blocklist):
        return False
    return any(keyword in title_lower for keyword in keywords)


def is_data_science_relevant(title: str) -> bool:
    """Filters Data Science, Machine Learning, and AI roles."""
    keywords = [
        "data scientist", "data engineer", "machine learning", "ml engineer",
        "ai engineer", "deep learning", "nlp", "research engineer",
        "research intern", "applied scientist", "computer vision",
        "generative ai", "llm", "prompt engineer", "data science intern",
        "ml intern", "ai intern", "data analyst", "business analyst",
        "analytics manager", "analytics lead"
    ]
    blocklist = [
        "customer support", "customer success", "sales",
        "human resources", "recruiter", "marketing", "legal",
        # Senior/Experience blocks
        "senior", "sr.", "sr ", "lead", "manager", "principal", "architect",
        "director", "vp", "chief", "experienced", "mid-level", "mid level"
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
        "business development", "program manager",
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


def is_finance_tech_relevant(title: str) -> bool:
    """
    FinTech/bank-specific tech roles that is_relevant() misses.
    Banks use different naming conventions from product companies.
    """
    keywords = [
        "technology analyst",      # JPMorgan, Goldman entry-level
        "software analyst",
        "associate - technology",
        "technology associate",
        "quantitative analyst",    # quant roles
        "quant developer",
        "trading technology",
        "investment technology",
        "markets technology",
        "global technology",       # Citi/HSBC naming
        "tech analyst",
    ]
    blocklist = [
        "senior", "vp", "director", "head", "lead", "manager",
        "vice president", "executive director", "managing director",
    ]
    t = title.lower()
    if any(b in t for b in blocklist):
        return False
    return any(k in t for k in keywords)


def check_job_relevance_and_category(title: str) -> str | None:
    """Classifies job titles into target categories or returns None if not relevant."""
    if is_data_science_relevant(title):
        return "data_science"
    if is_relevant(title) or is_finance_tech_relevant(title):
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
            
            # Block program-restricted listings (DoD SkillBridge, etc.)
            if is_program_restricted(title):
                continue
                
            # Workday list API does not expose full job descriptions.
            relevant.append({
                "company": company_name,
                "title": title,
                "location": location,
                "url": job_url,
                "category": category,
                "description": "",
                "remote_class": get_remote_class(location),
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
            loc = job.get("location") or {}
            location = ", ".join(filter(None, [
                loc.get("city", ""),
                loc.get("country", ""),
                "Remote" if loc.get("remote") else "",
            ])) or "Not specified"
            if not is_india_location(location):
                continue

            job_id = job.get("id", "")
            job_url = (
                f"https://jobs.smartrecruiters.com/{company_id}/{job_id}"
            )
            
            # Block program-restricted listings
            if is_program_restricted(title):
                continue
                
            # SmartRecruiters posting list does not include full descriptions.
            relevant.append({
                "company": company_name,
                "title": title,
                "location": location,
                "url": job_url,
                "category": category,
                "description": "",
                "remote_class": get_remote_class(location),
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
        
        # Block program-restricted listings
        if is_program_restricted(title):
            continue
            
        relevant.append({
            "company": company_name,
            "title": title,
            "location": location,
            "url": job_url,
            "category": category,
            "description": "",
            "remote_class": get_remote_class(location),
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

    try:
        jobs = response.json()
    except Exception as e:
        print(f"Failed to fetch {company_name}: invalid JSON ({e})")
        return []

    relevant = []

    for job in jobs:
        # Use .get() throughout — a single malformed posting (missing
        # 'text', 'categories', or 'hostedUrl') must not crash the whole
        # company's scrape and lose every other valid job in this batch.
        title = job.get("text", "")
        if not title:
            continue
        category = check_job_relevance_and_category(title)
        if not category:
            continue
        location = (job.get("categories") or {}).get("location", "Not specified")
        if not is_india_location(location):
             continue
        job_url = job.get("hostedUrl", "")
        description = job.get("descriptionPlain", "") or job.get("description", "")
        
        # Block program-restricted listings (lever has full description text available)
        if is_program_restricted(title, description):
            continue
            
        relevant.append({
            "company": company_name,
            "title": title,
            "location": location,
            "url": job_url,
            "category": category,
            "description": description, 
            "remote_class": get_remote_class(location),
        })
    return relevant

def scrape_ashby(company_name, company_token):
    # Try public API first
    api_url = f"https://api.ashbyhq.com/v1/iframe/web/jobs?jobBoardId={company_token}"
    try:
        response = requests.get(api_url, timeout=10)
        if response.status_code == 200:
            jobs = response.json().get('jobs', [])
            relevant = []
            for j in jobs:
                title = j.get('title', '')
                category = check_job_relevance_and_category(title)
                if not category:
                    continue
                location = j.get('location', 'Not specified')
                if not is_india_location(location):
                    continue
                description = j.get('descriptionPlain', '') or j.get('descriptionHtml', '') or ''
                
                # Block program-restricted listings (Ashby API lists description)
                if is_program_restricted(title, description):
                    continue
                    
                relevant.append({
                    "company": company_name,
                    "title": title,
                    "location": location,
                    "url": j.get('jobUrl', ''),
                    "category": category,
                    "description": description,
                    "remote_class": get_remote_class(location),
                })
            return relevant
    except Exception as e:
        print(f"Ashby API failed for {company_name}: {e}")

    # Fallback to jobs.ashbyhq.com HTML parser if API throws 401
    try:
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin
        web_url = f"https://jobs.ashbyhq.com/{company_token}"
        web_res = requests.get(web_url, timeout=10)
        if web_res.status_code == 200:
            soup = BeautifulSoup(web_res.text, 'html.parser')
            relevant = []
            for a in soup.find_all('a', href=True):
                if f"/{company_token}/" in a['href']:
                    job_url = urljoin(web_url, a['href'])
                    title_elem = a.find('h4')
                    title = title_elem.text.strip() if title_elem else a.text.strip()
                    if not title:
                        continue
                    category = check_job_relevance_and_category(title)
                    if not category:
                        continue
                    # Ashby HTML board doesn't expose location without a subpage crawl.
                    # We accept all listings here — the detail page fetch (if added later)
                    # can refine the location. For now we tag as Remote / India.
                    
                    # Block program-restricted listings
                    if is_program_restricted(title):
                        continue
                        
                    relevant.append({
                        "company": company_name,
                        "title": title,
                        "location": "Remote / India",
                        "url": job_url,
                        "category": category,
                        "description": "",
                        "remote_class": "india",  # Hardcoded fallback target matching
                    })
            return relevant
    except Exception as e:
        print(f"Ashby HTML fallback failed for {company_name}: {e}")
    return []

def scrape_keka(company_name, tenant):
    web_url = f"https://{tenant}.keka.com/careers"
    try:
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin
        res = requests.get(web_url, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            relevant = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                if "/applyjob/" in href:
                    job_url = urljoin(web_url, href)
                    title = a.text.strip()
                    # Clean title if it contains apply text
                    title = title.replace("Apply", "").strip()
                    category = check_job_relevance_and_category(title)
                    if not category:
                        continue
                    
                    # Try to check location from surrounding text elements in Keka
                    location = "India / Remote"
                    parent = a.find_parent()
                    if parent:
                        parent_text = parent.text.lower()
                        # If a non-India location is found in the card, filter it out
                        if not is_india_location(parent_text):
                            continue
                            
                    # Block program-restricted listings
                    if is_program_restricted(title):
                        continue
                        
                    # Keka HTML board does not include job descriptions inline.
                    relevant.append({
                        "company": company_name,
                        "title": title,
                        "location": location,
                        "url": job_url,
                        "category": category,
                        "description": "",
                        "remote_class": get_remote_class(location),
                    })
            return relevant
    except Exception as e:
        print(f"Keka fetch failed for {company_name}: {e}")
    return []

def scrape_icims(company_name, customer_token):
    web_url = f"https://{customer_token}.icims.com/jobs/search?pr=0&in_iframe=1"
    try:
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin
        res = requests.get(web_url, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            relevant = []
            # iCIMS lists jobs inside table rows or divs with class 'container-fluid'
            for a in soup.find_all('a', href=True):
                href = a['href']
                if "/jobs/" in href and "/candidate" not in href:
                    job_url = urljoin(web_url, href)
                    # Get title and clean it
                    title = a.text.strip()
                    if not title or len(title) < 3 or "click" in title.lower():
                        continue
                    category = check_job_relevance_and_category(title)
                    if not category:
                        continue
                    
                    # Locate and validate location on iCIMS
                    location = "India / Remote"
                    parent = a.find_parent('div')
                    if parent:
                        loc_elem = parent.find(class_='description')
                        if loc_elem:
                            location = loc_elem.text.strip()
                    if not is_india_location(location):
                        continue
                            
                    # Block program-restricted listings
                    if is_program_restricted(title):
                        continue
                            
                    # iCIMS HTML board does not include job descriptions inline.
                    relevant.append({
                        "company": company_name,
                        "title": title,
                        "location": location,
                        "url": job_url,
                        "category": category,
                        "description": "",
                        "remote_class": get_remote_class(location),
                    })
            return relevant
    except Exception as e:
        print(f"iCIMS fetch failed for {company_name}: {e}")
    return []


def scrape_amazon(max_results: int = 300) -> list[dict]:
    """
    Scrape Amazon/AWS India jobs using Amazon's internal JSON search API
    (the same endpoint their careers SPA calls — no auth required).

    Endpoint: https://amazon.jobs/en/search.json
    Filters:  country_code=IND, offset pagination, result_limit=100 per page

    NOTE: Google and Apple use SSR/JS-rendered React SPAs with no publicly
    accessible JSON API — they require Playwright for headless rendering.
    """
    base_url = "https://amazon.jobs/en/search.json"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, */*",
        "Referer": "https://amazon.jobs/en/search",
    }
    relevant = []
    offset = 0
    page_size = 100

    while len(relevant) < max_results:
        params = {
            "normalized_country_code[]": "IND",
            "result_limit": page_size,
            "offset": offset,
        }
        try:
            resp = requests.get(base_url, params=params, headers=headers, timeout=15)
        except Exception as e:
            print(f"Amazon fetch error at offset {offset}: {e}")
            break

        if resp.status_code != 200:
            print(f"Amazon API returned HTTP {resp.status_code} at offset {offset}")
            break

        try:
            data = resp.json()
        except Exception as e:
            print(f"Amazon JSON parse error: {e}")
            break

        jobs = data.get("jobs", [])
        if not jobs:
            break

        for job in jobs:
            title = job.get("title", "")
            category = check_job_relevance_and_category(title)
            if not category:
                continue

            city    = job.get("city", "")
            country = job.get("country_code", "")
            location = f"{city}, {country}".strip(", ") or "India"
            if not is_india_location(location):
                continue

            job_id  = job.get("id_icims") or job.get("job_id", "")
            job_url = f"https://amazon.jobs/en/jobs/{job_id}" if job_id else ""

            # Amazon's search API returns description, basic qualifications, and preferred qualifications separately.
            # Concatenate them all so we can parse experience requirements and run semantic match accurately.
            raw_desc = (
                (job.get("description") or "") + " " +
                (job.get("basic_qualifications") or "") + " " +
                (job.get("preferred_qualifications") or "")
            )
            import re as _re
            description = _re.sub(r"<[^>]+>", " ", raw_desc).strip()

            # Block program-restricted listings
            if is_program_restricted(title, description):
                continue

            relevant.append({
                "company":     "Amazon",
                "title":       title,
                "location":    location,
                "url":         job_url,
                "category":    category,
                "description": description,
                "remote_class": get_remote_class(location),
            })

        if len(jobs) < page_size:
            break  # last page
        offset += page_size

    return relevant


def scrape_amazon_interns(max_results: int = 100) -> list[dict]:
    """
    Same as scrape_amazon() but filters to internship job type only.
    Uses Amazon's search API with job_type[]=Intern filter.
    """
    base_url = "https://amazon.jobs/en/search.json"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, */*",
        "Referer": "https://amazon.jobs/en/search",
    }
    relevant = []
    offset = 0
    page_size = 100

    while len(relevant) < max_results:
        params = {
            "normalized_country_code[]": "IND",
            "job_type[]": "Intern",
            "result_limit": page_size,
            "offset": offset,
        }
        try:
            resp = requests.get(base_url, params=params, headers=headers, timeout=15)
        except Exception as e:
            print(f"Amazon intern fetch error at offset {offset}: {e}")
            break

        if resp.status_code != 200:
            break

        try:
            data = resp.json()
        except Exception:
            break

        jobs = data.get("jobs", [])
        if not jobs:
            break

        for job in jobs:
            title = job.get("title", "")
            # Don't filter by relevance keywords for intern roles — accept all tech interns
            category = check_job_relevance_and_category(title) or "tech"

            city    = job.get("city", "")
            country = job.get("country_code", "")
            location = f"{city}, {country}".strip(", ") or "India"
            if not is_india_location(location):
                continue

            job_id  = job.get("id_icims") or job.get("job_id", "")
            job_url = f"https://amazon.jobs/en/jobs/{job_id}" if job_id else ""

            # Concatenate description and qualifications
            raw_desc = (
                (job.get("description") or "") + " " +
                (job.get("basic_qualifications") or "") + " " +
                (job.get("preferred_qualifications") or "")
            )
            import re as _re
            description = _re.sub(r"<[^>]+>", " ", raw_desc).strip()

            if is_program_restricted(title, description):
                continue

            relevant.append({
                "company":      "Amazon",
                "title":        title,
                "location":     location,
                "url":          job_url,
                "category":     category,
                "description":  description,
                "remote_class": get_remote_class(location),
            })

        if len(jobs) < page_size:
            break
        offset += page_size

    return relevant


def get_all_jobs():
    all_jobs = []
    status_rows = []
    from datetime import datetime, timezone
    import csv
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # ── Greenhouse ────────────────────────────────────────────────────────────
    for name, token in [
        # Core Indian tech / MNCs
        ("Razorpay",      "razorpaysoftwareprivatelimited"),
        ("PhonePe",       "phonepe"),
        ("Groww",         "groww"),
        ("Postman",       "postman"),
        ("Coinbase",      "coinbase"),
        ("Rubrik",        "rubrik"),
        ("Tekion",        "tekion"),
        ("InMobi",        "inmobi"),
        ("DeepMind",      "deepmind"),
        ("Glean",         "gleanwork"),
        ("Stripe",        "stripe"),
        ("Samsara",       "samsara"),
        ("Mixpanel",      "mixpanel"),
        ("Zscaler",       "zscaler"),
        ("PagerDuty",     "pagerduty"),
        ("YugabyteDB",    "yugabyte"),
        ("Vercel",        "vercel"),
        ("Brex",          "brex"),
        ("Figma",         "figma"),
        ("Airtable",      "airtable"),
        ("Airbnb",        "airbnb"),
        ("Reddit",        "reddit"),
        ("Databricks",    "databricks"),
        ("MongoDB",       "mongodb"),
        ("Twilio",        "twilio"),
        ("Elastic",       "elastic"),
        ("Okta",          "okta"),
        ("Affirm",        "affirm"),
        ("Cloudflare",    "cloudflare"),
        ("Remote.com",    "remote"),
        ("Jane Street",   "janestreet"),
        ("Slice",         "slice"),
        ("Uber",          "uber"),
        ("Atlassian",     "atlassian"),
        # Indian startups & consumer brands (Greenhouse confirmed)
        ("boAt Lifestyle","imaginemarketingboat"),
        ("Urban Company", "urbanclap"),
        ("Dunzo",         "dunzo"),
        ("Rapido",        "rapido"),
        ("BlackBuck",     "blackbuck"),
        ("Mamaearth",     "honasconsumerlimited"),
        ("Ola",           "olacabs"),
        ("Lenskart",      "lenskart"),
        ("Vedantu",       "vedantu"),
        ("Unacademy",     "unacademy"),
        ("ShareChat",     "sharechat"),
        ("BharatPe",      "bharatpe"),
        ("BrowserStack",  "browserstack"),
        ("Hasura",        "hasura"),
        ("Setu",          "setu"),
        ("Hotstar",       "disneyhotstar"),
    ]:
        try:
            jobs = scrape_greenhouse_json(name, token)
            all_jobs += jobs
            status_rows.append([name, "Greenhouse", "Success", now_str, f"Found {len(jobs)} jobs"])
        except Exception as e:
            status_rows.append([name, "Greenhouse", "Failed", now_str, str(e)])
            print(f"Error scraping Greenhouse for {name}: {e}")

    # ── Lever ─────────────────────────────────────────────────────────────────
    for name, slug in [
        ("CRED",          "cred"),
        ("Meesho",        "meesho"),
        ("Paytm",         "paytm"),
        ("Hevo Data",     "hevodata"),
        ("Stable Money",  "stable-money1"),
        ("Zeta",          "zeta"),
        ("Sprinto",       "Sprinto"),
        ("Mindtickle",    "mindtickle"),
        ("fi.money",      "epifi"),
        ("FamPay",        "fampay"),
        ("JumpCloud",     "jumpcloud"),
        ("Pocket FM",     "pocketfm"),
        ("contentSquare", "contentsquare"),
    ]:
        try:
            jobs = scrape_lever(name, slug)
            all_jobs += jobs
            status_rows.append([name, "Lever", "Success", now_str, f"Found {len(jobs)} jobs"])
        except Exception as e:
            status_rows.append([name, "Lever", "Failed", now_str, str(e)])
            print(f"Error scraping Lever for {name}: {e}")

    # ── Workday ───────────────────────────────────────────────────────────────
    for name, tenant, board, wd in [
        ("Salesforce",    "salesforce", "External_Career_Site",      12),
        ("Nvidia",        "nvidia",     "NVIDIAExternalCareerSite",    5),
        ("Cohesity",      "cohesity",   "Cohesity_Careers",            5),
    ]:
        try:
            jobs = scrape_workday(name, tenant, board, wd)
            all_jobs += jobs
            status_rows.append([name, "Workday", "Success", now_str, f"Found {len(jobs)} jobs"])
        except Exception as e:
            status_rows.append([name, "Workday", "Failed", now_str, str(e)])
            print(f"Error scraping Workday for {name}: {e}")

    # ── Ashby ─────────────────────────────────────────────────────────────────
    for name, company_id in [
        ("Superhuman",    "superhuman"),
        ("PostHog",       "posthog"),
        ("Notion",        "notion"),
        ("Linear",        "linear"),
        ("Moengage",      "moengage"),
        ("Chargebee",     "chargebee"),
        ("Khatabook",     "khatabook"),
        ("Exotel",        "exotel"),
        ("Recko",         "recko"),
        ("BetterPlace",   "betterplace"),
        ("Vokal",         "vokal"),
        ("Smallcase",     "smallcase"),
        ("Jar",           "jar"),
        ("Refyne",        "refyne"),
    ]:
        try:
            jobs = scrape_ashby(name, company_id)
            all_jobs += jobs
            status_rows.append([name, "Ashby", "Success", now_str, f"Found {len(jobs)} jobs"])
        except Exception as e:
            status_rows.append([name, "Ashby", "Failed", now_str, str(e)])
            print(f"Error scraping Ashby for {name}: {e}")

    # ── Keka Hire ─────────────────────────────────────────────────────────────
    for name, tenant in [
        ("Jupiter",        "jupiter"),
        ("Chalo",          "chalo"),
        ("Epigamia",       "epigamia"),
        ("Toppr",          "toppr"),
        ("mFine",          "mfine"),
        ("Park+",          "parkplus"),
        ("Loco",           "loco"),
        ("Zupay",          "zupay"),
        ("Obvious",        "obvious"),
        ("Jar App",        "jarapp"),
        ("Spotdraft",      "spotdraft"),
        ("Progcap",        "progcap"),
        ("Volopay",        "volopay"),
        ("Mindtickle",     "mindtickle"),
        ("Scaler",         "scaler"),
        ("Newton School",  "newtonschool"),
        ("Teachmint",      "teachmint"),
        ("Airmeet",        "airmeet"),
    ]:
        try:
            jobs = scrape_keka(name, tenant)
            all_jobs += jobs
            status_rows.append([name, "Keka Hire", "Success", now_str, f"Found {len(jobs)} jobs"])
        except Exception as e:
            status_rows.append([name, "Keka Hire", "Failed", now_str, str(e)])
            print(f"Error scraping Keka for {name}: {e}")

    # ── iCIMS ─────────────────────────────────────────────────────────────────
    for name, token in [
        ("GitHub",       "careers-githubinc"),
        ("Synchrony",    "careers-synchronyfinancial"),
        ("NCR Voyix",    "careers-ncrvoyix"),
        ("Conduent",     "careers-conduent"),
        ("Sabre",        "careers-sabre"),
        ("Unison",       "careers-unisonpoint"),
    ]:
        try:
            jobs = scrape_icims(name, token)
            all_jobs += jobs
            status_rows.append([name, "iCIMS", "Success", now_str, f"Found {len(jobs)} jobs"])
        except Exception as e:
            status_rows.append([name, "iCIMS", "Failed", now_str, str(e)])
            print(f"Error scraping iCIMS for {name}: {e}")

    # ── Amazon Jobs — Full-time (India) ──────────────────────────────────────
    try:
        amazon_jobs = scrape_amazon(max_results=300)
        all_jobs += amazon_jobs
        status_rows.append(["Amazon", "Custom JSON API", "Success", now_str, f"Found {len(amazon_jobs)} jobs"])
    except Exception as e:
        status_rows.append(["Amazon", "Custom JSON API", "Failed", now_str, str(e)])
        print(f"Error scraping Amazon: {e}")

    # ── Amazon Jobs — Internships (India) ─────────────────────────────────────
    try:
        amazon_intern_jobs = scrape_amazon_interns(max_results=100)
        all_jobs += amazon_intern_jobs
        status_rows.append(["Amazon (Intern)", "Custom JSON API", "Success", now_str, f"Found {len(amazon_intern_jobs)} intern jobs"])
    except Exception as e:
        status_rows.append(["Amazon (Intern)", "Custom JSON API", "Failed", now_str, str(e)])
        print(f"Error scraping Amazon interns: {e}")

    # Write status health report to CSV sheet
    try:
        status_file = "company_status.csv"
        with open(status_file, "w", newline="", encoding="utf-8") as sf:
            writer = csv.writer(sf)
            writer.writerow(["Company Name", "ATS System", "Status", "Last Attempted (UTC)", "Details"])
            writer.writerows(status_rows)
    except PermissionError:
        print("Warning: company_status.csv is locked. Skipping status write.")

    # ── Deduplicate all scraped jobs by URL ───────────────────────────────────
    # Prevents "ON CONFLICT DO UPDATE command cannot affect row a second time"
    seen_urls = set()
    deduped_jobs = []
    for j in all_jobs:
        if j["url"] not in seen_urls:
            seen_urls.add(j["url"])
            deduped_jobs.append(j)

    return deduped_jobs





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