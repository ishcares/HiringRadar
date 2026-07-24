import logging
import os
import re
from datetime import datetime

from embeddings import calculate_cosine_similarity, get_embeddings_from_hf

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Skill synonym map — maps every known alias to a canonical form.
# Both student skills AND job skills are normalised through this before comparison
# so "Postgres", "PostgreSQL", "psql" all map to "postgresql".
# ---------------------------------------------------------------------------
_SKILL_SYNONYMS: dict[str, str] = {
    # Python ecosystem
    "py":               "python",

    # Node.js
    "node":             "nodejs",
    "node.js":          "nodejs",
    "node js":          "nodejs",

    # Go
    "golang":           "go",

    # Databases
    "postgres":         "postgresql",
    "psql":             "postgresql",
    "pg":               "postgresql",
    "mongo":            "mongodb",
    "elastic":          "elasticsearch",
    "es":               "elasticsearch",
    "dynamo":           "dynamodb",
    "dynamodb":         "dynamodb",
    "couch":            "couchdb",
    "maria":            "mariadb",
    "mssql":            "sqlserver",
    "sql server":       "sqlserver",
    "microsoft sql":    "sqlserver",

    # Cloud
    "gcp":              "googlecloud",
    "google cloud":     "googlecloud",
    "google cloud platform": "googlecloud",
    "aws":              "aws",
    "amazon web services": "aws",
    "azure":            "azure",
    "microsoft azure":  "azure",

    # Infrastructure
    "k8s":              "kubernetes",
    "kube":             "kubernetes",
    "docker compose":   "docker",
    "ci/cd":            "cicd",
    "ci cd":            "cicd",
    "github actions":   "githubactions",
    "gitlab ci":        "gitlabci",

    # Messaging / Streaming
    "apache kafka":     "kafka",
    "apache spark":     "spark",
    "apache airflow":   "airflow",
    "rabbit":           "rabbitmq",
    "rabbitmq":         "rabbitmq",
    "celery":           "celery",

    # ML
    "tensorflow":       "tensorflow",
    "tf":               "tensorflow",
    "pytorch":          "pytorch",
    "torch":            "pytorch",
    "sklearn":          "scikitlearn",
    "scikit-learn":     "scikitlearn",
    "scikit learn":     "scikitlearn",
    "hugging face":     "huggingface",
    "hf":               "huggingface",

    # Frontend
    "reactjs":          "react",
    "react.js":         "react",
    "vuejs":            "vue",
    "vue.js":           "vue",
    "nextjs":           "nextjs",
    "next.js":          "nextjs",
    "nuxtjs":           "nuxtjs",
    "nuxt.js":          "nuxtjs",
    "angular":          "angular",
    "angularjs":        "angular",
    "js":               "javascript",
    "ts":               "typescript",

    # Backend frameworks
    "fastapi":          "fastapi",
    "fast api":         "fastapi",
    "django rest":      "django",
    "django rest framework": "django",
    "drf":              "django",
    "spring boot":      "springboot",
    "spring":           "springboot",
    "express":          "expressjs",
    "express.js":       "expressjs",
    "nestjs":           "nestjs",
    "nest.js":          "nestjs",
    "flask":            "flask",
    "gin":              "gin",  # Go Gin framework
    "fiber":            "fiber", # Go Fiber framework

    # Version control
    "github":           "git",
    "gitlab":           "git",
    "bitbucket":        "git",

    # Systems
    "unix":             "linux",
    "ubuntu":           "linux",
    "centos":           "linux",
    "debian":           "linux",
    "macos":            "macos",

    # ORM / Query
    "sqlalchemy":       "sqlalchemy",
    "prisma":           "prisma",
    "sequelize":        "sequelize",
    "hibernate":        "hibernate",

    # Tools
    "vscode":           "vscode",
    "vs code":          "vscode",
    "intellij":         "intellij",
    "pycharm":          "pycharm",

    # Languages — common abbreviations
    "c++":              "cpp",
    "c plus plus":      "cpp",
    "c#":               "csharp",
    "c sharp":          "csharp",
    "dotnet":           "csharp",
    ".net":             "csharp",
    "kotlin":           "kotlin",
    "swift":            "swift",
    "ruby":             "ruby",
    "r":                "rlang",
    "rust":             "rust",
    "scala":            "scala",
    "perl":             "perl",
    "php":              "php",
    "lua":              "lua",
    "shell":            "bash",
    "bash scripting":   "bash",
    "shell scripting":  "bash",
}


def _norm_skill(skill: str) -> str:
    """
    Normalise a skill name for synonym-aware comparison.

    Steps:
    1. Lowercase + strip whitespace
    2. Strip punctuation that doesn't change meaning (trailing dots, parens)
    3. Lookup in _SKILL_SYNONYMS — map to canonical form if found
    4. Remove all non-alphanumeric characters for final comparison key

    Examples:
        "PostgreSQL" → "postgresql"
        "Postgres"   → "postgresql"  (synonym map)
        "Node.js"    → "nodejs"
        "node"       → "nodejs"  (synonym map)
        "K8s"        → "kubernetes"  (synonym map)
    """
    cleaned = skill.lower().strip().rstrip(".")
    # Check synonym map (exact cleaned string)
    canonical = _SKILL_SYNONYMS.get(cleaned, cleaned)
    # Remove all non-alphanumeric characters to get the final key
    return re.sub(r"[^a-z0-9]", "", canonical)

# ---------------------------------------------------------------------------
# Tuning knobs — override via env vars without redeploying
# ---------------------------------------------------------------------------
MATCH_THRESHOLD = float(os.getenv("MATCH_THRESHOLD", "0.15"))
ROLE_BONUS      = float(os.getenv("ROLE_BONUS",      "0.15"))
INTERN_BONUS    = float(os.getenv("INTERN_BONUS",    "0.05"))

# ---------------------------------------------------------------------------
# In-process embedding cache — keyed on (title, company) tuple
# Avoids re-embedding the same job titles on every 5-min alert cycle.
# NOTE: unbounded for now — fine at 7-company scale, revisit before scaling up.
# ---------------------------------------------------------------------------
_EMBED_CACHE: dict[tuple, list[float]] = {}

