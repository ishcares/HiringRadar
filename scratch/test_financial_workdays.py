import requests

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Content-Type": "application/json",
    "Accept": "application/json",
}
payload = {
    "appliedFacets": {},
    "limit": 20,
    "offset": 0,
    "searchText": "",
}

# Test BNY (bny, BNY_Careers)
url_bny = "https://bny.wd1.myworkdayjobs.com/wday/cxs/bny/BNY_Careers/jobs"
print("Testing BNY:")
try:
    r = requests.post(url_bny, json=payload, headers=headers, timeout=10)
    print("  Status:", r.status_code)
    if r.status_code == 200:
        print("  Success! Found jobs:", len(r.json().get("jobPostings", [])))
    else:
        print("  Failed:", r.text[:200])
except Exception as e:
    print("  Error:", e)
