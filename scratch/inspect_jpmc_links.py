import requests
import json

# Test 1: expand=requisitionList on main URL
url_expand = "https://jpmc.fa.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions?finder=findReqs;siteNumber=CX_1001&expand=requisitionList&limit=5"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

print("Testing expand=requisitionList on main URL:")
try:
    r_exp = requests.get(url_expand, headers=headers, timeout=15)
    print("  Status:", r_exp.status_code)
    if r_exp.status_code == 200:
        data = r_exp.json()
        items = data.get("items", [])
        if items:
            req_list = items[0].get("requisitionList", [])
            print(f"  Success! Found {len(req_list)} job requisitions in requisitionList.")
            if req_list:
                print("  Sample Job Keys:", list(req_list[0].keys()))
                print("  Sample Job Details:")
                print(f"    Title: {req_list[0].get('Title')}")
                print(f"    Id: {req_list[0].get('Id')}")
                print(f"    RequisitionNumber: {req_list[0].get('RequisitionNumber')}")
                print(f"    PrimaryLocation: {req_list[0].get('PrimaryLocation')}")
                print(f"    ShortDescription: {req_list[0].get('ShortDescription')[:200] if req_list[0].get('ShortDescription') else 'None'}")
    else:
        print("  Failed:", r_exp.text[:200])
except Exception as e:
    print("  Error:", e)
