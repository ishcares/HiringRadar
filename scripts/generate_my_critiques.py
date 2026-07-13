import sys
import os

sys.path.append(r"C:\Users\ishit\OneDrive\Desktop\HiringRadar")

from dotenv import load_dotenv
load_dotenv(dotenv_path=r"C:\Users\ishit\OneDrive\Desktop\HiringRadar\.env")

from resume_parser import extract_text_from_pdf
from ai_agent import generate_gap_critique_and_pitch

pdf_path = r"C:\Users\ishit\.gemini\antigravity-ide\brain\8675f697-87f1-4cfb-9555-18f90e2b3c84\media__1783807564196.pdf"

# 1. Mock Glean Backend Intern/SDE-1 JD
glean_job_title = "Software Engineer, Backend"
glean_company = "Glean"
glean_jd = """
Requirements:
- Strong programming skills in Python, Go, or Java.
- Understanding of distributed systems, search/indexing algorithms, and REST APIs.
- Experience with relational databases (MySQL/PostgreSQL) and caching layers (Redis).
- Familiarity with cloud environments (GCP/AWS) and container orchestration (Docker/Kubernetes).
"""

# 2. Mock Stripe Software Engineer Intern JD
stripe_job_title = "Software Engineer, Intern"
stripe_company = "Stripe"
stripe_jd = """
Requirements:
- Strong experience in JavaScript/TypeScript, React, or Ruby on Rails.
- Solid understanding of web fundamentals (HTML, CSS, JSON, REST APIs).
- Understanding of databases and transactional safety.
- Passion for developer tools and building clean APIs.
"""

def generate_report(resume_text, job_title, company, jd, output_filename):
    print(f"Generating critique for {company}...")
    report = generate_gap_critique_and_pitch(
        resume_text=resume_text,
        job_title=job_title,
        company=company,
        job_description=jd
    )
    
    output_path = f"C:\\Users\\ishit\\OneDrive\\Desktop\\HiringRadar\\{output_filename}"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# Aligner Report: {company} ({job_title})\n\n")
        f.write("## ⚠️ Missing Skills\n")
        for skill in report.get("missing_skills", []):
            f.write(f"- {skill}\n")
            
        f.write("\n## 📚 Actionable Reskilling Advice\n")
        f.write(report.get("reskilling_advice", "No advice provided."))
        
        f.write("\n\n## 📣 Recruiter Outreach Pitch\n")
        f.write("```text\n")
        f.write(report.get("recruiter_pitch", ""))
        f.write("\n```\n")
    print(f"Saved: {output_path}")

if __name__ == "__main__":
    if os.path.exists(pdf_path):
        print("Extracting text from your resume PDF...")
        resume_text = extract_text_from_pdf(pdf_path)
        
        generate_report(resume_text, glean_job_title, glean_company, glean_jd, "my_glean_report.md")
        
        import time
        print("\nWaiting 3 seconds to prevent API rate limits...")
        time.sleep(3)
        
        generate_report(resume_text, stripe_job_title, stripe_company, stripe_jd, "my_stripe_report.md")
        print("\nAll reports generated successfully!")
    else:
        print(f"Error: Resume PDF not found at {pdf_path}")
