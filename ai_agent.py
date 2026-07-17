import os
import json
import time
from dotenv import load_dotenv
import re

# Ensure environment variables are loaded
load_dotenv()

# Configure Gemini Client
_gemini_client = None

def _get_client():
    global _gemini_client
    if _gemini_client is None:
        try:
            from google import genai
            key = os.getenv("GEMINI_API_KEY")
            if key:
                _gemini_client = genai.Client(api_key=key)
        except Exception as e:
            print(f"Gemini client init failed: {e}")
    return _gemini_client

FAST_MODEL = "gemini-2.5-flash-lite"
SMART_MODEL = "gemini-2.5-flash"

def execute_gemini_with_retry(prompt: str, model_name: str = FAST_MODEL, max_retries: int = 3) -> str:
    """Executes a Gemini generation call with exponential back-off retries to handle 429/503 errors."""
    client = _get_client()
    if not client:
        return ""
        
    delay = 2  # Start with a 2-second delay
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            text = (response.text or "").strip()
            if not text:
                raise ValueError("Gemini returned an empty response (possible safety block or quota soft-limit).")
            return text
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


def parse_skills_from_resume(resume_text: str) -> dict:
    """Uses Gemini to extract structured profile data from a raw resume text."""
    prompt = f"""You are extracting structured data from a resume for a job-matching tool. Return ONLY valid JSON. No markdown fences, no prose before or after, no comments.

STRICT RULE — READ CAREFULLY:
Only extract a skill, tool, or technology if the EXACT term (or a direct alias) appears
literally in the text below. Never infer related or implied technologies.
- If the resume says "built a REST API," extract "REST API" only — do NOT add "Node.js,"
  "Express," or "Postman" unless those exact words appear elsewhere in the text.
- If the resume says "worked with databases," extract "databases" only — do NOT add
  "PostgreSQL," "MongoDB," or any specific database engine unless named explicitly.
- If unsure whether something counts as an explicit mention, leave it out. Under-extraction
  is safe; over-extraction is a serious error that misleads the candidate.

Extract these fields:

1. "skills": array of strings. Technical skills/tools/languages/frameworks explicitly named
   anywhere in the resume (skills section, project bullets, experience bullets). Normalize
   only exact aliases (e.g. "ReactJS" -> "React", "Node" -> "Node.js", "Py" is NOT a valid
   alias for "Python" — do not guess abbreviations). Deduplicate.

2. "projects": array of objects, each:
   {{"name": string, "tech_stack": array of strings (explicit only, same rule as above),
     "summary": string, max 15 words, in your own words}}

3. "experience_years": number. Sum of professional (full-time or paid part-time) experience
   only. Internships count as 0 toward this unless the resume itself frames them as full-time
   professional roles. If the resume is clearly a student/fresher resume with no professional
   roles, return 0.

4. "education_level": one of ["Undergraduate", "Postgraduate", "PhD"] — based on the highest
   degree in progress or completed.

5. "certifications": array of strings. Only formally named certifications or credentials
   (e.g. "AWS Certified Cloud Practitioner"). Do NOT include short online courses mentioned
   in passing (e.g. "completed a course on X") unless the resume explicitly calls it a
   certification or credential.

6. "years_since_graduation": number or null. Null if still enrolled / no graduation date stated.

If a field cannot be determined from the text, use an empty array, 0, or null as appropriate —
never fabricate a plausible-sounding value.

Resume text:
{resume_text}
"""

    try:
        text = execute_gemini_with_retry(prompt)

        # Strip markdown code fences (handles ```json ... ``` or ``` ... ```)
        text = re.sub(r"^```(?:json)?\s*", "", text.strip())
        text = re.sub(r"\s*```$", "", text).strip()

        # Strip trailing commas before } or ] (Gemini 2.5-flash emits these)
        text = re.sub(r",\s*([}\]])", r"\1", text)

        if not text:
            print("Error parsing resume structured data: Gemini returned empty text after cleanup.")
            return {}

        result = json.loads(text)
        if isinstance(result, dict):
            # Normalize skills to lowercase
            skills = result.get("skills", [])
            if isinstance(skills, list):
                result["skills"] = [str(s).lower().strip() for s in skills]
            return result
        return {}
    except Exception as e:
        print(f"Error parsing resume structured data: {e}")
        return {}


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