# Fallback display values used ONLY when the HF embedding API is unavailable
# and we fall back to keyword-only scoring. Keyed on the exact bonus-sum
# values produced by _keyword_fallback_scores, so they never collide with
# real cosine-similarity scores.
_FALLBACK_DISPLAY_MAP = {
    round(ROLE_BONUS + INTERN_BONUS, 2): 0.90,  # role + intern match
    round(ROLE_BONUS, 2):                0.80,  # role match only
    round(INTERN_BONUS, 2):              0.65,  # intern match only
}


keyword_map = {
    # Tech Roles
    "backend":   ["backend", "server", "api", "django", "node", "golang", "java", "spring", "software engineer", "software developer", "sde"],
    "frontend":  ["frontend", "react", "vue", "angular", "ui", "javascript", "css"],
    "ml":        ["machine learning", "ml", "ai", "deep learning", "nlp", "data science"],
    "data":      ["data engineer", "data analyst", "analytics", "sql", "etl"],
    "devops":    [
        "devops", "sre", "site reliability", "kubernetes", "docker",
        "infrastructure", "platform engineer", "devsecops", "helm",
        "terraform", "ci/cd", "gitops",
    ],
    "fullstack": ["fullstack", "full stack", "full-stack", "software engineer", "software developer", "sde"],
    "android":   ["android", "kotlin"],
    "ios":       ["ios", "swift"],

    # MBA / Business Roles
    "pm":        ["product manager", "apm", "associate product manager", "associate pm", "product management", "product intern", "product analyst"],
    "analyst":   ["business analyst", "operations analyst", "strategy analyst", "program analyst", "analyst"],
    "consulting":["consultant", "consulting", "management trainee", "management consultant"],
    "growth":    ["growth", "growth hacker", "growth manager", "marketing analyst", "marketing manager"],
    "finance":   ["finance", "financial analyst", "investment analyst", "corporate finance", "treasury analyst"],

    # Design Roles
    "design":    ["design", "ux", "ui designer", "product design", "figma", "interaction designer", "visual designer"],
}

# Common abbreviations to expand before embedding so the model understands them
_ABBREV = {
    "engg": "engineering", "eng": "engineering", "swe": "software engineer",
    "sde": "software development engineer", "dev": "developer",
    "ai": "artificial intelligence", "ml": "machine learning",
    "nlp": "natural language processing", "cv": "computer vision",
    "fe": "frontend", "be": "backend", "fs": "fullstack",
    "ios": "iOS mobile", "infra": "infrastructure",
    "intern": "internship", "jr": "junior", "sr": "senior",
}


def group_jobs(jobs):
    seen = {}
    for job in jobs:
        key = (job["company"], job["title"].strip(), job["location"])
        if key not in seen:
            seen[key] = {**job, "count": 1}
        else:
            seen[key]["count"] += 1
    return list(seen.values())


def get_experience_tag(title: str, description: str = "") -> str:
    # First check description for explicit experience year requirements
    # NOTE: description can be None when loaded from Supabase (NULL != empty string).
    desc_lower = (description or "").lower()
    if desc_lower:
        # Allow for adverbs/adjectives between "of" and "experience"
        # e.g. "8+ years of meaningful experience", "5+ years of hands-on work"
        exp_match = re.search(
            r"(\b\d+)(?:-\d+)?\+?\s*(?:years?|yrs?)\b\s*(?:of\s+)?(?:\w+\s+)*(?:experience|software|work|product)",
            desc_lower
        )
        if exp_match:
            try:
                years = int(exp_match.group(1))
                if years >= 5:
                    return "🚀 Senior (5+ yrs)"
                if years >= 2:
                    return "💼 Mid-level (2-5 yrs)"
            except ValueError:
                pass

    t = title.lower()

    # Use word boundary checks to avoid partial matches
    if re.search(r"\b(intern|internship|trainee|campus|fresher|new grad)\b", t):
        return "🌱 Fresher / Intern"
    if re.search(r"\b(director|vp|vice president|head of|chief)\b", t):
        return "👑 Director / VP"
    if re.search(r"\b(engineering manager|tech lead|team lead|lead engineer|engineering lead|lead)\b", t):
        return "🏆 Manager / Lead"
    if (
        re.search(r"\b(principal|staff|architect|sde-3|sde iii|sde3|sdeiii|pmts)\b", t)
        or re.search(r"\b(?:engineer|developer|sde|swe|analyst|qa|specialist|mts)[\s-]*(?:iv|v|4|5|6)\b", t)
    ):
        return "⚡ Staff / Principal"

    # ── Senior / SDE-2 detection ──────────────────────────────────────────────
    # Catches: Senior, Sr., SDE-2, SDE-II, SDE 2, SDE2, SDE II, SDEii, SMTs, etc.
    # Also numeric/roman level 3 (e.g. Support Engineer 3, QA Engineer III)
    if (
        re.search(r"\b(senior|sr\.?|smts|lmts)\b", t)
        or re.search(r"\b(?:engineer|developer|sde|swe|analyst|qa|specialist|mts)[\s-]*(?:iii|3)\b", t)
    ):
        return "🚀 Senior (5+ yrs)"

    # Standalone MTS = Salesforce Member of Technical Staff (≈SDE-2, 3+ yrs)
    # Must be checked BEFORE the generic mid-level pattern to avoid partial-match confusion.
    if re.search(r"\bmts\b", t):
        return "💼 Mid-level (2-5 yrs)"

    if (
        re.search(r"\b(?:sde|swe|software\s+(?:development\s+)?engineer|engineer|developer|qa|analyst|specialist)[\s-]*(?:ii|2)\b", t)
        or re.search(r"\b(mid-level|mid level|experienced)\b", t)
    ):
        return "💼 Mid-level (2-5 yrs)"
    # ── End senior / SDE-2 detection ─────────────────────────────────────────

    if (
        re.search(r"\b(junior|jr\.?|sde-1|sde i|sde1|associate)\b", t)
        or re.search(r"\b(?:engineer|developer|sde|swe|analyst|qa|specialist|mts)[\s-]*(?:i|1)\b", t)
    ):
        return "🔵 Junior (0-2 yrs)"

    return "💼 Software Engineer"


