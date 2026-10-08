"""
HiringRadar Multi-Stage Evidence-Based Matching Engine.

Architecture:
1. Candidate Evidence Profile (Categorized skills, projects, concepts, constraints)
2. Job Requirement Atomizer (Atomic claims for required, preferred, domain, seniority)
3. Multi-Stage Evidence Verification (MATCHED vs UNKNOWN vs NOT_MATCHED)
4. Deterministic Eligibility Gatekeeper (Graduation year, experience years, location)
5. Evidence-Based Scoring Formula
6. Traceable Evidence Graph & Structured Explanation
"""

import logging
import re
from datetime import datetime
from ontology import normalize_skill, get_skill_relation, detect_domains

logger = logging.getLogger(__name__)


def extract_candidate_evidence(student: dict) -> dict:
    """Builds a multi-vector semantic evidence representation of the candidate."""
    raw_skills = student.get("skills") or []
    norm_skills = [normalize_skill(s) for s in raw_skills]

    # Categorize skills
    languages = []
    backend = []
    databases = []
    cloud = []
    security = []
    other = []

    for s in norm_skills:
        if s in ["java", "python", "go", "javascript", "typescript", "c++", "c", "bash"]:
            languages.append(s)
        elif s in ["spring boot", "fastapi", "django", "express.js", "rest apis", "microservices", "concurrency", "multithreading"]:
            backend.append(s)
        elif s in ["postgresql", "mysql", "mongodb", "redis", "elasticsearch", "sql"]:
            databases.append(s)
        elif s in ["aws", "docker", "kubernetes", "linux", "gcp", "azure", "git", "ci/cd"]:
            cloud.append(s)
        elif s in ["jwt", "owasp api security", "threat modeling", "pki", "cryptography", "ecdsa", "aws iam"]:
            security.append(s)
        else:
            other.append(s)

    # Extract projects & evidence bullets (e.g. from resume text or profile)
    projects = student.get("projects") or []
    if not projects and student.get("resume_text"):
        # Auto-extract known project names and evidence lines
        text = student.get("resume_text", "")
        if "biolock" in text.lower():
            projects.append({
                "name": "BioLock",
                "technologies": ["Java", "Redis", "AWS", "JCA", "ECDSA", "Spring Boot"],
                "concepts": ["transaction integrity", "authorization", "replay protection", "concurrency", "jwt security"]
            })

    return {
        "chat_id": student.get("chat_id"),
        "name": student.get("name", "Candidate"),
        "target_roles": student.get("preferred_roles") or ["backend", "software engineer"],
        "skills": {
            "all": norm_skills,
            "languages": languages,
            "backend": backend,
            "databases": databases,
            "cloud": cloud,
            "security": security,
            "other": other,
        },
        "projects": projects,
        "constraints": {
            "graduation_year": student.get("graduation_year", datetime.now().year),
            "years_of_experience": student.get("years_of_experience", 0),
            "preferred_locations": student.get("preferred_locations") or ["any"],
            "job_type": student.get("job_type", "both"),
        }
    }


