"""
verify_ats.py — Check which ATS tokens/slugs are valid before adding to scraper.py

Run with:
    python verify_ats.py

Prints a table showing which companies return valid jobs vs 404.
Safe to run — read-only HTTP GETs, no auth, no side effects.
"""

import requests
import json

TIMEOUT = 10

def check_greenhouse(name: str, token: str) -> str:
    url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
    try:
        r = requests.get(url, timeout=TIMEOUT)
        if r.status_code == 200:
            count = len(r.json().get("jobs", []))
            return f"OK  ({count} jobs)"
        return f"FAIL {r.status_code}"
    except Exception as e:
        return f"ERR  {e}"

def check_lever(name: str, slug: str) -> str:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    try:
        r = requests.get(url, timeout=TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            count = len(data) if isinstance(data, list) else 0
            return f"OK  ({count} jobs)"
        return f"FAIL {r.status_code}"
    except Exception as e:
        return f"ERR  {e}"

def check_smartrecruiters(name: str, company_id: str) -> str:
    url = f"https://api.smartrecruiters.com/v1/companies/{company_id}/postings"
    try:
        r = requests.get(url, params={"limit": 10}, timeout=TIMEOUT)
        if r.status_code == 200:
            count = r.json().get("totalFound", "?")
            return f"OK  ({count} total)"
        return f"FAIL {r.status_code}"
    except Exception as e:
        return f"ERR  {e}"

def check_ashby(name: str, token: str) -> str:
    url = f"https://api.ashbyhq.com/v1/iframe/web/jobs?jobBoardId={token}"
    try:
        r = requests.get(url, timeout=TIMEOUT)
        if r.status_code == 200:
            count = len(r.json().get("jobs", []))
            return f"OK  ({count} jobs)"
        return f"FAIL {r.status_code}"
    except Exception as e:
        return f"ERR  {e}"


# ── Companies to verify ───────────────────────────────────────────────────────
# Add any candidate company+token here before putting it into scraper.py.

GREENHOUSE_CANDIDATES = [
    # Indian companies that 404'd — trying alternate tokens
    ("Clevertap",    "clevertap1"),
    ("Innovaccer",   "innovaccer1"),
    ("ShareChat",    "moj"),           # ShareChat rebranded to Moj
    ("Unacademy",    "unacademy1"),
    ("Swiggy",       "swiggy1"),
    ("Vedantu",      "vedantu1"),
    ("Nykaa",        "fsg"),           # FSN E-Commerce (Nykaa parent)
    # Finance
    ("Zerodha",      "zerodha"),
    ("Angel One",    "angelone"),
    # Other freshers-friendly
    ("Tower Research","towerresearch"),
    ("Arcesium",     "arcesium"),
    ("D.E. Shaw",    "deshaw"),
]

LEVER_CANDIDATES = [
    ("Swiggy",       "swiggy"),
    ("Unacademy",    "unacademy"),
    ("Vedantu",      "vedantu"),
    ("ShareChat",    "sharechat"),
    ("Innovaccer",   "innovaccer"),
    ("Khatabook",    "khatabook"),
    ("OKCredit",     "okcredit"),
    ("Apna",         "apna"),
    ("Classplus",    "classplus"),
    ("upGrad",       "upgrad"),
    ("Volopay",      "volopay"),
    ("Recko",        "recko"),
    ("Lenskart",     "lenskart"),
    ("Clevertap",    "clevertap"),
    ("Exotel",       "exotel"),
    ("Darwinbox",    "darwinbox"),
    ("Dunzo",        "dunzo"),
]

SMARTRECRUITERS_CANDIDATES = [
    ("Swiggy",       "Swiggy"),
    ("Turing",       "Turing"),
    ("Games24x7",    "Games24x7"),
    ("Juspay",       "Juspay"),
    ("Nykaa",        "Nykaa"),
    ("Clevertap",    "Clevertap"),
    ("Darwinbox",    "Darwinbox"),
    ("ShareChat",    "Sharechat"),
]

ASHBY_CANDIDATES = [
    ("Pika",         "pika"),
    ("Perplexity",   "perplexityai"),
    ("Anduril",      "anduril"),
    ("Deel",         "deel"),
    ("Cal.com",      "calcom"),
    ("Loom",         "loom"),
]


# ── Runner ────────────────────────────────────────────────────────────────────

def run():
    width = 40
    print(f"\n{'ATS':<16} {'Company':<16} {'Token/Slug':<24} Result")
    print("-" * 80)

    for name, token in GREENHOUSE_CANDIDATES:
        result = check_greenhouse(name, token)
        print(f"{'Greenhouse':<16} {name:<16} {token:<24} {result}")

    print()
    for name, slug in LEVER_CANDIDATES:
        result = check_lever(name, slug)
        print(f"{'Lever':<16} {name:<16} {slug:<24} {result}")

    print()
    for name, cid in SMARTRECRUITERS_CANDIDATES:
        result = check_smartrecruiters(name, cid)
        print(f"{'SmartRecruiters':<16} {name:<16} {cid:<24} {result}")

    print()
    for name, token in ASHBY_CANDIDATES:
        result = check_ashby(name, token)
        print(f"{'Ashby':<16} {name:<16} {token:<24} {result}")

    print("\nDone. Copy any 'OK' rows into scraper.py.")

if __name__ == "__main__":
    run()