# Tags that indicate a role is NOT fresher/entry-level friendly.
# SDE-2 / Mid-level is included — a 2026 grad should not get SDE-2 alerts.
_SENIOR_TAGS = {
    "👑 Director / VP",
    "🏆 Manager / Lead",
    "⚡ Staff / Principal",
    "🚀 Senior (5+ yrs)",
    "💼 Mid-level (2-5 yrs)",   # SDE-2, Engineer II — needs 2-4 yrs experience
}


def is_senior(title: str, description: str = "") -> bool:
    """True if the job's experience tag indicates a senior/lead+ role."""
    return get_experience_tag(title, description) in _SENIOR_TAGS


def get_graduation_tag(title: str, grad_year: int, description: str = "") -> str:
    current_year = datetime.now().year
    years_to_grad = grad_year - current_year
    exp_tag = get_experience_tag(title, description)

    if years_to_grad <= 0:
        if any(x in exp_tag for x in ["Fresher", "Intern", "Junior", "Software Engineer"]):
            return "✅ Good for you"
        return "⚠️ May need experience"
    else:
        if any(x in exp_tag for x in ["Fresher", "Intern"]):
            return "✅ Good for you"
        if "Software Engineer" in exp_tag or "Junior" in exp_tag:
            return "⚠️ May need experience (Full-time)"
        return "⚠️ Check requirements"


def matches_role(title: str, roles: list) -> bool:
    if not roles:
        return True
    title_lower = title.lower()
    for role in roles:
        keywords = keyword_map.get(role, [role])
        for k in keywords:
            if re.search(rf"\b{re.escape(k)}\b", title_lower):
                return True
    return False


def is_internship(job: dict) -> bool:
    return any(k in job["title"].lower() for k in ["intern", "internship", "trainee"])


def is_early_career(job: dict) -> bool:
    """
    True if the role is explicitly designed for fresh graduates / campus hires.
    These are full-time roles but targeted at 0-experience candidates.

    Examples: "Software Engineer, Early Career", "Graduate Software Engineer",
    "New Grad SDE", "Campus Hire", "Associate SDE", "Technology Analyst Program"
    """
    title_lower = job["title"].lower()
    desc_lower = (job.get("description") or "").lower()
    early_keywords = [
        "early career",
        "new grad",
        "new graduate",
        "graduate program",
        "grad program",
        "graduate hire",
        "graduate engineer",
        "graduate developer",
        "campus hire",
        "campus recruitment",
        "campus program",
        "university graduate",
        "university program",
        "rotational program",
        "associate program",
        "technology analyst program",
        "analyst program",
        "fresher",
        "entry level",
        "entry-level",
        "0 years",
        "0-1 year",
        "0 to 1 year",
    ]
    # Check title first (strongest signal)
    if any(k in title_lower for k in early_keywords):
        return True
    # Check first 500 chars of description for explicit fresher targeting
    desc_snippet = desc_lower[:500]
    if any(k in desc_snippet for k in ["fresh graduate", "recent graduate", "campus recruit", "fresher candidate", "0-1 year"]):
        return True
    return False


def filter_by_job_type(jobs: list, job_type: str) -> list:
    if job_type == "both" or not job_type:
        return jobs
    return [j for j in jobs if (job_type == "internship") == is_internship(j)]


def extract_target_batch_years(title: str, description: str) -> set:
    """
    Extract graduation batch years explicitly mentioned in a job posting.
    Returns a set of years (e.g. {2026, 2027}).

    Patterns matched (case-insensitive):
      - "2027 batch" / "batch 2027" / "batch of 2027"
      - "graduating in/by 2027" / "graduation 2027"
      - "pass-out 2027" / "passout 2027" / "pass out 2027"
      - "2026/2027 graduates" / "2026-27 batch"
      - "fresher 2027" / "freshers from 2027"
      - "2027 pass out" / "2027 graduate"
    """
    text = (title + " " + (description or "")).lower()
    found = set()

    # "batch 2027" / "2027 batch" / "batch of 2027" / "cohort 2027"
    for m in re.finditer(
        r'\b(?:batch|cohort)\s+(?:of\s+)?(\d{4})\b|\b(\d{4})\s+batch\b', text
    ):
        yr = int(m.group(1) or m.group(2))
        if 2020 <= yr <= 2032:
            found.add(yr)

    # "graduating in/by 2027" / "graduation year 2027" / "graduation: 2027"
    for m in re.finditer(r'graduating\s+(?:in|by)?\s*(\d{4})|graduation\s+(?:year\s+|:\s*)?(\d{4})', text):
        yr = int(m.group(1) or m.group(2))
        if 2020 <= yr <= 2032:
            found.add(yr)

    # "pass-out 2027" / "pass out 2027" / "passout 2027" / "2027 pass-out"
    for m in re.finditer(r'pass[\s-]?out\s+(\d{4})|(\d{4})\s+pass[\s-]?out', text):
        yr = int(m.group(1) or m.group(2))
        if 2020 <= yr <= 2032:
            found.add(yr)

    # "2026/2027" or "2026-27" followed by batch/graduate/pass
    for m in re.finditer(
        r'\b(\d{4})[/-](\d{2}|\d{4})\s*(?:batch|graduates?|pass|passing)', text
    ):
        yr1 = int(m.group(1))
        raw2 = m.group(2)
        yr2 = int(raw2) if len(raw2) == 4 else yr1 // 100 * 100 + int(raw2)
        for yr in (yr1, yr2):
            if 2020 <= yr <= 2032:
                found.add(yr)

    # "freshers from/of/batch 2027" / "fresher 2027"
    for m in re.finditer(r'freshers?\s+(?:of|from|batch)?\s*(\d{4})', text):
        yr = int(m.group(1))
        if 2020 <= yr <= 2032:
            found.add(yr)

    return found


def _expand_title(title: str) -> str:
    """Expand abbreviations in job titles before embedding."""
    words = title.lower().split()
    return " ".join(_ABBREV.get(w.strip(".,/-"), w) for w in words)


