import requests

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
})

# Step 1: GET to initialize cookies
print("1. Initializing session cookies via GET...")
r_get = session.get("https://bny.wd1.myworkdayjobs.com/BNY_Careers", timeout=10)
print("  GET status:", r_get.status_code)
print("  Cookies acquired:", dict(session.cookies))

# Step 2: POST to retrieve jobs
payload = {
    "appliedFacets": {},
    "limit": 20,
    "offset": 0,
    "searchText": "",
}
url_post = "https://bny.wd1.myworkdayjobs.com/wday/cxs/bny/BNY_Careers/jobs"
print("\n2. Executing POST to retrieve jobs...")
r_post = session.post(url_post, json=payload, timeout=10)
print("  POST status:", r_post.status_code)
if r_post.status_code == 200:
    print("  Success! Found jobs:", len(r_post.json().get("jobPostings", [])))
else:
    print("  Failed:", r_post.text[:200])
