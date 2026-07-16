"""
ats_screener.py — ATS Skill Gap Analyzer for HiringRadar.

Single responsibility: given a student profile and a job, return:
  - which required skills they have (matched)
  - which required skills they're missing (gap)
  - a 0-1 readiness score
  - actionable learning resources for each missing skill

Used by:
  - bot.py: format_job_card() to show skill gap inline on every alert
  - bot.py: /ats_check command for weekly gap report
  - jd_skill_extractor.py: feeds required_skills into this module
"""

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Learning resources map — skill keyword → free resource
# Covers the 50 most common skills appearing in Indian tech job descriptions.
# ---------------------------------------------------------------------------
_RESOURCES: dict[str, dict] = {
    # Languages
    "python":       {"name": "Python Full Course",              "url": "https://youtu.be/rfscVS0vtbw",          "hours": 8},
    "golang":       {"name": "Go by Example",                   "url": "https://gobyexample.com",              "hours": 6},
    "go":           {"name": "Go by Example",                   "url": "https://gobyexample.com",              "hours": 6},
    "java":         {"name": "Java Full Course — freeCodeCamp", "url": "https://youtu.be/GoXwIVyNvX0",          "hours": 10},
    "typescript":   {"name": "TypeScript Handbook",             "url": "https://www.typescriptlang.org/docs/",  "hours": 5},
    "rust":         {"name": "The Rust Book",                   "url": "https://doc.rust-lang.org/book/",       "hours": 12},
    "scala":        {"name": "Scala Tour",                      "url": "https://docs.scala-lang.org/tour/",     "hours": 8},
    "cpp":          {"name": "C++ Full Course — Bro Code",      "url": "https://youtu.be/-TkoO8Z07hI",          "hours": 10},

    # Frontend
    "react":        {"name": "React Full Course — freeCodeCamp","url": "https://youtu.be/bMknfKXIFA8",          "hours": 12},
    "nextjs":       {"name": "Next.js Docs — Getting Started",  "url": "https://nextjs.org/docs",               "hours": 6},
    "vue":          {"name": "Vue.js Official Guide",            "url": "https://vuejs.org/guide/",              "hours": 8},
    "angular":      {"name": "Angular Tour of Heroes",          "url": "https://angular.dev/tutorials/",        "hours": 8},

    # Backend / Frameworks
    "django":       {"name": "Django Official Tutorial",        "url": "https://docs.djangoproject.com/en/stable/intro/tutorial01/", "hours": 6},
    "fastapi":      {"name": "FastAPI Tutorial",                "url": "https://fastapi.tiangolo.com/tutorial/", "hours": 4},
    "flask":        {"name": "Flask Mega-Tutorial — Miguel",    "url": "https://blog.miguelgrinberg.com/post/the-flask-mega-tutorial-part-i-hello-world", "hours": 8},
    "nodejs":       {"name": "Node.js Crash Course — Traversy", "url": "https://youtu.be/fBNz5xF-Kx4",          "hours": 4},
    "graphql":      {"name": "GraphQL Official Learn",          "url": "https://graphql.org/learn/",            "hours": 4},
    "grpc":         {"name": "gRPC Crash Course — Hussain",     "url": "https://youtu.be/Yw4rkaTc0f8",          "hours": 3},

    # Databases
    "postgresql":   {"name": "PostgreSQL Tutorial",             "url": "https://www.postgresqltutorial.com/",   "hours": 6},
    "mysql":        {"name": "MySQL Crash Course — Traversy",   "url": "https://youtu.be/9ylj9NR0Lcg",          "hours": 4},
    "mongodb":      {"name": "MongoDB in 1 Hour — Web Dev Simplified","url": "https://youtu.be/c2M-rlkkT5o",    "hours": 2},
    "redis":        {"name": "Redis Crash Course — Fireship",   "url": "https://youtu.be/Hbt56gFj998",          "hours": 2},
    "elasticsearch":{"name": "Elasticsearch Getting Started",   "url": "https://www.elastic.co/guide/en/elasticsearch/reference/current/getting-started.html", "hours": 4},
    "cassandra":    {"name": "Apache Cassandra Docs",           "url": "https://cassandra.apache.org/doc/",     "hours": 6},

    # Infrastructure / DevOps
    "docker":       {"name": "Docker Crash Course — TechWorld", "url": "https://youtu.be/3c-iBn73dDE",          "hours": 3},
    "kubernetes":   {"name": "Kubernetes Beginner Course — freeCodeCamp","url": "https://youtu.be/X48VuDVv0do", "hours": 4},
    "k8s":          {"name": "Kubernetes Beginner Course",      "url": "https://youtu.be/X48VuDVv0do",          "hours": 4},
    "terraform":    {"name": "Terraform in 2 Hours — freeCodeCamp","url": "https://youtu.be/SLB_c_ayRMo",       "hours": 3},
    "ansible":      {"name": "Ansible Full Course — Simplilearn","url": "https://youtu.be/EcnqJbxBcM0",         "hours": 4},
    "jenkins":      {"name": "Jenkins Full Course — Edureka",   "url": "https://youtu.be/FX322RVNGj4",          "hours": 4},
    "github actions":{"name":"GitHub Actions Docs",             "url": "https://docs.github.com/en/actions",    "hours": 3},
    "cicd":         {"name": "CI/CD Explained — GitLab",        "url": "https://about.gitlab.com/topics/ci-cd/","hours": 2},

    # Cloud
    "aws":          {"name": "AWS Cloud Practitioner — freeCodeCamp","url": "https://youtu.be/SOTamWNgDKc",     "hours": 12},
    "gcp":          {"name": "Google Cloud Training",           "url": "https://cloud.google.com/training",     "hours": 8},
    "azure":        {"name": "Azure Fundamentals — MS Learn",   "url": "https://learn.microsoft.com/en-us/training/paths/azure-fundamentals/", "hours": 8},

    # Data / ML
    "kafka":        {"name": "Apache Kafka for Beginners — Confluent","url": "https://developer.confluent.io/courses/apache-kafka/events/", "hours": 5},
    "spark":        {"name": "Apache Spark Tutorial — DataBricks","url": "https://learn.databricks.com/",       "hours": 8},
    "airflow":      {"name": "Airflow Tutorial — Astronomer",   "url": "https://docs.astronomer.io/learn/",    "hours": 4},
    "dbt":          {"name": "dbt Learn",                       "url": "https://learn.getdbt.com/",             "hours": 4},
    "pytorch":      {"name": "PyTorch Official Tutorial",       "url": "https://pytorch.org/tutorials/",        "hours": 8},
    "tensorflow":   {"name": "TensorFlow for Beginners",        "url": "https://www.tensorflow.org/tutorials",  "hours": 8},

    # System design / CS fundamentals
    "system design":{"name": "System Design Primer — GitHub",  "url": "https://github.com/donnemartin/system-design-primer", "hours": 10},
    "data structures":{"name":"NeetCode DSA Roadmap",           "url": "https://neetcode.io/roadmap",           "hours": 40},
    "algorithms":   {"name": "NeetCode DSA Roadmap",            "url": "https://neetcode.io/roadmap",           "hours": 40},
    "distributed systems":{"name":"MIT 6.824 Distributed Systems","url":"https://pdos.csail.mit.edu/6.824/",   "hours": 30},

    # Tools
    "git":          {"name": "Git & GitHub Full Course — freeCodeCamp","url": "https://youtu.be/RGOj5yH7evk",  "hours": 3},
    "linux":        {"name": "Linux Command Line Basics",       "url": "https://www.freecodecamp.org/news/the-linux-commands-handbook/", "hours": 4},
}


