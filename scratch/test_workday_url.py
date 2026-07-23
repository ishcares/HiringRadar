import requests
import json

url = "https://visa.wd1.myworkdayjobs.com/wday/cxs/visa/VisaJobsGlobal/jobs"
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
print("Response text:", r.text[:1000])
