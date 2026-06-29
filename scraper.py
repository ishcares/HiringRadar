import os
import requests
import json
import psycopg2

def get_db_connection():
    url = os.getenv("DATABASE_URL")
    return psycopg2.connect(url)

def is_relevant(title):
    # Covers the full spectrum — freshers to senior engineers.
    # Deliberately avoids overbroad terms: 'data' catches 'data entry operator',
    # 'entry' catches anything, 'associate' catches 'sales associate'.
    keywords = [
        # Core engineering (catches Junior, Senior, Staff, Principal variants)
        "engineer", "developer", "sde", "software", "backend", "frontend",
        "fullstack", "full-stack", "devops", "mobile", "android", "ios",
        "infra", "infrastructure", "platform", "security", "cloud",
        # Senior / leadership roles
        "senior", "staff", "principal", "lead", "architect",
        "engineering manager", "tech lead", "sde-2", "sde-3",
        # Data & AI
        "data scientist", "data engineer", "data analyst", "machine learning",
        "ml engineer", "ai engineer", "deep learning", "nlp",
        # Product & Design
        "product manager", "product analyst", "product intern",
        "ux", "ui designer", "design",
        # Fresher / intern (tech-specific)
        "intern", "internship", "trainee", "campus", "junior", "fresher",
        "new grad", "graduate engineer","research engineer", "research intern", "applied scientist",
        "computer vision", "generative ai", "llm", "prompt engineer",
        "data science intern", "ml intern", "ai intern",
    ]
    title_lower = title.lower()
    return any(keyword in title_lower for keyword in keywords)

def scrape_greenhouse_json(company_name, board_token):
    """
    Upgraded from HTML to JSON API. Uses Greenhouse's official public endpoint.
    Completely immune to frontend layout shifts and structural design changes.
    """
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"

    try:
        response = requests.get(url, timeout=10)
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
        if is_relevant(title):
            # Extract standard values from Greenhouse payload
            location = job.get("location", {}).get("name", "Not specified")
            job_url = job.get("absolute_url", "")
            
            relevant.append({
                "company": company_name,
                "title": title,
                "location": location,
                "url": job_url
            })
    return relevant

def scrape_lever(company_name, company_slug):
    url = f"https://api.lever.co/v0/postings/{company_slug}?mode=json"
    try:
        response = requests.get(url, timeout=10)
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
        if is_relevant(title):
            relevant.append({
                "company": company_name,
                "title": title,
                "location": job["categories"].get("location", "Not specified"),
                "url": job["hostedUrl"]
            })
    return relevant

def get_all_jobs():
    all_jobs = []

    # Upgraded: Greenhouse companies use clean board tokens now instead of complex HTML slugs
    for name, token in [
        ("Razorpay", "razorpaysoftwareprivatelimited"),
        ("PhonePe", "phonepe"),
        ("Groww", "groww"),
        ("Postman", "postman"),
        ("Coinbase", "coinbase"),   # Verified: has Remote-India + Hybrid-Bangalore roles
        ("Rubrik", "rubrik"),       # Verified: active Bangalore intern + engineering roles
        ("Tekion", "tekion"),       # Verified: active Chennai/Bangalore fresher + engineering roles
        ("InMobi", "inmobi"), 
        
          # Verified: active India fresher + university roles
    ]:
        try:
            all_jobs += scrape_greenhouse_json(name, token)
        except Exception as e:
            print(f"Error scraping Greenhouse platform for {name}: {e}")

    # Lever companies
    for name, slug in [
        ("CRED", "cred"),
        ("Meesho", "meesho"),
        ("Freshworks", "freshworks"),
        ("Atlassian", "atlassian"),
        ("Paytm", "paytm"), 
        ("Upstox", "upstox"),              # ✅ stockbroking, hires interns
        ("Jupiter", "jupiter"),                    # ✅ new
        ("Hevo Data", "hevodata"),
        ("Stable Money", "stable-money1"),   # ✅ new
        ("Zeta", "zeta"),
        ("Sprinto", "Sprinto"),        # ✅ Indian SaaS security
        ("Mindtickle", "mindtickle"), # Major Indian SaaS — hires freshers heavily
    ]:
        try:
            all_jobs += scrape_lever(name, slug)
        except Exception as e:
            print(f"Error scraping Lever platform for {name}: {e}")

    return all_jobs

def load_seen_jobs():
    conn = get_db_connection()
    cur = conn.cursor()
    # Auto-initialize table if it doesn't exist yet on clean DB
    cur.execute("CREATE TABLE IF NOT EXISTS seen_jobs (url TEXT PRIMARY KEY)")
    cur.execute("SELECT url FROM seen_jobs")
    urls = set(row[0] for row in cur.fetchall())
    cur.close()
    conn.close()
    return urls

def save_seen_jobs(new_urls):
    conn = get_db_connection()
    cur = conn.cursor()
    for url in new_urls:
        cur.execute("INSERT INTO seen_jobs (url) VALUES (%s) ON CONFLICT DO NOTHING", (url,))
    conn.commit()
    cur.close()
    conn.close()

def get_new_jobs():        
    seen = load_seen_jobs()
    all_jobs = get_all_jobs()

    # 1. Filter out truly new jobs
    new_jobs = [job for job in all_jobs if job["url"] not in seen]

    if new_jobs:
        # 2. FIX: Extract explicit strings into a clean list
        new_urls = [job["url"] for job in new_jobs]
        
        # 3. Save to DB IMMEDIATELY before returning to the bot
        save_seen_jobs(new_urls)

    return new_jobs
        
if __name__ == "__main__":
    # Swapped to get_new_jobs() so you can run locally and only see fresh posts
    jobs = get_new_jobs()
    if not jobs:
        print("No new relevant jobs tracked in this run.")
    else:
        print(f"🔥 Detected {len(jobs)} new postings:")
        for job in jobs:
            print(f"\n⚡ {job['company']} - {job['title']}")
            print(f"   Location: {job['location']}")
            print(f"   Link: {job['url']}")

# --- Subscriber Management Functions Kept Intact ---
def save_subscriber(chat_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS subscribers (chat_id BIGINT PRIMARY KEY)")
    cur.execute("INSERT INTO subscribers (chat_id) VALUES (%s) ON CONFLICT DO NOTHING", (chat_id,))
    conn.commit()
    cur.close()
    conn.close()

def load_subscribers():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS subscribers (chat_id BIGINT PRIMARY KEY)")
    cur.execute("SELECT chat_id FROM subscribers")
    ids = set(row[0] for row in cur.fetchall())
    cur.close()
    conn.close()
    return ids

def count_subscribers():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM subscribers")
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count

def remove_subscriber(chat_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM subscribers WHERE chat_id = %s", (chat_id,))
    conn.commit()
    cur.close()
    conn.close()