def _build_profile_text(student: dict) -> str:
    """
    Build a rich, semantically dense profile string for embedding.

    Design goals:
    - Mirror the language a JD uses ("proficient in", "experience with") so
      cosine similarity is maximised between profile and JD embeddings.
    - Enumerate every skill individually — embedding models treat each word
      as signal; a list "Python, SQL, React" beats "programming skills".
    - State job-type clearly (internship vs full-time) so the model can
      distinguish a grad fresher from a mid-level professional.
    """
    roles = student.get("preferred_roles") or []
    skills = student.get("skills") or []
    job_type = student.get("job_type", "both")
    grad_year = student.get("graduation_year", datetime.now().year)
    current_year = datetime.now().year
    years_left = grad_year - current_year

    role_descriptions = {
        "backend": "backend server-side API development using REST APIs, microservices, databases",
        "frontend": "frontend UI development with React, TypeScript, CSS, web performance",
        "ml": "machine learning, deep learning, NLP, computer vision, AI model training and deployment",
        "data": "data engineering, analytics pipelines, SQL, ETL, data warehousing, BI",
        "devops": "DevOps, cloud infrastructure, Kubernetes, Docker, CI/CD, site reliability engineering",
        "fullstack": "fullstack web development covering both frontend React and backend APIs",
        "android": "Android mobile app development with Kotlin, Jetpack Compose, Android SDK",
        "ios": "iOS mobile app development with Swift, SwiftUI, Xcode",
        "pm": "product management, roadmap planning, user research, agile, cross-functional teams",
        "analyst": "business analysis, data analysis, dashboards, stakeholder reporting",
        "design": "product design, UX research, Figma, interaction design, usability testing",
    }

    # Compute experience level from graduation year
    if years_left > 1:
        exp_level = "final year student seeking internship"
        position_type = "internship or summer internship"
    elif years_left >= 0:
        exp_level = "fresh graduate seeking entry-level full-time role or internship"
        position_type = "full-time entry-level or internship"
    else:
        exp_level = "software professional with up to 2 years of experience"
        position_type = "full-time software engineering"

    # Override with explicit job_type preference if set
    if job_type == "internship":
        position_type = "internship"
    elif job_type == "full-time":
        position_type = "full-time entry-level"

    role_desc = " and ".join(role_descriptions.get(r, r) for r in roles) or "software engineering"
    skills_str = ", ".join(skills) if skills else "programming and software development"

    return (
        f"I am a {exp_level} looking for {position_type} positions. "
        f"My areas of interest include {role_desc}. "
        f"I am proficient in {skills_str}. "
        f"I am seeking roles in software engineering, technology, and product development "
        f"at startups and technology companies."
    )


def _filter_fresher_jobs(jobs: list, grad_year: int, current_year: int, student_years: int | None = None) -> list:
    """Keep roles appropriate for the student's actual experience level.

    student_years — the explicit years_of_experience from their profile (0=fresher, 1, 2, 4).
    If not provided, falls back to inferring from graduation year.
    """
    # Determine the student's effective years of experience
    if student_years is not None:
        effective_exp = student_years
    else:
        # Fallback: infer from graduation year
        effective_exp = max(0, current_year - grad_year)

    # Students who have been working 3+ years are not filtered as freshers
    if effective_exp >= 3:
        return jobs

    # Hard filter: reject jobs requiring more experience than the student has (+ 1yr buffer)
    _MAX_EXP = effective_exp + 1  # e.g. fresher (0) → max job req 1yr, junior1 (1) → max 2yr
    jobs = [
        j for j in jobs
        if (j.get("min_years_experience") or 0) <= _MAX_EXP
    ]

    fresher_keywords = [
        "intern", "internship", "fresher", "junior", "graduate", "new grad",
        "sde-1", "sde1", "associate", "entry",
    ]
    non_fresher_tags = {
        "👑 Director / VP", "🏆 Manager / Lead",
        "⚡ Staff / Principal", "🚀 Senior (5+ yrs)",
        "💼 Mid-level (2-5 yrs)",
    }
    fresher_jobs = [
        j for j in jobs
        if any(k in j["title"].lower() for k in fresher_keywords)
        and get_experience_tag(j["title"], j.get("description") or "") not in non_fresher_tags
    ]
    generic_ok = [
        j for j in jobs
        if get_experience_tag(j["title"], j.get("description") or "") not in non_fresher_tags
        and j not in fresher_jobs
    ]
    return fresher_jobs + generic_ok


def _keyword_fallback_scores(jobs: list, roles: list, grad_year: int, current_year: int) -> list[float]:
    """Keyword-only scorer used when the HF API is unavailable.

    Scores are deterministic and based purely on hard signals:
    - Role keyword match  → +ROLE_BONUS
    - Internship match    → +INTERN_BONUS
    Base score is 0.0, so nothing crosses threshold unless it keyword-matches.
    """
    scores = []
    for job in jobs:
        score = 0.0
        if matches_role(job["title"], roles):
            score += ROLE_BONUS
        if grad_year >= current_year - 1 and is_internship(job):
            score += INTERN_BONUS
        if is_non_tech(job["title"]):
            score = 0.0
        scores.append(score)
    return scores


def is_non_tech(title: str) -> bool:
    """Return True if the job title indicates a non-engineering/non-tech role."""
    title_lower = title.lower()
    non_tech_keywords = [
        "collection manager",
        "lending collections",
        "sales executive",
        "business development executive",
        "bde",
        "telecaller",
        "customer support",
        "customer success",   # was missing — "Customer Success Manager" scored non-zero
        "hr recruiter",
        "hr manager",
        "account manager",
        "account executive",
        "operations executive",
        "marketing manager",
        "area collection",
    ]
    return any(k in title_lower for k in non_tech_keywords)