def _norm(skill: str) -> str:
    """Normalise skill name for fuzzy matching."""
    return re.sub(r"[^a-z0-9]", "", skill.lower())


def _find_resource(skill: str) -> Optional[dict]:
    """Find a learning resource for a skill using fuzzy prefix matching."""
    n = _norm(skill)
    # Exact match first
    if n in _RESOURCES:
        return _RESOURCES[n]
    # Prefix match (e.g. "kubernetes" matches "k8s cluster management")
    for key, res in _RESOURCES.items():
        if n.startswith(key) or key.startswith(n):
            return res
    return None


def analyze_gap(student: dict, job: dict) -> dict:
    """
    Compare student skills against job required_skills.

    Uses resume_skills if present (from PDF upload), else falls back
    to manually-entered skills[]. This makes the system work with
    both onboarded students and resume-uploaded students.

    Args:
        student: row from students table
        job:     row from jobs_cache (must have required_skills JSONB populated)

    Returns:
        {
            "matched":           ["Python", "Django"],
            "missing":           ["Kubernetes", "Redis"],
            "preferred_missing": ["GraphQL"],
            "gap_score":         0.67,        # matched / required
            "ats_ready":         False,        # gap_score >= 0.80
            "resources":         [{skill, name, url, hours}, ...]
            "has_jd_skills":     True,         # False = job has no extracted skills yet
        }
    """
    # Pull required skills from job (populated by jd_skill_extractor background job)
    required_raw = job.get("required_skills") or []
    preferred_raw = job.get("preferred_skills") or []

    if not required_raw:
        return {
            "matched": [], "missing": [], "preferred_missing": [],
            "gap_score": 1.0, "ats_ready": True,
            "resources": [], "has_jd_skills": False,
        }

    # Student's effective skills: resume > manual
    student_skills: list = (
        student.get("resume_skills")
        or student.get("skills")
        or []
    )
    student_norm = {_norm(s) for s in student_skills}

    matched, missing = [], []
    for skill in required_raw:
        if _norm(skill) in student_norm:
            matched.append(skill)
        else:
            missing.append(skill)

    preferred_missing = [s for s in preferred_raw if _norm(s) not in student_norm]

    gap_score = round(len(matched) / len(required_raw), 2) if required_raw else 1.0

    resources = []
    for skill in missing:
        res = _find_resource(skill)
        resources.append({
            "skill":  skill,
            "name":   res["name"] if res else f"Search '{skill} tutorial' on YouTube",
            "url":    res["url"]  if res else f"https://www.youtube.com/results?search_query={skill.replace(' ', '+')}+tutorial",
            "hours":  res["hours"] if res else "?",
        })

    return {
        "matched":           matched,
        "missing":           missing,
        "preferred_missing": preferred_missing,
        "gap_score":         gap_score,
        "ats_ready":         gap_score >= 0.80,
        "resources":         resources,
        "has_jd_skills":     True,
    }


