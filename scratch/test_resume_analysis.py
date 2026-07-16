import sys
import os
import asyncio
from dotenv import load_dotenv

sys.path.insert(0, os.getcwd())
load_dotenv()

from resume_ingest import extract_resume_text_from_path as extract_text_from_pdf
from ai_agent import evaluate_resume_for_job

def run_test():
    print("==================================================")
    print("  Testing Resume Analysis & Grader flow")
    print("==================================================")

    # 1. Look for a sample resume in the directory
    resume_path = None
    possible_names = ["resume.pdf", "sample_resume.pdf"]
    for name in possible_names:
        if os.path.exists(name):
            resume_path = name
            break
            
    if not resume_path:
        print("[FAIL] No sample resume.pdf found in the workspace directory to test with.")
        print("Please copy a test resume PDF into the folder as 'resume.pdf' and rerun.")
        return

    print(f"[INFO] Found test resume: {resume_path}")
    
    # 2. Extract text from PDF
    print("[INFO] Extracting text from PDF...")
    try:
        resume_text = extract_text_from_pdf(resume_path)
        if not resume_text:
            print("[FAIL] Extracted text is empty!")
            return
        print(f"[OK] Text extracted successfully ({len(resume_text)} characters).")
    except Exception as e:
        print(f"[FAIL] Failed to parse PDF: {e}")
        return

    # 3. Simulate a target job
    job_title = "Software Engineer - Backend"
    company = "Glean"
    job_description = (
        "We are looking for a Software Engineer to build our enterprise search backend. "
        "Key requirements: Strong knowledge of Go or Python, PostgreSQL, Redis, and Docker. "
        "Experience building microservices, deploying on AWS, and designing scalable APIs."
    )

    print("\n[INFO] Target Job:")
    print(f"   Role: {job_title} @ {company}")
    print(f"   Description: {job_description}\n")

    # 4. Run the Gemini resume evaluator
    print("[INFO] Calling Gemini evaluator...")
    try:
        report = evaluate_resume_for_job(resume_text, job_title, company, job_description)
        print("==================================================")
        print("  GEMINI EVALUATION REPORT:")
        print("==================================================")
        print(report)
        print("==================================================")
        print("[OK] Resume Analysis Test Completed successfully!")
    except Exception as e:
        print(f"[FAIL] Evaluation failed: {e}")

if __name__ == "__main__":
    run_test()
