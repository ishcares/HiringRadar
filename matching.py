import logging
import os
import re
from datetime import datetime
from functools import lru_cache

from embeddings import calculate_cosine_similarity, get_embeddings_from_hf

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tuning knobs — override via env vars without redeploying
# ---------------------------------------------------------------------------
MATCH_THRESHOLD = float(os.getenv("MATCH_THRESHOLD", "0.15"))
ROLE_BONUS      = float(os.getenv("ROLE_BONUS",      "0.15"))
INTERN_BONUS    = float(os.getenv("INTERN_BONUS",    "0.05"))

# ---------------------------------------------------------------------------
# In-process embedding cache — keyed on (title, company) tuple
# Avoids re-embedding the same job titles on every 5-min alert cycle.
# ---------------------------------------------------------------------------
_EMBED_CACHE: dict[tuple, list[float]] = {}


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


def get_experience_tag(title):
    t = title.lower()
    
    # Use word boundary checks to avoid partial matches (like 'intern' inside 'internal')
    if re.search(r"\b(intern|internship|trainee|campus|fresher|new grad)\b", t):
        return "🌱 Fresher / Intern"
    if re.search(r"\b(director|vp|vice president|head of|chief)\b", t):
        return "👑 Director / VP"
    if re.search(r"\b(engineering manager|tech lead|team lead|lead engineer|engineering lead|lead)\b", t):
        return "🏆 Manager / Lead"
    if re.search(r"\b(principal|staff|architect|sde-3|sde iii)\b", t):
        return "⚡ Staff / Principal"
    if re.search(r"\b(senior|sr|sde-2|sde ii)\b", t):
        return "🚀 Senior (5+ yrs)"
    if re.search(r"\b(junior|jr|sde-1|sde i|associate)\b", t):
        return "🔵 Junior (0-2 yrs)"
    if re.search(r"\b(mid-level|mid level|experienced)\b", t):
        return "💼 Mid-level (2-5 yrs)"
    return "💼 Software Engineer"


def get_graduation_tag(title: str, grad_year: int) -> str:
    current_year = datetime.now().year
    years_to_grad = grad_year - current_year
    exp_tag = get_experience_tag(title)

    if years_to_grad <= 0:
        # Passouts: SDE-1 / general Software Engineer roles are excellent fits
        if any(x in exp_tag for x in ["Fresher", "Intern", "Junior", "Software Engineer"]):
            return "✅ Good for you"
        return "⚠️ May need experience"
    else:
        # Current students (2027+): Only Intern/Trainee roles are immediate fits
        if any(x in exp_tag for x in ["Fresher", "Intern"]):
            return "✅ Good for you"
        # SDE-1 / Software Engineer roles get marked as full-time warning
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


def filter_by_job_type(jobs: list, job_type: str) -> list:
    if job_type == "both" or not job_type:
        return jobs
    return [j for j in jobs if (job_type == "internship") == is_internship(j)]


def _expand_title(title: str) -> str:
    """Expand abbreviations in job titles before embedding."""
    words = title.lower().split()
    return " ".join(_ABBREV.get(w.strip(".,/-"), w) for w in words)


def _build_profile_text(student: dict) -> str:
    """Build a rich, descriptive profile string for better embedding signal."""
    roles = student.get("preferred_roles") or []
    skills = student.get("skills") or []
    job_type = student.get("job_type", "both")
    grad_year = student.get("graduation_year", datetime.now().year)
    current_year = datetime.now().year
    years_left = grad_year - current_year

    role_descriptions = {
        "backend": "backend server-side API development",
        "frontend": "frontend UI web development React",
        "ml": "machine learning AI deep learning data science NLP",
        "data": "data engineering analytics SQL pipeline ETL",
        "devops": "DevOps cloud infrastructure Kubernetes SRE",
        "fullstack": "fullstack web development frontend backend",
        "android": "Android mobile Kotlin app development",
        "ios": "iOS Swift mobile app development",
    }
    role_desc = " and ".join(role_descriptions.get(r, r) for r in roles)
    exp_level = "internship or entry-level fresher" if years_left >= 0 else "software engineer"

    return (
        f"I am a {exp_level} looking for {job_type} roles in {role_desc}. "
        f"My technical skills include {', '.join(skills)}. "
        f"I am interested in software engineering and technology positions."
    )


def _filter_fresher_jobs(jobs: list, grad_year: int, current_year: int) -> list:
    """Keep fresher-friendly roles for recent grads; drop clearly senior titles."""
    if grad_year < current_year - 1:
        return jobs

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
        and get_experience_tag(j["title"]) not in non_fresher_tags
    ]
    generic_ok = [
        j for j in jobs
        if get_experience_tag(j["title"]) not in non_fresher_tags
        and j not in fresher_jobs
    ]
    return fresher_jobs if fresher_jobs else generic_ok


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


def is_senior(title: str) -> bool:
    """Check if the job title indicates a senior role."""
    title_lower = title.lower()
    senior_keywords = ["senior", "lead", "staff", "architect", "manager", "ii", "iii", "iv", "v", "principal"]
    return any(f" {k} " in f" {title_lower} " or title_lower.endswith(f" {k}") for k in senior_keywords)


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
        "hr recruiter",
        "operations executive",
        "marketing manager",
        "area collection"
    ]
    return any(k in title_lower for k in non_tech_keywords)