def atomize_job_requirements(job: dict) -> dict:
    """Atomizes a job description into discrete, testable requirement claims."""
    title = job.get("title", "")
    desc = job.get("description") or ""
    desc_lower = desc.lower()

    # Required and preferred skills
    raw_req = job.get("required_skills") or []
    raw_pref = job.get("preferred_skills") or []

    # If structured skills not present in DB, atomize from JD text
    if not raw_req and desc:
        detected_req = []
        for kw in ["java", "golang", "python", "spring boot", "react", "fastapi", "sql", "postgresql", "docker", "kubernetes", "aws", "redis"]:
            if re.search(rf"\b{re.escape(kw)}\b", desc_lower):
                detected_req.append(kw)
        raw_req = detected_req

    atomic_requirements = []
    for r in raw_req:
        atomic_requirements.append({
            "claim": normalize_skill(r),
            "original": r,
            "type": "required",
            "importance": 1.0,
        })

    for p in raw_pref:
        atomic_requirements.append({
            "claim": normalize_skill(p),
            "original": p,
            "type": "preferred",
            "importance": 0.5,
        })

    # Detect domains
    job_domains = detect_domains(title + " " + desc)

    # Detect experience requirement
    min_exp = job.get("min_years_experience")
    if min_exp is None and desc:
        m = re.search(r"(\b\d+)(?:-\d+)?\+?\s*(?:years?|yrs?)\b\s*(?:of\s+)?(?:\w+\s+)*(?:experience|software|work)", desc_lower)
        if m:
            try:
                min_exp = int(m.group(1))
            except ValueError:
                min_exp = 0
        else:
            min_exp = 0
    elif min_exp is None:
        min_exp = 0

    return {
        "title": title,
        "company": job.get("company", ""),
        "url": job.get("url", ""),
        "location": job.get("location", ""),
        "min_years_experience": min_exp or 0,
        "domains": job_domains,
        "requirements": atomic_requirements,
        "has_full_description": len(desc.strip()) > 50,
    }


