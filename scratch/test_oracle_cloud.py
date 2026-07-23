import requests

# Test JPMC Oracle CE API
jpmc_url = "https://jpmc.fa.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions?finder=findReqs;siteNumber=CX_1001&limit=5"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

print("Testing JPMC Oracle REST API:")
try:
    r_jpmc = requests.get(jpmc_url, headers=headers, timeout=15)
    print("  Status:", r_jpmc.status_code)
    if r_jpmc.status_code == 200:
        data = r_jpmc.json()
        items = data.get("items", [])
        print(f"  Success! Found {len(items)} requisitions.")
        for item in items[:2]:
            print(f"    - Title: {item.get('Title')}, ReqNumber: {item.get('RequisitionNumber')}, PrimaryLocation: {item.get('PrimaryLocation')}")
    else:
        print("  Failed:", r_jpmc.text[:200])
except Exception as e:
    print("  Error:", e)

# Test Goldman Sachs Oracle CE API
gs_url = "https://goldmansachs.fa.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions?finder=findReqs;siteNumber=CX_1001&limit=5"
print("\nTesting Goldman Sachs Oracle REST API:")
try:
    r_gs = requests.get(gs_url, headers=headers, timeout=15)
    print("  Status:", r_gs.status_code)
    if r_gs.status_code == 200:
        data = r_gs.json()
        items = data.get("items", [])
        print(f"  Success! Found {len(items)} requisitions.")
        for item in items[:2]:
            print(f"    - Title: {item.get('Title')}, ReqNumber: {item.get('RequisitionNumber')}, PrimaryLocation: {item.get('PrimaryLocation')}")
    else:
        print("  Failed:", r_gs.text[:200])
except Exception as e:
    print("  Error:", e)
