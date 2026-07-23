import sys
sys.path.insert(0, '.')
from scraper import scrape_workday, scrape_smartrecruiters

candidates = [
    ("Salesforce",    "salesforce", "External_Career_Site",      12),
    ("Samsung",       "sec",        "samsungcareers",             3),
    ("Nvidia",        "nvidia",     "NVIDIAExternalCareerSite",    5),
    ("Cohesity",      "cohesity",   "Cohesity_Careers",            5),
    ("JPMorgan Chase","jpmc",       "JPMorganChase",               1),
    ("Goldman Sachs", "goldmansachs","gs_external_career_website",  1),
    ("Barclays",      "barclays",   "BarcExternal",                1),
    ("Morgan Stanley","morganstanley","ExternalJobOpenings",         1),
    ("Visa",          "visa",       "VisaJobsGlobal",              1),
    ("American Express","aexp",     "AmexExternalReq",             1),
    ("Deutsche Bank", "db",         "DBWS_ExternalJobPostings",    5),
    ("Citi",          "citi",       "Citi",                        1),
    ("Wells Fargo",   "wellsfargo", "WellsFargoJobSearch",         1),
    ("BNY",           "bnymellon",  "BNYMellonCareers",            2),
    ("State Street",  "statestreet","StateStreetCareers",          2),
    ("Microsoft",     "microsoft",  "MicrosoftCareers",            1),
    ("Google",        "google",     "googlecareerssearch",         1),
]

print("Testing Workday candidates:")
for name, tenant, board, wd in candidates:
    try:
        jobs = scrape_workday(name, tenant, board, wd)
        print(f"  {name:<16}: Found {len(jobs)} jobs (Success)")
    except Exception as e:
        print(f"  {name:<16}: Failed: {e}")

print("\nTesting SmartRecruiters candidates:")
for name, company_id in [
    ("Mastercard", "Mastercard"),
    ("Visa",       "Visa"),
]:
    try:
        jobs = scrape_smartrecruiters(name, company_id)
        print(f"  {name:<16}: Found {len(jobs)} jobs (Success)")
    except Exception as e:
        print(f"  {name:<16}: Failed: {e}")