def format_gap_line(gap: dict, max_skills: int = 5) -> str:
    """
    One-line summary for embedding inside a job alert card.

    Example output:
      🎯 Skills: Python ✅ Django ✅ | Kubernetes ❌ Redis ❌ (67% ready)
    """
    if not gap["has_jd_skills"]:
        return ""

    matched_str  = "  ".join(f"{s} ✅" for s in gap["matched"][:max_skills])
    missing_str  = "  ".join(f"{s} ❌" for s in gap["missing"][:3])
    pct          = round(gap["gap_score"] * 100)
    ready_icon   = "✅" if gap["ats_ready"] else "⚠️"

    parts = []
    if matched_str:
        parts.append(matched_str)
    if missing_str:
        parts.append(missing_str)

    skill_str = "  |  ".join(parts) if parts else "No required skills listed"
    return f"🎯 ATS: {skill_str}  ({pct}% ready {ready_icon})"


def format_learn_message(job: dict, gap: dict) -> str:
    """
    Full Telegram message for the 'Learn Missing Skills' button response.

    Example:
      📚 Skill Gap: Razorpay — Backend Engineer

      ❌ Kubernetes (~4 hrs)
         Kubernetes for Beginners — freeCodeCamp
         → youtu.be/X48VuDVv0do

      ❌ Redis (~2 hrs)
         Redis Crash Course — Fireship
         → youtu.be/Hbt56gFj998
    """
    if not gap["missing"]:
        return "✅ You have all the required skills for this role!"

    lines = [
        f"📚 *Skill Gap: {job['company']} — {job['title']}*\n",
        f"You have {len(gap['matched'])}/{len(gap['matched']) + len(gap['missing'])} required skills.\n",
    ]

    total_hours = 0
    for r in gap["resources"]:
        h = r["hours"]
        h_str = f"~{h} hrs" if isinstance(h, int) else "?"
        if isinstance(h, int):
            total_hours += h
        lines.append(f"❌ *{r['skill']}* ({h_str})")
        lines.append(f"   {r['name']}")
        lines.append(f"   🔗 {r['url']}\n")

    if gap["preferred_missing"]:
        lines.append(f"_Nice-to-have gaps: {', '.join(gap['preferred_missing'][:5])}_\n")

    if total_hours:
        lines.append(f"⏱ Total to learn basics: ~{total_hours} hours")

    lines.append("\n💡 _Even surface-level familiarity with these can get you past an ATS filter._")
    return "\n".join(lines)


def aggregate_gaps(gap_list: list[dict]) -> dict:
    """
    Aggregate gap results across multiple jobs to find the most impactful
    missing skills — used by /ats_check weekly report.

    Returns:
        {
            "top_missing": [("Kubernetes", 8), ("Redis", 6), ...],
            "total_jobs": 12,
            "ready_count": 4,   # jobs where gap_score >= 0.80
        }
    """
    from collections import Counter
    counter = Counter()
    total = len(gap_list)
    ready = 0

    for gap in gap_list:
        for skill in gap.get("missing", []):
            counter[skill] += 1
        if gap.get("ats_ready"):
            ready += 1

    return {
        "top_missing": counter.most_common(10),
        "total_jobs":  total,
        "ready_count": ready,
    }
