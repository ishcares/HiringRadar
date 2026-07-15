import os
import json
from google import genai
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv()

# Configure Gemini Client
gemini_key = os.getenv("GEMINI_API_KEY")
client = None
if gemini_key:
    client = genai.Client(api_key=gemini_key)


def extract_structured_requirements(job_title: str, company: str, job_description: str) -> dict:
    """Parses a raw job description and extracts structured requirement weights.
    
    Done ONCE per job at scraper ingestion time.
    """
    if not client:
        # Fallback empty structure
        return {
            "role_level": "fresher",
            "requirements": [],
            "extraction_confidence": "low"
        }

    prompt = f"""
You are a senior technical hiring manager. Analyze the following Job Description (JD) to extract the key technologies and skills.
Group the requirements based on how a hiring manager signals priority (Must-Have vs. Nice-to-Have).

--- JOB DETAILS ---
Company: {company}
Title: {job_title}
Job Description:
{job_description}

--- EXTRACTION RULES ---
1. Identify the core skills, frameworks, or tools listed.
2. Assign a 'tier' to each requirement:
   - "must_have": Explicitly stated as required, mandatory, or essential.
   - "preferred": Mentioned under 'nice to have', 'bonus points', 'plus', or 'preferred'.
   - "mentioned": Mentioned in the description text but not explicitly in the core bullet points.
3. Provide the 'evidence' (the exact text snippet or reason why it falls into that tier).
4. Extract the 'role_level' ("intern", "fresher", "mid", "senior") based on seniority clues.

Output a raw JSON object (strictly no markdown backticks, just raw json) with this structure:
{{
  "role_level": "fresher",
  "requirements": [
    {{
      "skill": "React",
      "tier": "must_have",
      "evidence": "listed in mandatory requirements"
    }},
    {{
      "skill": "Docker",
      "tier": "preferred",
      "evidence": "listed under preferred qualifications"
    }}
  ],
  "extraction_confidence": "high"
}}
"""

    try:
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=prompt,
        )
        text = response.text.strip()
        
        # Clean markdown code block markers
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
        print(f"Error extracting JD requirements: {e}")
        return {
            "role_level": "fresher",
            "requirements": [],
            "extraction_confidence": "low"
        }
