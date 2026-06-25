import requests
from bs4 import BeautifulSoup
import psycopg2
import os


def get_db_connection():
    url = os.getenv("DATABASE_URL")
    return psycopg2.connect(url)

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
    all_jobs += scrape_greenhouse_html("Postman", "postman")      
 #lever companies
    all_jobs += scrape_lever("CRED","cred")
    all_jobs += scrape_lever("Meesho","meesho")
    return all_jobs

def load_seen_jobs():
   conn = get_db_connection()
   cur = conn.cursor()
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

   new_jobs = [job for job in all_jobs if job["url"]not in seen]

   save_seen_jobs(job["url"]for job in new_jobs)

   return new_jobs

        
if __name__ == "__main__":
    jobs = get_all_jobs()
    if not jobs:
      print("No relevant jobs found.")
    else :
      for job in jobs:
           print(f"\n{job['company']}- {job['title']}")
           print(f"Location:{job['location']}")
           print(f"Link:{job['url']}")

