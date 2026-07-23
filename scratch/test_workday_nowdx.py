import requests

# Test 1: Visa without wdX
url1 = "https://visa.myworkdayjobs.com/wday/cxs/visa/VisaJobsGlobal/jobs"
headers = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}
payload = {
    "appliedFacets": {},
    "limit": 20,
    "offset": 0,
    "searchText": "",
}

r1 = requests.post(url1, json=payload, headers=headers)
print("Visa status (no wdX):", r1.status_code)
if r1.status_code == 200:
    print("Visa succeeded! Found jobs:", len(r1.json().get("jobPostings", [])))
else:
    print("Visa failed with text:", r1.text[:200])

# Test 2: Barclays without wdX
url2 = "https://barclays.myworkdayjobs.com/wday/cxs/barclays/BarcExternal/jobs"
r2 = requests.post(url2, json=payload, headers=headers)
print("\nBarclays status (no wdX):", r2.status_code)
if r2.status_code == 200:
    print("Barclays succeeded! Found jobs:", len(r2.json().get("jobPostings", [])))
else:
    print("Barclays failed with text:", r2.text[:200])
