import sys
import webbrowser
import urllib.parse

def open_leads_search(company: str):
    """Generates the direct search URL and opens it in the default web browser."""
    query = f"site:linkedin.com/in/ \"{company}\" (\"engineering manager\" OR \"engineering lead\" OR \"tech lead\") India"
    url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}"
    
    print(f"\nConstructing direct search query for {company}...")
    print(f"URL: {url}\n")
    print("Opening Google Search in your browser...")
    webbrowser.open(url)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python find_leads.py [Company Name]")
        sys.exit(1)
        
    company_name = sys.argv[1]
    open_leads_search(company_name)

