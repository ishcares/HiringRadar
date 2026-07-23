import requests

url = "https://goldmansachs.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

print("Testing Goldman Sachs HTML Career Portal:")
try:
    r = requests.get(url, headers=headers, timeout=15)
    print("  Status:", r.status_code)
    print("  Response headers:", dict(r.headers))
    print("  Body length:", len(r.text))
except Exception as e:
    print("  Error:", e)
