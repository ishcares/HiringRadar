import requests
import json

url = "https://goldmansachs.fa.ocs.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions?finder=findReqs;siteNumber=CX_1001&expand=requisitionList&limit=5"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

print("Testing Goldman Sachs Oracle REST API:")
try:
    r = requests.get(url, headers=headers, timeout=15)
    print("  Status:", r.status_code)
    if r.status_code == 200:
        data = r.json()
        items = data.get("items", [])
        if items:
            req_list = items[0].get("requisitionList", [])
            print(f"  Success! Found {len(req_list)} job requisitions in requisitionList.")
            if req_list:
                print("  Sample Job Details:")
                print(f"    Title: {req_list[0].get('Title')}")
                print(f"    Id: {req_list[0].get('Id')}")
                print(f"    PrimaryLocation: {req_list[0].get('PrimaryLocation')}")
    else:
        print("  Failed:", r.text[:200])
except Exception as e:
    print("  Error:", e)
