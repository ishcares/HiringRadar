import csv
import json
import re
import concurrent.futures
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# --- STEP 1: DEFINE TARGET COMPANIES ---
# Replace this list with your 60+ corporate web domains
COMPANY_DOMAINS = [
    "figma.com", "vercel.com", "stripe.com", "airbnb.com", "github.com", 
    "slack.com", "uber.com", "reddit.com", "databricks.com", "snowflake.com",
    "retool.com", "pinecone.io", "runwayml.com", "miro.com", "openai.com",
    "scale.com", "huggingface.co", "adobe.com", "paypal.com", "americanexpress.com",
    "canva.com", "clickup.com", "linear.app", "docker.com", "loom.com", "zoom.us",
    "atlassian.com", "hashicorp.com", "razorpay.com", "groww.in",
    "notion.so", "sentry.io", "vanta.com", "posthog.com", "ramp.com", "sourcegraph.com",
    "qualcomm.com", "nvidia.com", "amd.com", "intel.com", "arm.com", "mediatek.com",
    "slice.it", "jupiter.money", "cred.club", "meesho.com", "paytm.com", "fampay.in",
    # Startups for verification
    "obvious.in", "locofast.com", "smarking.com", "pocketfm.com", "zepto.co", "atherenergy.com", "yellow.ai",
    "swiggy.com", "zomato.com"
]

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

def discover_and_scrape(domain):
    data_rows = []
    homepage_url = f"https://www.{domain}"
    career_url = None
    ats_type = "Unknown"
    company_token = domain.split('.')[0] # Fallback token (e.g. "stripe")

    print(f"Scanning {domain}...")

    # --- STEP 2: BRING THE CAREER URL ---
    try:
        res = requests.get(homepage_url, headers=HEADERS, timeout=8)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # Look for links containing career keywords
        for link in soup.find_all('a', href=True):
            href = link['href']
            text = link.text.lower().strip()
            if any(kw in text or kw in href.lower() for kw in ["career", "job", "hiring", "work-with-us"]):
                career_url = urljoin(homepage_url, href)
                break
                
        # If homepage extraction fails, fallback to common path guessing
        if not career_url:
            for path in ["/careers", "/jobs"]:
                test_url = f"https://www.{domain}{path}"
                if requests.get(test_url, headers=HEADERS, timeout=4).status_code == 200:
                    career_url = test_url
                    break
    except Exception:
        pass

    if not career_url:
        return [[domain, "Failed to find career page", "N/A", "N/A", "N/A"]]

    # --- STEP 3: IDENTIFY THE ATS & TOKENS ---
    try:
        # Fetch the content of the actual career page
        career_res = requests.get(career_url, headers=HEADERS, timeout=8)
        html_content = career_res.text.lower()
        final_url = career_res.url.lower()
        
        # Check domain or body text for ATS clues
        if "greenhouse.io" in html_content or "greenhouse.io" in final_url:
            ats_type = "Greenhouse"
            # Extract token (e.g. from boards.greenhouse.io/token)
            token_match = re.search(r"greenhouse\.io/([^/?#\s]+)", final_url)
            if token_match: 
                company_token = token_match.group(1)
            else:
                # Try search in html body links
                token_match = re.search(r"boards\.greenhouse\.io/([^/?#\s\"]+)", html_content)
                if token_match: company_token = token_match.group(1)
            
        elif "lever.co" in html_content or "lever.co" in final_url:
            ats_type = "Lever"
            token_match = re.search(r"lever\.co/([^/?#\s]+)", final_url)
            if token_match: 
                company_token = token_match.group(1)
            else:
                token_match = re.search(r"jobs\.lever\.co/([^/?#\s\"]+)", html_content)
                if token_match: company_token = token_match.group(1)
            
        elif "ashbyhq.com" in html_content or "ashbyhq.com" in final_url:
            ats_type = "Ashby"
            token_match = re.search(r"ashbyhq\.com/([^/?#\s]+)", final_url)
            if token_match: 
                company_token = token_match.group(1)
            else:
                token_match = re.search(r"ashbyhq\.com/([^/?#\s\"]+)", html_content)
                if token_match: company_token = token_match.group(1)
    except Exception as e:
        print(f"Error parsing ATS for {domain}: {e}")

    # --- STEP 4: SCRAPE THE ROLES DIRECTLY FROM API ---
    try:
        if ats_type == "Greenhouse":
            # Using the stable, public Greenhouse Boards API
            api_url = f"https://boards-api.greenhouse.io/v1/boards/{company_token}/jobs"
            res = requests.get(api_url, timeout=5)
            if res.status_code == 200:
                jobs = res.json().get('jobs', [])
                for j in jobs:
                    data_rows.append([domain, ats_type, j.get('title'), j.get('location', {}).get('name'), j.get('absolute_url')])
            else:
                # Fallback to boards web page parsing if API token is slightly different
                web_url = f"https://boards.greenhouse.io/{company_token}"
                web_res = requests.get(web_url, timeout=5)
                soup = BeautifulSoup(web_res.text, 'html.parser')
                found = False
                for a in soup.find_all('a', href=True):
                    if "/jobs/" in a['href']:
                        job_url = urljoin(web_url, a['href'])
                        title = a.text.strip()
                        data_rows.append([domain, ats_type, title, "Remote / India", job_url])
                        found = True
                if not found:
                    raise Exception(f"Failed Greenhouse fetch: Status {res.status_code}")
                
        elif ats_type == "Lever":
            # Using the stable, public Lever Postings API
            api_url = f"https://api.lever.co/v0/postings/{company_token}"
            res = requests.get(api_url, timeout=5)
            if res.status_code == 200:
                jobs = res.json()
                for j in jobs:
                    data_rows.append([domain, ats_type, j.get('title'), j.get('categories', {}).get('location'), j.get('hostedUrl')])
            else:
                raise Exception(f"Failed Lever fetch: Status {res.status_code}")
                
        elif ats_type == "Ashby":
            # Using the stable, public Ashby Jobs API
            api_url = f"https://api.ashbyhq.com/v1/iframe/web/jobs?jobBoardId={company_token}"
            res = requests.get(api_url, timeout=5)
            if res.status_code == 200:
                jobs = res.json().get('jobs', [])
                for j in jobs:
                    data_rows.append([domain, ats_type, j.get('title'), j.get('location'), j.get('jobUrl')])
            else:
                # Fallback to jobs.ashbyhq.com web page parsing
                web_url = f"https://jobs.ashbyhq.com/{company_token}"
                web_res = requests.get(web_url, timeout=5)
                if web_res.status_code == 200:
                    soup = BeautifulSoup(web_res.text, 'html.parser')
                    found = False
                    for a in soup.find_all('a', href=True):
                        if f"/{company_token}/" in a['href']:
                            job_url = urljoin(web_url, a['href'])
                            title = a.find('h4')
                            title_text = title.text.strip() if title else a.text.strip()
                            data_rows.append([domain, ats_type, title_text, "Remote / US", job_url])
                            found = True
                    if not found:
                        raise Exception(f"Failed Ashby fetch: Status {res.status_code}")
                else:
                    raise Exception(f"Failed Ashby fetch: Status {res.status_code}")
                
        else:
            # Fallback row if it uses a custom HTML site or Workday
            data_rows.append([domain, "Custom HTML / Workday", "Manual verification needed", "N/A", career_url])
            
    except Exception as api_err:
        print(f"API Fetch Error for {domain} ({ats_type}, token={company_token}): {api_err}")
        data_rows.append([domain, f"{ats_type} (API Error)", "Failed to parse API", "N/A", career_url])

    return data_rows