def check_eligibility(
    student: dict,
    job_title: str,
    company: str,
    description: str,
    category: str = None,
    min_years_experience: int = None,
) -> tuple[bool, str]:
    """
    Checks if a student is eligible for a given job.
    Returns:
        (is_eligible, ineligibility_reason)
    """
    if not student:
        return True, ""

    title_lower = job_title.lower()
    desc_lower = (description or "").lower()
    
    # Clean department
    dept = (student.get("department") or "cse").lower().strip()
    
    # Graduation year
    current_year = datetime.now().year
    grad_year = student.get("graduation_year") or current_year
    
    # Skills normalisation
    student_skills = [str(s).lower().strip() for s in (student.get("skills") or [])]
    
    # ── 1. DCEO / Mechanical / Electrical / Facilities vs CS student ──
    is_dceo_or_ops = (
        "dceo" in title_lower or 
        "data center engineering operations" in title_lower or
        "hvac" in title_lower or 
        "facilities engineer" in title_lower or
        "mechanical engineer" in title_lower or 
        "electrical engineer" in title_lower or
        "power engineer" in title_lower or 
        "cooling" in title_lower or 
        "generator" in title_lower or
        "chiller" in title_lower or 
        "civil engineer" in title_lower or
        "logistics specialist" in title_lower or
        "high voltage" in title_lower or
        "datacenter technician" in title_lower or
        "critical facilities" in title_lower
    )
    
    is_cs_student = any(kw in dept for kw in ["cse", "it", "cs", "computer science", "data science", "ds", "software"])
    
    if is_dceo_or_ops and is_cs_student:
        return False, "This is an electrical/mechanical/facilities engineering role (DCEO/HVAC/Logistics), which does not align with your Computer Science / IT background."

    # ── 2. Hardware/VLSI vs CS Student fit ──
    is_hardware_job = (
        category == "hardware" or
        any(kw in title_lower for kw in ["vlsi", "asic", "rtl", "silicon", "analog design", "physical design", "fpga", "chip design"]) or
        any(kw in desc_lower[:1000] for kw in ["verilog", "systemverilog", "vhdl", "rtl design", "synthesis", "semiconductor"])
    )
    
    is_hardware_student = (
        any(kw in dept for kw in ["ece", "ee", "electronics", "electrical", "instrumentation"]) or
        any(any(kw in sk for kw in ["vlsi", "synthesis", "physical design", "verilog", "embedded"]) for sk in student_skills)
    )
    
    if is_hardware_job and not is_hardware_student:
        return False, "This is a hardware engineering role (VLSI/Silicon/ASIC), which requires an Electronics/Electrical background, but your profile is Computer Science/IT."

    # ── 3. Internship vs Graduated student ──
    is_intern = any(k in title_lower for k in ["intern", "internship", "trainee"])
    if is_intern and grad_year < current_year:
        return False, f"This is an internship role that requires candidates to be currently enrolled in college, but your profile indicates you graduated in {grad_year}."

    # ── 4. Senior/Mid-level vs Fresher ──
    min_exp = min_years_experience
    if min_exp is None:
        tag = get_experience_tag(job_title, description)
        if tag in _SENIOR_TAGS:
            if "Mid-level" in tag:
                min_exp = 2
            elif "Senior" in tag:
                min_exp = 5
            elif "Staff" in tag:
                min_exp = 8
            else:
                min_exp = 3

    if min_exp and min_exp >= 2:
        student_exp = student.get("years_of_experience")
        if student_exp is None:
            # Infer from graduation year (0 if still in college, positive if graduated)
            student_exp = max(0, current_year - grad_year)

        if student_exp < min_exp:
            return False, f"This role requires a minimum of {min_exp} years of professional experience. Your profile shows approximately {student_exp} year(s) of experience, which does not meet this requirement."

    # ── 5. Non-tech job fit for tech student ──
    if is_non_tech(job_title) and is_cs_student:
        return False, "This is a non-technical role (Sales/Operations/Recruiting), which does not align with your technical Software Engineering goals."

    return True, ""


# ── Scoring weights (all 4 signals, must sum to 1.0) ─────────────────────────
# Tune via env vars without redeployment.
_W_SEMANTIC  = float(os.getenv("SCORE_W_SEMANTIC",  "0.45"))  # skills embedding (title + JD)
_W_SKILLS    = float(os.getenv("SCORE_W_SKILLS",    "0.25"))  # explicit skills keyword overlap
_W_EXP       = float(os.getenv("SCORE_W_EXP",       "0.20"))  # experience level compatibility
_W_LOCATION  = float(os.getenv("SCORE_W_LOCATION",  "0.10"))  # location preference match
_JD_CHARS    = int(os.getenv("SCORE_JD_CHARS",      "400"))   # how many JD chars to embed

# Sub-weights within the semantic signal
_W_TITLE  = 0.40   # title proportion of semantic
_W_JD     = 0.60   # JD proportion of semantic (when description present)


