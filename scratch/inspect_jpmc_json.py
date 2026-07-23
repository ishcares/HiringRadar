import requests
import json

jpmc_url = "https://jpmc.fa.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions?finder=findReqs;siteNumber=CX_1001&limit=5"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

r = requests.get(jpmc_url, headers=headers)
print("JPMC Status:", r.status_code)
if r.status_code == 200:
    data = r.json()
    items = data.get("items", [])
    print("Number of items:", len(items))
    if items:
        # Print first item keys and values
        print(json.dumps(items[0], indent=2)[:2000])

# Test gs.fa
gs_url = "https://gs.fa.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions?finder=findReqs;siteNumber=CX_1001&limit=5"
try:
    r_gs = requests.get(gs_url, headers=headers, timeout=5)
    print("\nGS status:", r_gs.status_code)
except Exception as e:
    print("\nGS failed:", e)
