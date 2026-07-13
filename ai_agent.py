import os
import json
import time
from google import genai
from google.genai import errors
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv()

# Configure Gemini Client
gemini_key = os.getenv("GEMINI_API_KEY")
client = None
if gemini_key:
    client = genai.Client(api_key=gemini_key)


def execute_gemini_with_retry(prompt: str, model_name: str = 'gemini-3.5-flash', max_retries: int = 3) -> str:
    """Executes a Gemini generation call with exponential back-off retries to handle 429/503 errors."""
    if not client:
        return ""
        
    delay = 2  # Start with a 2-second delay
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            return response.text.strip()
        except Exception as e:
            # Check for API rate limiting or unavailable errors
            err_str = str(e)
            if "429" in err_str or "503" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                print(f"Gemini API rate limited/unavailable (attempt {attempt+1}/{max_retries}). Retrying in {delay}s...")
                time.sleep(delay)
                delay *= 2  # Exponentially double the wait time
            else:
                # If it's a different error, raise it
                raise e
    # If all retries fail, execute one final attempt (which will raise the exception if it fails)
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
    )
    return response.text.strip()


def generate_gap_critique_and_pitch(resume_text: str, job_title: str, company: str, job_description: str) -> dict:
    """Uses Gemini to identify missing skills and generate a high-conversion outreach message."""
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
        text = execute_gemini_with_retry(prompt)
        
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
        print(f"Error generating AI critique: {e}")
        return {
            "missing_skills": ["Failed to calculate gaps"],
            "reskilling_advice": "AI processing error. Please try again later.",
            "recruiter_pitch": f"Hey! I noticed you are hiring for {job_title} at {company}. I have attached my resume for your review."
        }


def parse_skills_from_resume(resume_text: str) -> list[str]:
    """Uses Gemini to extract a clean list of technical skills from a raw resume text."""
    prompt = f"""
You are a technical resume parser. Read the raw resume text below and extract a list of all technical programming languages, frameworks, databases, and development tools mentioned.

--- RESUME TEXT ---
{resume_text}

--- INSTRUCTIONS ---
Output a raw JSON array of strings containing the lowercase names of the skills (e.g. ["python", "reactjs", "postgresql", "docker"]).
Output ONLY the raw JSON array (no markdown code blocks, no backticks, no other text).
"""

    try:
        text = execute_gemini_with_retry(prompt)
        
        # Clean markdown wrappers if present
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```json") or lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
            
        result = json.loads(text)
        if isinstance(result, list):
            return [str(s).lower().strip() for s in result]
        return []
    except Exception as e:
        print(f"Error parsing resume skills: {e}")
        return []


def generate_roadmap_from_live_jobs(student_skills: list[str], target_category: str, live_jobs: list) -> dict:
    """Generates a complete multi-phase career execution blueprint based on real-world active job openings in the database."""
    skills_str = ", ".join(student_skills)
    
    job_details_list = []
    for job in live_jobs[:15]:
        job_details_list.append(f"Company: {job.get('company')}\nRole: {job.get('title')}\nDetails: {job.get('description', '')[:300]}")
    jobs_context = "\n\n━━━━━━━━━━━━━━━━━━━━━\n\n".join(job_details_list)

    prompt = f"""
You are an elite career accelerator architect and senior systems engineer.
Compare the student's current skills against the aggregated active job requirements in the market.

--- CURRENT STUDENT SKILLS ---
{skills_str}

--- ACTIVE LIVE JOB POSTINGS IN MARKET ---
{jobs_context}

--- INSTRUCTIONS ---
Analyze the overlap and construct a highly detailed, multi-phase reskilling roadmap. 
Output a raw JSON object (strictly no markdown code blocks, no backticks, just raw json) with these exact keys:

1. "missing_skills": A list of the top 3-4 critical technologies/tools required by these live jobs that are missing in the student's profile, including their prerequisites (e.g. "Redis caching (Prerequisite: SQL database basics)").
2. "dsa_roadmap": A list of 3 items representing a 3-week study syllabus. If the category is "tech", output DSA topics with prerequisites (e.g. "Week 1: Recursion & Backtracking (Prerequisite for Dynamic Programming)"). If the category is DevOps, AI, PM, or Design, output role-specific interview concepts with prerequisites (e.g., "Week 1: Product Metrics & A/B Testing").
3. "project_name": A catchy, high-impact name for a capstone portfolio project to bridge these gaps.
4. "project_milestones": A list of 3 strings representing a 3-week execution milestone for the project (e.g., "Week 1: Set up relational database schemas and build core REST endpoints").
5. "resume_hook": A 2-sentence impact-driven resume bullet point describing this project that the student can add to their resume once built (using metrics/technical terminology).

JSON output format:
{{
  "missing_skills": ["skill1", "skill2"],
  "dsa_roadmap": ["week1 plan", "week2 plan", "week3 plan"],
  "project_name": "Project Name Here",
  "project_milestones": ["week1 task", "week2 task", "week3 task"],
  "resume_hook": "Resume bullet point description..."
}}
"""

    try:
        text = execute_gemini_with_retry(prompt)
        
        # Clean markdown wrappers if present
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
        print(f"Error generating live roadmap: {e}")
        return {
            "missing_skills": ["System design", "Cloud deployment"],
            "dsa_roadmap": ["Week 1: Arrays & Hashing (Prerequisite: Basic Loops)", "Week 2: Two Pointers", "Week 3: Sliding Window"],
            "project_name": "Web Platform MVP",
            "project_milestones": ["Week 1: Set up database schemas", "Week 2: Implement caching", "Week 3: Deploy using Docker"],
            "resume_hook": "Developed a full-stack platform optimizing database query times and enabling containerized deployment."
        }

def evaluate_resume_for_job(resume_text: str, job_title: str, company: str, job_description: str) -> str:
    """Evaluates candidate resume against job description using strict recruiter grading rules."""
    prompt = f"""
You are a strict Corporate Technical Recruiter and an automated ATS Parser filtering entry-level engineering applications for top-tier technology firms. Evaluate the provided Candidate Resume against the target Job Description.

Calculate a highly realistic market match score based on a maximum of 100 points, strictly penalizing missing infrastructure tools, superficial skill listings, or project scope mismatches.

Apply these hard rules:
1. If the Job Description explicitly lists a critical stack element (e.g., Docker, Redis, Kubernetes, AWS) and the resume only lists standard MERN framework elements with zero infrastructure projects, automatically deduct 20 points.
2. If the candidate lists skills in a "Technical Skills" section but fails to implement them inside their listed projects, reduce the Hard Skill Alignment score by 50%.
3. Grade the projects on structural depth: Simple CRUD or tutorial-based apps get a maximum score of 10/20 for project depth. Systems with architectural complexity (JWT rotation, containerization, microservices) get full points.

--- CANDIDATE RESUME ---
{resume_text}

--- TARGET JOB DESCRIPTION ---
Company: {company}
Role: {job_title}
Details:
{job_description}

Return the evaluation strictly in this format:
- Match Score: [X]%
- Critical Stack Gaps: [List maximum 3 missing technical keywords/concepts]
- Project Scope Assessment: [1 sentence on whether their projects match live market demands]
"""
    try:
        text = execute_gemini_with_retry(prompt, model_name='gemini-3.5-flash')
        return text
    except Exception as e:
        print(f"Error in strict resume evaluation: {e}")
        return f"Error evaluating resume: {e}"
