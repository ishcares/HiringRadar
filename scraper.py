import os
import requests
import psycopg2

def get_db_connection():
    url = os.getenv("DATABASE_URL")
    return psycopg2.connect(url)

def is_india_location(location: str) -> bool:
    if not location:
        return True
    india_keywords = [
        "india", "bangalore", "bengaluru", "mumbai", "delhi",
        "hyderabad", "pune", "chennai", "noida", "gurgaon",
        "gurugram", "kolkata", "remote"
    ]
    blocklist = [
        "malaysia", "singapore", "us", "usa", "united states",
        "london", "uk", "europe", "australia", "canada",
        "new york", "san francisco", "seattle","turkiye","san francisco" "canada"
    ]
    location_lower = location.lower()
    if any(b in location_lower for b in blocklist):
        return False
    return any(k in location.lower() for k in india_keywords)

def is_relevant(title):
    keywords = [
        "engineer", "developer", "sde", "software", "backend", "frontend",
        "fullstack", "full-stack", "devops", "mobile", "android", "ios",
        "infra", "infrastructure", "platform", "security", "cloud",
        "engineering manager", "tech lead", "sde-2", "sde-3",
        "staff engineer", "principal engineer", "senior engineer",
        "senior developer", "senior software", "lead engineer",
        "senior data", "senior ml", "senior ai",
        "data scientist", "data engineer", "data analyst", "machine learning",
        "ml engineer", "ai engineer", "deep learning", "nlp",
        "product manager", "product analyst", "product intern",
        "ux", "ui designer",
        "intern", "internship", "trainee", "campus", "junior", "fresher",
        "new grad", "graduate engineer", "research engineer", "research intern",
        "applied scientist", "computer vision", "generative ai", "llm",
        "prompt engineer", "data science intern", "ml intern", "ai intern",
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

def scrape_greenhouse_json(company_name, board_token):
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
    try:
        response = requests.get(url, timeout=5)
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
        if not is_relevant(title):
            continue
        location = job.get("location", {}).get("name", "Not specified")
        if not is_india_location(location):
            continue
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
        response = requests.get(url, timeout=5)
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
        if not is_relevant(title):
            continue
        location = job["categories"].get("location", "Not specified")
        if not is_india_location(location):
            continue
        relevant.append({
            "company": company_name,
            "title": title,
            "location": location,
            "url": job["hostedUrl"]
        })
    return relevant

def get_all_jobs():
    all_jobs = []

    for name, token in [
        ("Razorpay", "razorpaysoftwareprivatelimited"),
        ("PhonePe", "phonepe"),
        ("Groww", "groww"),
        ("Postman", "postman"),
        ("Coinbase", "coinbase"),
        ("Rubrik", "rubrik"),
        ("Tekion", "tekion"),
        ("InMobi", "inmobi"),
        ("DeepMind", "deepmind"),
        ("Glean", "gleanwork"),
       
        
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
        ("FamPay", "fampay"),          # ✅ fintech for students, hires interns
        ("JumpCloud", "jumpcloud"),
        
    ]:
        try:
            all_jobs += scrape_lever(name, slug)
        except Exception as e:
            print(f"Error scraping Lever for {name}: {e}")

    return all_jobs

def load_seen_jobs():
    conn = get_db_connection()
    cur = conn.cursor()
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
        print(f"🔥 Detected {len(jobs)} new postings:")
        for job in jobs:
            print(f"\n⚡ {job['company']} - {job['title']}")
            print(f"   Location: {job['location']}")
            print(f"   Link: {job['url']}")

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
