import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv()

# Configure Gemini
gemini_key = os.getenv("GEMINI_API_KEY")
if gemini_key:
    genai.configure(api_key=gemini_key)


def generate_gap_critique_and_pitch(resume_text: str, job_title: str, company: str, job_description: str) -> dict:
    """Uses Gemini to identify missing skills and generate a high-conversion outreach message.
    
    Returns a dictionary with 'missing_skills', 'reskilling_advice', and 'recruiter_pitch'.
    """
    if not gemini_key:
        return {
            "missing_skills": ["API configuration missing"],
            "reskilling_advice": "Configure GEMINI_API_KEY in your system environment to activate AI analysis.",
            "recruiter_pitch": "Hey! I saw the job opening and would love to apply. Please check my resume."
        }

    prompt = f"""
You are an expert technical recruiter and resume builder assisting freshers/students in landing engineering roles.
Compare the student's resume details against the Target Job Description below.

--- STUDENT RESUME / SKILLS INFO ---
{resume_text}

--- TARGET JOB DETAILS ---
Company: {company}
Role: {job_title}
Job Description/Requirements:
{job_description}

--- INSTRUCTIONS ---
Analyze the overlap and output a raw JSON object (strictly no markdown formatting, no backticks, just raw json) with these exact keys:
1. "missing_skills": A list of the top 3-4 critical technologies, tools, or frameworks mentioned in the job description that are completely missing or weak in the student's resume.
2. "reskilling_advice": A short 2-sentence actionable advice on what project or topic to learn next to bridge this gap.
3. "recruiter_pitch": A high-impact, 3-paragraph cold outreach message (email/LinkedIn) the student can send directly to a recruiter or engineering lead at {company}. The pitch must:
   - Highlight the student's strong matching skills that align with the role.
   - Address the gap proactively (e.g. "While I am currently expanding my knowledge in [missing skill], my background in [matched skill] allows me to...")
   - End with a clear call-to-action (e.g. asking for a 10-minute chat or sharing their portfolio).

JSON output format:
{{
  "missing_skills": ["skill1", "skill2"],
  "reskilling_advice": "Advice text here.",
  "recruiter_pitch": "Dear [Name] or Hiring Team,\\n\\n..."
}}
"""

    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        # Clean markdown code block markers if the model included them
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```json") or lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
            
        result = json.loads(text)
        return result
    except Exception as e:
        print(f"Error generating AI critique: {e}")
        return {
            "missing_skills": ["Failed to calculate gaps"],
            "reskilling_advice": "AI processing error. Please try again later.",
            "recruiter_pitch": f"Hey! I noticed you are hiring for {job_title} at {company}. I have attached my resume for your review."
        }