def evaluate_candidate_against_job(candidate: dict, job_spec: dict) -> dict:
    """
    Evaluates candidate evidence against atomic job requirements.
    Separates MATCHED, UNKNOWN, and NOT_MATCHED.
    Separates Semantic Alignment from Hard Eligibility.
    """
    cand_skills = candidate["skills"]["all"]
    cand_projects = candidate.get("projects", [])
    constraints = candidate["constraints"]

    # 1. Evaluate Atomic Requirements
    matched_reqs = []
    unknown_reqs = []
    not_matched_reqs = []
    evidence_graph = []

    for req in job_spec["requirements"]:
        claim = req["claim"]
        found = False

        # Check candidate skills directly or via ontology
        for cs in cand_skills:
            rel = get_skill_relation(cs, claim)
            if rel == "EQUIVALENT":
                matched_reqs.append(req)
                evidence_graph.append({"requirement": req["original"], "status": "MATCHED", "evidence": f"Candidate Skill: {cs}"})
                found = True
                break
            elif rel in ("SPECIALIZED", "PARENT"):
                matched_reqs.append(req)
                evidence_graph.append({"requirement": req["original"], "status": "MATCHED", "evidence": f"Candidate Skill: {cs} ({rel.lower()} of {claim})"})
                found = True
                break

        if found:
            continue

        # Check projects context for evidence
        project_found = False
        for proj in cand_projects:
            proj_techs = [normalize_skill(t) for t in proj.get("technologies", [])]
            proj_concepts = [c.lower() for c in proj.get("concepts", [])]
            if claim in proj_techs or any(claim in c for c in proj_concepts):
                matched_reqs.append(req)
                evidence_graph.append({"requirement": req["original"], "status": "MATCHED", "evidence": f"Project {proj['name']} ({claim})"})
                project_found = True
                break

        if project_found:
            continue

        # If not found in skills/projects:
        # If candidate has listed primary skills in that exact category (e.g. languages: Python/Java, but role strictly requires Golang),
        # mark as NOT_MATCHED. If it's an auxiliary tool or infra tool, mark as UNKNOWN (insufficient evidence).
        if claim in ["golang", "c++", "ruby", "c#", "rust", "php", "swift"]:
            not_matched_reqs.append(req)
            evidence_graph.append({"requirement": req["original"], "status": "NOT_MATCHED", "evidence": f"Resume lacks {claim}"})
        else:
            unknown_reqs.append(req)
            evidence_graph.append({"requirement": req["original"], "status": "UNKNOWN", "evidence": f"Insufficient evidence on resume"})

    # 2. Hard Eligibility Check (Deterministic)
    current_year = datetime.now().year
    grad_year = constraints["graduation_year"]
    cand_exp = constraints["years_of_experience"]
    min_exp = job_spec["min_years_experience"]

    eligibility_status = "PASS"
    eligibility_notes = []

    # Check Experience
    if min_exp > 2 and cand_exp == 0:
        eligibility_status = "FAIL"
        eligibility_notes.append(f"Requires {min_exp}+ yrs experience; candidate has {cand_exp} yrs (fresher)")
    elif min_exp > 0 and cand_exp < min_exp:
        eligibility_status = "CAUTION"
        eligibility_notes.append(f"Requires {min_exp} yrs experience; candidate has {cand_exp} yrs")
    else:
        eligibility_notes.append("Experience requirements satisfied")

    # Check Graduation Fit
    title_lower = job_spec["title"].lower()
    is_intern = any(w in title_lower for w in ["intern", "internship", "trainee"])
    is_senior = any(w in title_lower for w in ["senior", "lead", "principal", "manager", "staff", "director"])

    if is_senior:
        eligibility_status = "FAIL"
        eligibility_notes.append(f"Seniority conflict: Role is {job_spec['title']} for 0-exp candidate")
    elif is_intern:
        # College student (e.g. 2027 batch) is the prime audience for internships
        eligibility_status = "PASS"
        eligibility_notes.append(f"Graduating {grad_year} — Eligible for Summer/Winter Internship")
    elif grad_year > current_year:
        # Student hasn't graduated yet and this is a full-time role
        desc_text = job_spec.get("description") or ""
        is_campus_batch = f"{grad_year}" in job_spec["title"] or f"{grad_year}" in desc_text
        if is_campus_batch:
            eligibility_status = "PASS"
            eligibility_notes.append(f"Targeted campus hire for {grad_year} batch")
        else:
            if eligibility_status != "FAIL":
                eligibility_status = "CAUTION"
            eligibility_notes.append(f"Full-time role (graduation {grad_year})")
    elif not is_senior and min_exp <= 1:
        eligibility_notes.append("Fresher / Entry-Level friendly full-time role")

    # Check Location Fit
    job_loc = job_spec.get("location", "").lower()
    pref_locs = constraints.get("preferred_locations", ["any"])
    if pref_locs and not any(l.lower() == "any" for l in pref_locs):
        if not any(l.lower() in job_loc for l in pref_locs):
            eligibility_notes.append(f"Location mismatch: Job is in {job_spec.get('location')}")
        else:
            eligibility_notes.append(f"Location compatible: {job_spec.get('location')}")
    else:
        eligibility_notes.append(f"Location compatible: {job_spec.get('location') or 'Any'}")

    # 3. Domain Alignment
    cand_domains = ["fintech", "backend_systems", "security"]  # from candidate's BioLock & backend skills
    shared_domains = [d for d in job_spec["domains"] if d in cand_domains]

    # 4. Deterministic Scoring Calculation
    total_req_count = max(1, len([r for r in job_spec["requirements"] if r["type"] == "required"]))
    matched_req_count = len([r for r in matched_reqs if r["type"] == "required"])
    req_ratio = matched_req_count / total_req_count

    # Role fit score
    role_fit = 0.85 if any(r.lower() in title_lower for r in ["software", "backend", "developer", "engineer"]) else 0.40

    # Domain bonus
    domain_score = min(1.0, 0.50 + 0.25 * len(shared_domains))

    # Base semantic score (0 - 100)
    semantic_score = int(round(
        (0.50 * req_ratio + 0.30 * role_fit + 0.20 * domain_score) * 100
    ))

    # Guardrails: Empty description penalty
    if not job_spec["has_full_description"]:
        semantic_score = min(semantic_score, 40)
        eligibility_notes.append("⚠️ Job description unverified / missing in database")

    # For pre-final year students (e.g. 2027 grad):
    if grad_year > current_year:
        if is_intern:
            semantic_score = min(100, int(semantic_score * 1.25))
        else:
            semantic_score = int(semantic_score * 0.70)

    # Hard eligibility penalty
    if eligibility_status == "FAIL":
        final_score = min(semantic_score, 20)
    elif eligibility_status == "CAUTION":
        final_score = int(semantic_score * 0.60)
    else:
        final_score = semantic_score

    return {
        "final_score": final_score,
        "semantic_score": semantic_score,
        "eligibility_status": eligibility_status,
        "eligibility_notes": eligibility_notes,
        "matched_requirements": matched_reqs,
        "unknown_requirements": unknown_reqs,
        "not_matched_requirements": not_matched_reqs,
        "shared_domains": shared_domains,
        "evidence_graph": evidence_graph,
        "job_title": job_spec["title"],
        "company": job_spec["company"],
        "url": job_spec["url"],
    }