def _skills_overlap_score(
    student_skills: list,
    job_title: str,
    job_desc: str,
    job_required_skills: list | None = None,
    job_preferred_skills: list | None = None,
) -> float:
    """
    Signal 2 — Synonym-aware, structured-first skill overlap.

    TWO-PATH SCORING:

    Path A — Structured skills (preferred): When the job has Gemini-extracted
    required_skills[], compare normalised student skills against that clean list.
    This is far more accurate than raw text scan because:
      - Skills are atomic ("PostgreSQL" not "experience with databases")
      - No false positives from skill words appearing in prose
      - Preferred skills give a bonus on top of required skills score

    Path B — Raw text fallback: When required_skills[] is empty or None,
    fall back to word-boundary regex scan of job title + description text.
    This ensures we always return a signal even for un-extracted jobs.

    Both paths use _norm_skill() for synonym normalisation:
      "Postgres" and "PostgreSQL" now correctly match each other.

    Scoring:
      Path A:
        base  = matched_required / total_required     (0–1)
        bonus = 0.05 * min(matched_preferred, 3)      (up to +0.15)
        Final = min(1.0, base + bonus)
      Path B:
        matched / total_student_skills                (0–1)

    Returns:
        float in [0.0, 1.0]. Returns 0.4 (neutral-low) when student has no skills.
    """
    if not student_skills:
        return 0.4  # neutral-low: no skills set → small penalty vs 0.5 to reduce false positives

    student_norm = {_norm_skill(s) for s in student_skills}

    # ── Path A: Structured Gemini-extracted skills ────────────────────────────
    if job_required_skills:  # non-empty list from jd_skill_extractor
        required_norm = [_norm_skill(s) for s in job_required_skills]
        total_required = len(required_norm)

        matched_required = sum(1 for s in required_norm if s in student_norm)
        base = matched_required / total_required if total_required else 0.0

        # Preferred skills bonus: each matched preferred skill adds 0.05 (cap 3)
        bonus = 0.0
        if job_preferred_skills:
            preferred_norm = [_norm_skill(s) for s in job_preferred_skills]
            matched_preferred = sum(1 for s in preferred_norm if s in student_norm)
            bonus = 0.05 * min(matched_preferred, 3)

        score = min(1.0, base + bonus)
        logger.debug(
            "[skills_overlap] Structured path: req=%d matched=%d pref_bonus=%.2f → %.3f",
            total_required, matched_required, bonus, score,
        )
        return round(score, 4)

    # ── Path B: Raw text fallback (no extracted skills yet) ───────────────────
    haystack = (job_title + " " + job_desc).lower()
    matched = 0
    for skill in student_skills:
        skill_clean = str(skill).lower().strip()
        # Try both the original form and the synonym-normalised form
        patterns = {skill_clean, _SKILL_SYNONYMS.get(skill_clean, skill_clean)}
        for pat in patterns:
            if pat and re.search(r"\b" + re.escape(pat) + r"\b", haystack):
                matched += 1
                break

    score = matched / len(student_skills)
    logger.debug(
        "[skills_overlap] Raw-text path: student_skills=%d matched=%d → %.3f",
        len(student_skills), matched, score,
    )
    return round(score, 4)


def _experience_score(job_title: str, job_desc: str, grad_year: int, current_year: int) -> float:
    """
    Signal 3 — Experience compatibility.

    Returns how well the student's experience level fits the role:
      1.0 = perfect fit (fresher for intern/fresher role, or grad for generic SDE)
      0.7 = acceptable (slightly over/under qualified)
      0.3 = poor fit (senior role for fresh grad)
      0.0 = zero fit (director/VP for student)

    Unlike the binary filter, this contributes positively to the match score,
    so a perfect-level role actually boosts the final percentage.
    """
    tag = get_experience_tag(job_title, job_desc or "")
    years_since_grad = current_year - grad_year   # negative = still studying

    if tag in ("🌱 Fresher / Intern",):
        # Fresher/intern role
        if years_since_grad <= 0:
            return 1.0   # perfect: still in college, role is for students
        elif years_since_grad <= 1:
            return 0.85  # just graduated, still fine
        else:
            return 0.50  # over-qualified for pure intern

    elif tag in ("🔵 Junior (0-2 yrs)",):
        if years_since_grad <= 1:
            return 1.0   # perfect: fresh grad for junior role
        elif years_since_grad <= 2:
            return 0.85
        elif years_since_grad <= 0:
            return 0.70  # final-year student: slightly junior
        else:
            return 0.40

    elif tag in ("💼 Software Engineer",):   # generic title, no level signal
        if years_since_grad <= 2:
            return 0.85  # most generic SDE roles accept fresh grads
        return 0.65

    elif tag in ("💼 Mid-level (2-5 yrs)",):
        if years_since_grad <= 1:
            return 0.30  # fresh grad applying for SDE-2: poor fit
        elif years_since_grad <= 3:
            return 0.70
        return 0.85

    elif tag in ("🚀 Senior (5+ yrs)",):
        if years_since_grad <= 2:
            return 0.15
        return 0.50

    elif tag in ("🏆 Manager / Lead", "⚡ Staff / Principal", "👑 Director / VP"):
        return 0.05  # essentially never right for a student

    return 0.60  # fallback


def _location_score(job_location: str, preferred_locations: list) -> float:
    """
    Signal 4 — Location compatibility.

    Returns how well the job location matches student preferences:
      1.0 = exact match (student wants Bangalore, job is Bangalore)
      0.85 = remote (always acceptable)
      0.60 = student set 'any' (no preference = neutral)
      0.10 = no match (student wants Mumbai, job is Chennai)

    Unlike the binary filter in match_jobs_for_student (which drops
    non-matching jobs entirely), this is a SOFT signal — a Mumbai-student
    seeing a Bangalore job gets a lower score, not zero.
    """
    if not preferred_locations:
        return 0.60  # no preference = neutral

    if any(loc.lower().strip() == "any" for loc in preferred_locations):
        return 0.60  # student accepts anywhere = neutral

    job_loc_lower = (job_location or "").lower()

    # Remote roles are always acceptable
    if "remote" in job_loc_lower:
        return 0.85

    # Check if any preferred city appears in job location
    for loc in preferred_locations:
        if str(loc).lower().strip() in job_loc_lower:
            return 1.0  # exact city match

    return 0.10  # no match — penalise but don't zero out