def compute_gap_analysis(resume_data: dict, jd_data: dict) -> dict:
    """Deterministic multi-signal skill and experience overlap matcher."""
    resume_skills = {s.lower().strip() for s in resume_data.get("skills", [])}
    required = {s.lower().strip() for s in jd_data.get("required_skills", [])}
    preferred = {s.lower().strip() for s in jd_data.get("preferred_skills", [])}

    ALIASES = {
        "react": {"reactjs", "react.js"},
        "node": {"nodejs", "node.js"},
        "vue": {"vuejs", "vue.js"},
        "angular": {"angularjs"},
        "next": {"nextjs", "next.js"},
        "postgres": {"postgresql"},
        "mongo": {"mongodb"},
        "docker": {"dockerfile"},
        "k8s": {"kubernetes"},
        "python": {"py"},
        "javascript": {"js"},
        "typescript": {"ts"},
        "golang": {"go"},
        "cpp": {"c++"},
    }

    def _canonical(term):
        for canon, aliases in ALIASES.items():
            if term == canon or term in aliases:
                return canon
        return term

    def fuzzy_match(skill_set_a, skill_set_b):
        canon_b = {_canonical(b): b for b in skill_set_b}
        matched = set()
        for a in skill_set_a:
            if _canonical(a) in canon_b:
                matched.add(a)
        return matched

    matched_required = fuzzy_match(required, resume_skills)
    matched_preferred = fuzzy_match(preferred, resume_skills)
    missing_required = required - matched_required

    # Signal 1: Required skills match (0–1.0)
    required_pct = len(matched_required) / len(required) if required else 1.0

    # Signal 2: Experience gap
    exp_gap = None
    min_exp = jd_data.get("min_experience_years") or 0
    res_exp = resume_data.get("experience_years") or 0
    if min_exp > res_exp:
        exp_gap = min_exp - res_exp
    # Experience compatibility score (1.0 = perfect fit, 0.0 = way off)
    if min_exp == 0:
        exp_score = 1.0
    elif res_exp >= min_exp:
        exp_score = 1.0
    elif exp_gap and exp_gap <= 1:
        exp_score = 0.75
    elif exp_gap and exp_gap <= 3:
        exp_score = 0.40
    else:
        exp_score = 0.10

    # Signal 3: Project domain relevance
    # Check if student projects use skills that overlap with job requirements
    projects = resume_data.get("projects", [])
    project_skills = set()
    for p in projects:
        project_skills.update(s.lower().strip() for s in p.get("tech_stack", []))
    project_overlap = fuzzy_match(required, project_skills)
    project_score = len(project_overlap) / len(required) if required else 0.5

    # Signal 4: Education fit
    edu = (resume_data.get("education_level") or "").lower()
    job_title_lower = (jd_data.get("job_title") or "").lower()
    if "phd" in edu or "postgrad" in edu:
        edu_score = 1.0
    elif "undergrad" in edu or "bachelor" in edu:
        # Undergrad is fine for most engineering roles
        if any(kw in job_title_lower for kw in ["research", "scientist", "principal", "staff"]):
            edu_score = 0.5  # these prefer postgrad
        else:
            edu_score = 0.9
    else:
        edu_score = 0.7  # unknown, don't penalise

    # Weighted composite score
    # Skills overlap is the strongest signal (50%), project relevance (25%),
    # experience (15%), education (10%)
    composite = (
        0.50 * required_pct +
        0.25 * project_score +
        0.15 * exp_score +
        0.10 * edu_score
    )

    return {
        "required_match_pct": round(required_pct * 100),
        "composite_pct": round(composite * 100),
        "matched_required": sorted(matched_required),
        "missing_required": sorted(missing_required),
        "matched_preferred": sorted(matched_preferred),
        "project_overlap": sorted(project_overlap),
        "project_score_pct": round(project_score * 100),
        "experience_gap_years": exp_gap,
        "exp_score_pct": round(exp_score * 100),
        "edu_score_pct": round(edu_score * 100),
        "education_level": resume_data.get("education_level") or "Unknown",
    }


