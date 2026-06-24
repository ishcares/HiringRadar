import requests
from bs4 import BeautifulSoup
import json
import os




def is_relevant(title):
   return True

def scrape_greenhouse_html(company_name, slug):
    url = f"https://job-boards.greenhouse.io/{slug}"
    response = requests.get(url)

    if response.status_code !=200:
      print(f"Failed to fetch{company_name}: {response.status_code}")
      return []
    soup = BeautifulSoup(response.text,"html.parser")
    job_rows = soup.find_all("tr",class_="job-post")
   
   
    relevant = []

    for row in job_rows:
      title_tag = row.find("p", class_="body--medium")
      location_tag = row.find("p", class_="body--metadata")
      link_tag = row.find("a", href=True)

      if not title_tag:
         continue
      title = title_tag.get_text(strip=True)
      location = location_tag.get_text(strip=True) if location_tag else "Not specified"
      url = link_tag["href"] if link_tag else ""

      if is_relevant(title):
         relevant.append({
               "company": company_name,
               "title" : title,
               "location": location,
               "url": url
        })
    return relevant

def scrape_lever(company_name,company_slug):
    url = f"https://api.lever.co/v0/postings/{company_slug}?mode=json"
    response = requests.get(url)

    if response.status_code != 200:
        print(f"Failed to fetch{company_name}: {response.status_code}")
        return []
    jobs = response.json()
    relevant = []

    for job in jobs:
        title = job["text"]
        if is_relevant(title):
            relevant.append({
                "company": company_name,
                 "title": title,
                 "location": job["categories"].get("location","Not specified"),
                 "url": job["hostedUrl"]

            })

    return relevant
def get_all_jobs():
    all_jobs = []

  #greenhouse companies
    all_jobs += scrape_greenhouse_html("Razorpay","razorpaysoftwareprivatelimited")
    all_jobs += scrape_greenhouse_html("PhonePe","phonepe")
    all_jobs += scrape_greenhouse_html("Groww","groww")
           
 #lever companies
    all_jobs += scrape_lever("CRED","cred")

    return all_jobs
        
if __name__ == "__main__":
    jobs = get_all_jobs()
    if not jobs:
      print("No relevant jobs found.")
    else :
      for job in jobs:
           print(f"\n{job['company']}- {job['title']}")
           print(f"Location:{job['location']}")
           print(f"Link:{job['url']}")

SEEN_JOBS_FILE = "seen_jobs.json"

def load_seen_json():
   if os.path.exists(SEEN_JOBS_FILE) :
      with open(SEEN_JOBS_FILE,"r") as f:
         return set(json.load(f))
   return set()

def save_seen_jobs(seen):
    with open(SEEN_JOBS_FILE,"w") as f:
       json.dump(list(seen),f)


def get_new_jobs():        
   seen = load_seen_json()
   all_jobs = get_all_jobs()

   new_jobs = [job for job in all_jobs if job["url"]not in seen]

   seen.update(job["url"] for job in new_jobs)
   save_seen_jobs(seen)

   return new_jobs