def _score_jobs(jobs: list, student: dict, roles: list, embed_fn) -> tuple[list[float], bool]:
    """
    4-signal hybrid scorer.

    Signal 1 — Semantic similarity (weight _W_SEMANTIC):
      cosine(profile_embedding, title_embedding + JD_embedding)
      Profile text is built from skills, roles, grad level.

    Signal 2 — Skills overlap (weight _W_SKILLS) — STRUCTURED-FIRST:
      When the job has Gemini-extracted required_skills[], compares normalised
      student skills against that clean structured list.
      Falls back to raw JD text scan when required_skills is not yet available.
      Both paths use synonym normalisation (_norm_skill) so
      'Postgres' correctly matches 'PostgreSQL' etc.

    Signal 3 — Experience compatibility (weight _W_EXP):
      Uses min_years_experience from jobs_cache when available (Gemini-extracted)
      for precise year-requirement matching. Falls back to title-based tag inference.
      1.0 = perfect level fit, 0.0 = completely wrong level.

    Signal 4 — Location compatibility (weight _W_LOCATION):
      How well the job location matches preferred_locations.
      1.0 = exact city, 0.85 = remote, 0.10 = no match.

    Non-tech hard zero still applied after blending.
    """
    current_year = datetime.now().year
    grad_year = student.get("graduation_year", current_year)
    pref_locs = student.get("preferred_locations") or []
    student_skills = student.get("skills") or []

    profile_text = _build_profile_text(student)

    # ── Build title texts and find cache misses ──────────────────────────────
    title_texts: list[str] = []
    title_cache_keys: list[tuple] = []
    for j in jobs:
        key = (j["title"], j.get("company", ""))
        text = f"{_expand_title(j['title'])} at {j.get('company', '')} in {j.get('location', '')}".strip()
        title_texts.append(text)
        title_cache_keys.append(key)

    title_missing = [i for i, k in enumerate(title_cache_keys) if k not in _EMBED_CACHE]

    # ── Build JD texts (truncated) ───────────────────────────────────────────
    jd_texts: list[str] = []
    jd_cache_keys: list[tuple] = []
    for j in jobs:
        desc = (j.get("description") or "")[:_JD_CHARS].strip()
        key = ("jd", j["title"], j.get("company", ""))
        jd_texts.append(desc)
        jd_cache_keys.append(key)

    jd_missing = [i for i, k in enumerate(jd_cache_keys) if jd_texts[i] and k not in _EMBED_CACHE]

    # ── Batch embed: profile + missing titles + missing JDs ──────────────────
    texts_to_embed = ([profile_text]
                      + [title_texts[i] for i in title_missing]
                      + [jd_texts[i]    for i in jd_missing])

    fresh_embeddings = embed_fn(texts_to_embed)

    if not fresh_embeddings or len(fresh_embeddings) < 1:
        logger.warning(
            "Local embedding model returned no data. "
            "Falling back to keyword-only scoring."
        )
        return _keyword_fallback_scores(jobs, roles, grad_year, current_year), True

    profile_emb = fresh_embeddings[0]
    fresh_rest   = fresh_embeddings[1:]

    title_fresh = fresh_rest[:len(title_missing)]
    jd_fresh    = fresh_rest[len(title_missing):]

    for idx, emb in zip(title_missing, title_fresh):
        _EMBED_CACHE[title_cache_keys[idx]] = emb
    for idx, emb in zip(jd_missing, jd_fresh):
        _EMBED_CACHE[jd_cache_keys[idx]] = emb

    # ── Compute per-job scores ────────────────────────────────────────────────
    scores: list[float] = []

    for i, job in enumerate(jobs):
        # Hard zero for non-tech roles — skip all other computation
        if is_non_tech(job["title"]):
            scores.append(0.0)
            continue

        title  = job["title"]
        desc   = job.get("description") or ""
        loc    = job.get("location", "")

        # ── Signal 1: Semantic similarity ─────────────────────────────────────
        title_emb  = _EMBED_CACHE[title_cache_keys[i]]
        title_sim  = calculate_cosine_similarity(profile_emb, title_emb)

        jd_key = jd_cache_keys[i]
        if jd_texts[i] and jd_key in _EMBED_CACHE:
            jd_sim    = calculate_cosine_similarity(profile_emb, _EMBED_CACHE[jd_key])
            sem_score = _W_TITLE * title_sim + _W_JD * jd_sim
        else:
            sem_score = title_sim

        # ── Signal 2: Skills overlap (structured-first) ───────────────────────
        job_required  = job.get("required_skills") or []
        job_preferred = job.get("preferred_skills") or []
        skill_score = _skills_overlap_score(
            student_skills, title, desc,
            job_required_skills=job_required,
            job_preferred_skills=job_preferred,
        )

        # ── Signal 3: Experience compatibility ────────────────────────────────
        # Use Gemini-extracted min_years_experience when present — it's more
        # precise than regex parsing the description inside _experience_score.
        min_exp_from_db = job.get("min_years_experience")  # int or None
        if min_exp_from_db is not None and min_exp_from_db > 0:
            # Override the description-level regex with the structured value
            years_since_grad = current_year - grad_year
            over_by = years_since_grad - min_exp_from_db
            if over_by >= 0:
                # Student meets or exceeds the requirement
                exp_score = min(1.0, 0.80 + 0.05 * over_by)   # e.g. 0yr over → 0.80, 1yr → 0.85
            else:
                # Student is under the requirement
                under_by = abs(over_by)
                exp_score = max(0.05, 0.70 - 0.20 * under_by)  # e.g. 1yr under → 0.50, 3yr → 0.10
            exp_score = round(exp_score, 4)
        else:
            exp_score = _experience_score(title, desc, grad_year, current_year)

        # ── Signal 4: Location compatibility ──────────────────────────────────
        loc_score = _location_score(loc, pref_locs)

        # ── Blend all 4 signals ───────────────────────────────────────────────
        blended = (
            _W_SEMANTIC  * sem_score   +
            _W_SKILLS    * skill_score +
            _W_EXP       * exp_score   +
            _W_LOCATION  * loc_score
        )

        scores.append(round(blended, 4))

    return scores, False


def _rescale_for_display(score: float, used_fallback: bool) -> float:
    """Rescale scores to a display-friendly 0-1 range.

    `used_fallback` is passed explicitly by the caller rather than
    inferred from the score value, so a real cosine score that happens
    to equal 0.20/0.15/0.05 can never be misrouted into the fallback
    display map.
    """
    if used_fallback:
        return _FALLBACK_DISPLAY_MAP.get(round(score, 2), 0.60)

    display_floor, display_ceil = 0.25, 0.75
    display_score = (score - display_floor) / (display_ceil - display_floor)
    return round(max(0.0, min(1.0, display_score)), 4)


