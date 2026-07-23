import requests

url = "https://barclays.wd3.myworkdayjobs.com/wday/cxs/barclays/External_Career_Site_Barclays/jobs"
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

r = requests.post(url, json=payload, headers=headers)
print("Status:", r.status_code)
if r.status_code == 200:
    print("Barclays succeeded! Found jobs:", len(r.json().get("jobPostings", [])))
else:
    print("Barclays failed with text:", r.text[:200])
