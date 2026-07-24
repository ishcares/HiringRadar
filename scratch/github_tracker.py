"""
Asynchronous Python engine to parse crowdsourced GitHub tables from SimplifyJobs
for target SWE/Internship opportunities, and dispatch alerts to Telegram.
"""
import os
import requests
import json
import logging
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
MY_CHAT_ID = "7401731570" # Ishita's Telegram Chat ID

# Corporate keywords to track
TARGET_COMPANIES = [
    "bloomberg", "jpmorgan", "barclays", "goldman", "morgan stanley", 
    "american express", "amex", "visa", "mastercard", "deutsche bank", 
    "amazon", "google", "microsoft"
]

TRACKER_URLS = [
    ("New Grad Positions", "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/README.md"),
    ("Summer 2026 Internships", "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/README.md")
]

CACHE_FILE = os.path.join(os.path.dirname(__file__), "seen_tracked_jobs.json")

def load_seen_tracked_jobs():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception as e:
            logger.error("Failed to load seen tracked jobs cache: %s", e)
    return set()

def save_seen_tracked_jobs(seen_set):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(list(seen_set), f, indent=2)
    except Exception as e:
        logger.error("Failed to save seen tracked jobs cache: %s", e)

def send_telegram_alert(message):
    if not BOT_TOKEN:
        logger.warning("BOT_TOKEN not set, skipping Telegram alert.")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": MY_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            logger.error("Failed to send Telegram alert: HTTP %d | %s", r.status_code, r.text)
    except Exception as e:
        logger.error("Error sending Telegram alert: %s", e)

def run_tracker_and_alert():
    logger.info("Starting SimplifyJobs GitHub tracker check...")
    headers = {"User-Agent": "HiringRadar-Tracker-Engine"}
def is_india_target(loc_str: str) -> bool:
    loc = loc_str.lower()
    # Explicitly block non-India targets
    blocked = [
        "usa", "united states", "u.s.", "uk", "london", "canada", "seattle", 
        "austin", "phoenix", "brighton", "redmond", "o'fallon", "san francisco", "seattle", "wa"
    ]
    if any(b in loc for b in blocked):
        # Keep if it explicitly mentions India
        if not any(k in loc for k in ["india", "bangalore", "bengaluru", "hyderabad"]):
            return False
            
    india_keywords = [
        "india", "bengaluru", "bangalore", "hyderabad", "pune", "mumbai", 
        "gurgaon", "gurugram", "noida", "chennai", "delhi", "remote", "anywhere"
    ]
    return any(k in loc for k in india_keywords)

def run_tracker_and_alert():
    logger.info("Starting SimplifyJobs GitHub tracker check...")
    headers = {"User-Agent": "HiringRadar-Tracker-Engine"}
    seen_jobs = load_seen_tracked_jobs()
    new_seen = set(seen_jobs)
    
    new_matches = []
    
    for board_name, url in TRACKER_URLS:
        try:
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code != 200:
                logger.error("Failed to fetch %s: HTTP %d", board_name, r.status_code)
                continue
                
            soup = BeautifulSoup(r.text, "html.parser")
            rows = soup.find_all("tr")
            
            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 3:
                    company_text = cols[0].text.strip()
                    role_text = cols[1].text.strip()
                    location_text = cols[2].text.strip()
                    
                    apply_link = ""
                    if len(cols) >= 4:
                        a_tags = cols[3].find_all("a", href=True)
                        for a in a_tags:
                            href = a["href"]
                            if "simplify.jobs" not in href or "apply" in href.lower():
                                apply_link = href
                                break
                    
                    # Generate a unique key for deduplication
                    job_key = f"{company_text}||{role_text}||{location_text}"
                    
                    company_lower = company_text.lower()
                    matched = [c for c in TARGET_COMPANIES if c in company_lower]
                    
                    if matched and is_india_target(location_text):
                        # Always log the match to stdout so the user sees it here
                        print(f"👉 MATCH FOUND: [{board_name}] {company_text} - {role_text} ({location_text})")
                        print(f"   Link: {apply_link}")
                        
                        if job_key not in seen_jobs:
                            new_seen.add(job_key)
                            new_matches.append({
                                "board": board_name,
                                "company": company_text,
                                "role": role_text,
                                "location": location_text,
                                "url": apply_link
                            })
                        
        except Exception as e:
            logger.error("Error checking %s: %s", board_name, e)
            
    if new_matches:
        logger.info("Found %d new target matching roles for India!", len(new_matches))
        # Alert for each matching role (max 10 to prevent spamming)
        for job in new_matches[:10]:
            link_str = f"[Apply Now]({job['url']})" if job['url'] else "_No direct link provided_"
            msg = (
                f"🚨 **HIRING RADAR ALERT** 🛰️\n\n"
                f"New target role detected on SimplifyJobs (India/Remote)!\n\n"
                f"• **Company:** {job['company']}\n"
                f"• **Role:** {job['role']}\n"
                f"• **Location:** {job['location']}\n"
                f"• **Source:** {job['board']}\n\n"
                f"🔗 {link_str}"
            )
            send_telegram_alert(msg)
            
        save_seen_tracked_jobs(new_seen)
    else:
        logger.info("No new target matching roles found on SimplifyJobs.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_tracker_and_alert()