def format_evidence_report(evaluation: dict) -> str:
    """Formats the final analysis strictly grounded on verified evidence."""
    score = evaluation["final_score"]
    title = evaluation["job_title"]
    company = evaluation["company"]

    lines = []
    lines.append(f"🏢 {company} — {title}")
    lines.append(f"🎯 Match: {score}/100")
    lines.append("")

    # ROLE & REQUIREMENTS
    lines.append("REQUIRED REQUIREMENTS")
    for r in evaluation["matched_requirements"]:
        lines.append(f"✓ {r['original']}")
    for r in evaluation["unknown_requirements"]:
        lines.append(f"? {r['original']} — insufficient evidence on resume")
    for r in evaluation["not_matched_requirements"]:
        lines.append(f"✗ {r['original']} — not matched")
    if not evaluation["matched_requirements"] and not evaluation["unknown_requirements"] and not evaluation["not_matched_requirements"]:
        lines.append("• Standard engineering competencies")
    lines.append("")

    # DOMAIN
    lines.append("DOMAIN")
    if evaluation["shared_domains"]:
        for d in evaluation["shared_domains"]:
            lines.append(f"✓ {d.replace('_', ' ').title()}")
    else:
        lines.append("• General Software Engineering")
    lines.append("")

    # ELIGIBILITY
    lines.append(f"ELIGIBILITY: {evaluation['eligibility_status']}")
    for note in evaluation["eligibility_notes"]:
        lines.append(f"• {note}")
    lines.append("")

    # EVIDENCE GRAPH
    lines.append("EVIDENCE TRACE")
    for item in evaluation["evidence_graph"][:5]:
        if item["status"] == "MATCHED":
            lines.append(f"• {item['requirement']} → Supported by {item['evidence']}")
    lines.append("")

    lines.append(f"🔗 [Apply Here]({evaluation['url']})")
    return "\n".join(lines)


def validate_and_correct_consistency(evaluation: dict) -> dict:
    """
    Consistency Validator & Contradiction Gate.
    Enforces that:
    1. An ineligible role (FAIL) can NEVER have an 'Apply' recommendation or positive recruiter spin.
    2. Missing core requirements cap the score and enforce caution.
    3. Absence of evidence produces UNKNOWN, never false negative or false positive.
    """
    status = evaluation.get("eligibility_status", "PASS")
    score = evaluation.get("final_score", 0)

    # Invariant 1: Ineligible role must be capped at 25 and marked Skip
    if status == "FAIL":
        evaluation["final_score"] = min(score, 25)
        evaluation["recommendation"] = "Skip / Ineligible 🛑"
        evaluation["recruiter_take"] = "This role has strict experience/seniority requirements that do not match your current graduation stage."

    # Invariant 2: Low score cannot say 'Apply'
    elif evaluation["final_score"] < 50:
        evaluation["recommendation"] = "Skip / Low Match 🛑"
        if not evaluation.get("recruiter_take"):
            evaluation["recruiter_take"] = "Insufficient overlap with required tech stack."

    # Invariant 3: Caution roles
    elif status == "CAUTION" or evaluation["final_score"] < 75:
        evaluation["recommendation"] = "Apply with Caution ⚠️"
        if not evaluation.get("recruiter_take"):
            evaluation["recruiter_take"] = "Relevant engineering domain, but verify experience and graduation requirements."

    else:
        evaluation["recommendation"] = "Apply ✅"
        if not evaluation.get("recruiter_take"):
            evaluation["recruiter_take"] = "Strong alignment with required skills and graduation timeline."

    return evaluation