def match_jobs_for_student(
    student: dict,
    jobs: list,
    top_n: int = 10,
    threshold: float = MATCH_THRESHOLD,
    embed_fn=get_embeddings_from_hf,
):
    # Route job pool by department and skills to keep matching highly targeted
    dept = (student.get("department") or "cse").lower()
    skills = student.get("skills") or []
    skills_lower = [str(s).lower() for s in skills]

    is_hardware = (
        dept in ["ece", "ee", "electronics", "electrical", "instrumentation"] or
        any(any(kw in sk for kw in ["vlsi", "synthesis", "physical design", "verilog", "embedded"]) for sk in skills_lower)
    )

    if is_hardware:
        target_category = "hardware"
    elif dept in ["data science", "ds", "machine learning", "ml", "ai", "artificial intelligence"]:
        target_category = "data_science"
    elif dept in ["cse", "it", "cs", "computer science"]:
        target_category = "tech"
    elif dept in ["mba", "management", "bba", "business"]:
        target_category = "business"
    elif dept in ["design"]:
        target_category = "design"
    else:
        target_category = None  # fallback to show all

    if target_category:
        jobs = [j for j in jobs if j.get("category") == target_category]

    pref_locs = student.get("preferred_locations") or []
    if pref_locs and not any(loc.lower().strip() == "any" for loc in pref_locs):
        filtered_by_loc = []
        for j in jobs:
            job_loc = j.get("location", "").lower()
            if any(str(loc).lower().strip() in job_loc for loc in pref_locs):
                filtered_by_loc.append(j)
        jobs = filtered_by_loc

    # ── Experience-aware job type filtering ───────────────────────────────────
    # Rules for freshers (effective_exp <= 1 year, covers ALL users with 0-1 yrs
    # experience — whether still in college, recently graduated, or career switching):
    #
    #  FRESHER PATH (effective_exp <= 1):
    #   - Always show: internship jobs
    #   - Always show: early career / graduate programs / new grad roles
    #   - Also show:   full-time jobs that explicitly target their batch/grad year
    #                  (e.g. "2027 batch", "graduating 2027", "pass-out 2027")
    #   - Block:       all other generic full-time roles
    #                  (unless user explicitly chose "fulltime" job type)
    #
    #  EXPERIENCED PATH (effective_exp >= 2):
    #   - Respect job_type preference as-is (no smart filter needed)
    current_year = datetime.now().year
    grad_year = student.get("graduation_year", current_year)
    explicit_job_type = student.get("job_type") or "both"

    if grad_year > current_year:
        filtered = []
        for j in jobs:
            if is_internship(j):
                filtered.append(j)  # always include internships
                continue
            if is_early_career(j):
                filtered.append(j)  # early career / graduate programs always included
                continue
            # Full-time: include only if JD explicitly targets student's batch year
            batch_years = extract_target_batch_years(
                j.get("title", ""), j.get("description") or ""
            )
            if grad_year in batch_years:
                filtered.append(j)
            elif explicit_job_type == "fulltime":
                # User explicitly wants full-time → include generic entry-level too
                filtered.append(j)
        jobs = filtered
    else:
        jobs = filter_by_job_type(jobs, explicit_job_type)

    roles = student.get("preferred_roles") or []

    # NOTE: we no longer hard-filter jobs by matches_role() here. Doing so
    # previously zeroed-out semantically strong matches whose titles just
    # didn't literally contain a keyword (e.g. "Applied Scientist" for an
    # "ml" role preference). Role match is now purely a *scoring bonus*
    # inside _score_jobs, so the embedding similarity gets a fair say.

    if not jobs:
        return []

    student_years = student.get("years_of_experience")  # None if not set (older profiles)
    jobs = _filter_fresher_jobs(jobs, grad_year, current_year, student_years=student_years)
    
    # Filter out ineligible jobs (DCEO, mechanical/electrical, wrong graduation year, etc.)
    eligible_jobs = []
    for j in jobs:
        is_eligible, _ = check_eligibility(
            student,
            j["title"],
            j.get("company", ""),
            j.get("description") or "",
            category=j.get("category"),
            min_years_experience=j.get("min_years_experience")
        )
        if is_eligible:
            eligible_jobs.append(j)
    jobs = eligible_jobs

    if not jobs:
        return []

    scores, used_fallback = _score_jobs(jobs, student, roles, embed_fn)
    ranked = sorted(zip(jobs, scores), key=lambda x: x[1], reverse=True)
    results = [(job, score) for job, score in ranked if score >= threshold][:top_n]
    return [(job, _rescale_for_display(score, used_fallback)) for job, score in results]


def build_match_reason(job: dict, student: dict) -> str:
    """
    Build a short human-readable explanation of why a job matched.

    Priority order:
    1. Matched structured required_skills[] from Gemini extraction (most accurate)
    2. Matched skills found in job description text (fallback)
    3. Role keyword match
    4. Experience level fit
    """
    reasons = []
    student_skills = student.get("skills") or []
    student_norm = {_norm_skill(s) for s in student_skills}

    # ── Priority 1: Match against structured Gemini-extracted required skills ──
    job_required = job.get("required_skills") or []
    if job_required:
        matched_structured = [
            s for s in job_required
            if _norm_skill(s) in student_norm
        ]
        if matched_structured:
            skill_names = ", ".join(matched_structured[:3])
            reasons.append(f"You have {len(matched_structured)}/{len(job_required)} required skills ({skill_names}...)" if len(job_required) > 3 else f"Skills match: {skill_names}")

    # ── Priority 2: Fallback — match against raw JD text ──────────────────────
    if not reasons:
        desc = (job.get("description") or "").lower()
        title_lower = job["title"].lower()
        haystack = title_lower + " " + desc
        matched_text = []
        for s in student_skills:
            s_clean = s.lower().strip()
            if re.search(r"\b" + re.escape(s_clean) + r"\b", haystack):
                matched_text.append(s)
        if matched_text:
            reasons.append(f"Matches your {', '.join(matched_text[:2])} skills")

    # ── Priority 3: Role keyword match ────────────────────────────────────────
    title_lower = job["title"].lower()
    preferred_roles = student.get("preferred_roles") or []
    for role in preferred_roles:
        keywords = keyword_map.get(role, [])
        if any(k in title_lower for k in keywords):
            reasons.append(f"{role.capitalize()} role")
            break

    # ── Priority 4: Experience level fit ─────────────────────────────────────
    grad_year = student.get("graduation_year", datetime.now().year)
    fit = get_graduation_tag(job["title"], grad_year)
    if "Good" in fit:
        reasons.append("Fresher-friendly")

    if not reasons:
        reasons.append("Matches your profile")
    return " · ".join(reasons)