def evaluate_resume_for_job(resume_text: str, job_title: str, company: str, job_description: str) -> str:
    """Evaluates candidate resume using 4-signal gap analysis + LLM recruiter advice."""
    # 1. Structured parse of the candidate resume
    resume_data = parse_skills_from_resume(resume_text)

    # 2. Structured parse of the JD
    from jd_skill_extractor import extract_skills_from_jd
    jd_data = extract_skills_from_jd(job_title, company, job_description)
    if not jd_data:
        jd_data = {"required_skills": [], "preferred_skills": []}
    jd_data["job_title"] = job_title  # passed into edu fit check

    # 3. Multi-signal gap analysis
    gaps = compute_gap_analysis(resume_data, jd_data)

    missing_req  = gaps["missing_required"]
    matched_req  = gaps["matched_required"]
    proj_overlap = gaps["project_overlap"]
    exp_gap      = gaps["experience_gap_years"]

    # 4. LLM recruiter advice — specific, named skills only
    advice_prompt = f"""A student is deciding whether and how to apply for {job_title} at {company}.

Verified gap data (do not invent any skill not listed here):
- Required skills matched: {matched_req}
- Required skills missing: {missing_req}
- Skills shown in their projects: {proj_overlap}
- Preferred skills matched: {gaps['matched_preferred']}
- Experience gap: {exp_gap} years (null = no gap)
- Education: {gaps['education_level']}

Write exactly 2 sentences of recruiter-grade advice:
- Name specific missing skills. If missing_required is empty, confirm strong match and suggest one preferred skill to add to a project.
- If there is an experience gap, mention one concrete workaround (e.g. open-source contribution, personal project using that stack).
- No generic phrases ("upskill yourself", "you can do it"). Be direct and actionable."""

    advice = "Focus on adding a project that demonstrates the missing required skills."
    try:
        advice = execute_gemini_with_retry(advice_prompt)
    except Exception as e:
        print(f"Error generating advice: {e}")

    # 5. Format multi-signal recruiter card
    matched_str = ", ".join(matched_req)  if matched_req  else "None detected"
    missing_str = ", ".join(missing_req)  if missing_req  else "None — strong match! ✅"
    proj_str    = ", ".join(proj_overlap) if proj_overlap else "Not shown in projects yet"
    pref_str    = ", ".join(gaps["matched_preferred"]) if gaps["matched_preferred"] else "None"
    exp_str     = f"{exp_gap} yr gap" if exp_gap else "No gap ✅"

    report = (
        f"*🎯 Overall Match: {gaps['composite_pct']}%*\n"
        f"━" * 21 + "\n"
        f"\n📊 *Why {gaps['composite_pct']}%? Signal breakdown:*\n"
        f"  • Skills match:       {gaps['required_match_pct']}%\n"
        f"  • Project relevance: {gaps['project_score_pct']}%\n"
        f"  • Experience fit:    {gaps['exp_score_pct']}%\n"
        f"  • Education fit:     {gaps['edu_score_pct']}%\n"
        f"\n✅ *Matched required skills:* {matched_str}\n"
        f"❌ *Critical gaps:* {missing_str}\n"
        f"🛠️ *Shown in your projects:* {proj_str}\n"
        f"⭐ *Preferred skills you have:* {pref_str}\n"
        f"📅 *Experience:* {exp_str}\n"
        f"\n🧠 *Recruiter take:*\n{advice}"
    )
    return report

