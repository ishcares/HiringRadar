# Walkthrough — Scraper Company Update

I have updated the scraper configuration and relevance logic in `scraper.py` to add support for the requested financial and big tech companies.

## Changes Made

### 1. Updated relevance logic for FinTech roles
Added `is_finance_tech_relevant()` to catch entry-level financial tech titles (like *Technology Analyst* and *Software Analyst*) that were previously filtered out. Wired this check directly into `check_job_relevance_and_category()`.

### 2. Company lists in scraper.py
- **SmartRecruiters**: Added Mastercard (`Mastercard`) and Visa (`Visa`) which are now verified and active.
- **Workday**: Added Salesforce (`salesforce`), Nvidia (`nvidia`), Cohesity (`cohesity`) as active verified feeds.
- **Verification Logs**: Added comments and commented out other financial/big tech companies (like JPMorgan, Goldman, Barclays, Morgan Stanley, AmEx, Deutsche Bank, Citi, Wells Fargo, BNY, State Street, Microsoft, Samsung) that returned 422 Unprocessable Entity or 404 on myworkdayjobs endpoints.

---

## Validation Results

We ran integration tests using a local test script. Here are the results:

### Scraper Verification Runs
- **Salesforce** (Workday): `Found 2 jobs` (Success)
- **Cohesity** (Workday): `Found 2 jobs` (Success)
- **Nvidia** (Workday): `Found 0 jobs` (Success)
- **Mastercard** (SmartRecruiters): `Found 0 jobs` (Success)
- **Visa** (SmartRecruiters): `Found 0 jobs` (Success)

### Relevance Rules Test
- `is_finance_tech_relevant('Technology Analyst')` → `True` (Correctly parsed)
- `is_finance_tech_relevant('Senior Technology Analyst')` → `False` (Correctly blocked)
- `check_job_relevance_and_category('Technology Analyst')` → `'tech'` (Correctly classified)
- `check_job_relevance_and_category('Software Engineer')` → `'tech'` (Correctly classified)