# --- STEP 5: RUN MULTI-THREADED ENGINE & SAVE TO CSV ---
def main():
    all_job_data = []
    
    # Run 10 scrapers simultaneously to blaze through the list
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(discover_and_scrape, COMPANY_DOMAINS)
        for result_list in results:
            all_job_data.extend(result_list)
            
    # Calculate company board health metrics
    status_rows = []
    from datetime import datetime, timezone
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    
    # Group jobs by company to check health status
    company_health = {}
    for row in all_job_data:
        domain = row[0]
        ats = row[1]
        title = row[2]
        link = row[4]
        
        if domain not in company_health:
            company_health[domain] = {"ats": ats, "jobs_count": 0, "status": "Success", "details": "Active"}
            
        if ats and ("API Error" in ats or (title and "Failed to parse API" in title)):
            company_health[domain]["status"] = "Failed"
            company_health[domain]["details"] = "API Fetch Error (404/401)"
        elif ats and "Failed to find career page" in ats:
            company_health[domain]["status"] = "Failed"
            company_health[domain]["details"] = "Career page link discovery failed"
        elif title and "Manual verification needed" in title:
            company_health[domain]["status"] = "Manual Verification"
            company_health[domain]["details"] = f"Custom HTML site or Workday (check: {link})"
        else:
            company_health[domain]["jobs_count"] += 1
            
    for domain, health in company_health.items():
        details = health["details"] if health["status"] != "Success" else f"Scraped {health['jobs_count']} jobs successfully"
        status_rows.append([domain, health["ats"], health["status"], now_str, details])
            
    # Write scraped jobs to sheet
    try:
        with open('scraped_jobs.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Company Domain", "ATS System", "Job Title", "Location", "Application Link"])
            writer.writerows(all_job_data)
        print("\nProcess Finished! Open 'scraped_jobs.csv' to see all data.")
    except PermissionError:
        print("\nPermission Denied: Please close 'scraped_jobs.csv' if it is open in another program, then run the script again!")

    # Write health status report to sheet
    try:
        with open('company_status.csv', 'w', newline='', encoding='utf-8') as sf:
            writer = csv.writer(sf)
            writer.writerow(["Company Domain", "ATS System", "Status", "Last Attempted (UTC)", "Details"])
            writer.writerows(status_rows)
        print("Success! Health report updated in 'company_status.csv'")
    except PermissionError:
        print("Warning: 'company_status.csv' is locked. Skipping status write.")

if __name__ == "__main__":
    main()
