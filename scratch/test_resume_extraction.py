import sys
import os
import asyncio
from dotenv import load_dotenv

sys.path.insert(0, os.getcwd())
load_dotenv()

from resume_ingest import extract_resume_text_from_path as extract_text_from_pdf
from ai_agent import parse_skills_from_resume

def run_test():
    print("==================================================")
    print("  Testing Resume Structured Extraction Prompt")
    print("==================================================")

    resume_path = "resume.pdf"
    if not os.path.exists(resume_path):
        print(f"[FAIL] resume.pdf not found in root directory to test.")
        return

    print(f"[INFO] Parsing resume: {resume_path}")
    try:
        resume_text = extract_text_from_pdf(resume_path)
        if not resume_text:
            print("[FAIL] Empty resume text.")
            return
        
        print("[INFO] Calling parse_skills_from_resume...")
        extracted_data = parse_skills_from_resume(resume_text)
        
        print("==================================================")
        print("  EXTRACTED STRUCTURED RESUME DATA:")
        print("==================================================")
        import json
        print(json.dumps(extracted_data, indent=2))
        print("==================================================")
        print("[OK] Resume structured extraction test passed!")
        
    except Exception as e:
        print(f"[FAIL] Test execution failed: {e}")

if __name__ == "__main__":
    run_test()