def _score_jobs(jobs: list, student: dict, roles: list, embed_fn) -> list[float]:
    """Return raw cosine scores (+ bonuses) for each job.

    Uses an in-process cache so identical job texts are never re-embedded
    within the same process lifetime.
    """
    current_year = datetime.now().year
    grad_year = student.get("graduation_year", current_year)

    profile_text = _build_profile_text(student)

    # Build job texts, pulling from cache where possible
    job_texts: list[str] = []
    cache_keys: list[tuple] = []
    for j in jobs:
        key = (j["title"], j.get("company", ""))
        text = f"{_expand_title(j['title'])} at {j.get('company', '')} in {j.get('location', '')}".strip()
        job_texts.append(text)
        cache_keys.append(key)

    # Determine which job texts need fresh embeddings
    missing_indices = [i for i, k in enumerate(cache_keys) if k not in _EMBED_CACHE]
    texts_to_embed = [profile_text] + [job_texts[i] for i in missing_indices]

    fresh_embeddings = embed_fn(texts_to_embed)

    if not fresh_embeddings or len(fresh_embeddings) < 2:
        logger.warning(
            "HF embedding API unavailable or returned insufficient data. "
            "Falling back to keyword-only scoring — match percentages will not be shown."
        )
        return _keyword_fallback_scores(jobs, roles, grad_year, current_year)

    profile_emb = fresh_embeddings[0]
    fresh_job_embs = fresh_embeddings[1:]

    # Populate cache with newly fetched embeddings
    for idx, emb in zip(missing_indices, fresh_job_embs):
        _EMBED_CACHE[cache_keys[idx]] = emb

    # Assemble final embedding list from cache
    job_embs = [_EMBED_CACHE[k] for k in cache_keys]

    scores = [calculate_cosine_similarity(profile_emb, j_emb) for j_emb in job_embs]

    for i, job in enumerate(jobs):
        if matches_role(job["title"], roles):
            scores[i] = min(1.0, scores[i] + ROLE_BONUS)
        if grad_year >= current_year - 1 and is_internship(job):
            scores[i] = min(1.0, scores[i] + INTERN_BONUS)
        if is_senior(job["title"]):
            scores[i] = max(0.0, scores[i] - 0.10)
        if is_non_tech(job["title"]):
            scores[i] = 0.0

    return scores


def _rescale_for_display(score: float) -> float:
    """Rescale scores to a display-friendly 0-1 range, handling fallback values."""
    if score == 0.20:
        return 0.90  # 90% Match
    elif score == 0.15:
        return 0.80  # 80% Match
    elif score == 0.05:
        return 0.65  # 65% Match
        
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
    
    # Identify if candidate has hardware/VLSI profile
    is_hardware = (
        dept in ["ece", "ee", "electronics", "electrical", "instrumentation"] or
        any(any(kw in sk for kw in ["vlsi", "synthesis", "physical design", "verilog", "embedded"]) for sk in skills_lower)
    )
    
    # Map student departments to jobs_cache categories
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
        target_category = None # fallback to show all
        
    if target_category:
        # Filter jobs by category, keeping fallback jobs with matching category
        jobs = [j for j in jobs if j.get("category") == target_category]

    # Filter by preferred locations if configured
    pref_locs = student.get("preferred_locations") or []
    if pref_locs and not any(loc.lower().strip() == "any" for loc in pref_locs):
        filtered_by_loc = []
        for j in jobs:
            job_loc = j.get("location", "").lower()
            # If any preferred city matches a substring in the job location, keep it
            if any(str(loc).lower().strip() in job_loc for loc in pref_locs):
                filtered_by_loc.append(j)
        jobs = filtered_by_loc

    jobs = filter_by_job_type(jobs, student.get("job_type", "both"))
    roles = student.get("preferred_roles") or []
    jobs = [j for j in jobs if matches_role(j["title"], roles)]

    if not jobs:
        return []

    current_year = datetime.now().year
    grad_year = student.get("graduation_year", current_year)
    jobs = _filter_fresher_jobs(jobs, grad_year, current_year)
    if not jobs:
        return []

    scores = _score_jobs(jobs, student, roles, embed_fn)
    ranked = sorted(zip(jobs, scores), key=lambda x: x[1], reverse=True)
    results = [(job, score) for job, score in ranked if score >= threshold][:top_n]
    return [(job, _rescale_for_display(score)) for job, score in results]


def build_match_reason(job: dict, student: dict) -> str:
    """Build a short human-readable explanation of why a job matched."""
    reasons = []
    title_lower = job["title"].lower()
    skills = student.get("skills") or []
    matched_skills = [s for s in skills if s.lower() in title_lower]
    if matched_skills:
        reasons.append(f"Matches your {', '.join(matched_skills[:2])} skills")
    roles = student.get("preferred_roles") or []
    for role in roles:
        keywords = keyword_map.get(role, [])
        if any(k in title_lower for k in keywords):
            reasons.append(f"{role.capitalize()} role")
            break
    grad_year = student.get("graduation_year", datetime.now().year)
    fit = get_graduation_tag(job["title"], grad_year)
    if "Good" in fit:
        reasons.append("Fresher-friendly")
    if not reasons:
        reasons.append("Matches your profile")
    return " · ".join(reasons)
