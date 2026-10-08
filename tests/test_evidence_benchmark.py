"""
HiringRadar Multi-Stage Evidence Matching Benchmark & Evaluation Suite.

Tests:
1. False Positive Traps (e.g. Golang / IAM experienced roles for a Java student)
2. True Positive Internships (e.g. Rubrik Winter Intern for a 2027 Java/Python student)
3. Graduation / Eligibility Gating (2027 student vs senior 3+ yrs roles)
4. Unknown Handling (absence from resume -> UNKNOWN, not falsely MATCHED)
5. Ontology Relationships (Component/Parent/Equivalent)
6. Contradiction Detection / Consistency Validation
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from ontology import normalize_skill, get_skill_relation
from evidence_engine import (
    extract_candidate_evidence,
    atomize_job_requirements,
    evaluate_candidate_against_job,
    format_evidence_report,
)


@pytest.fixture
def candidate_ishita():
    return {
        "chat_id": 7401731570,
        "name": "Ishita",
        "department": "cse",
        "graduation_year": 2027,
        "years_of_experience": 0,
        "preferred_roles": ["backend", "software engineer"],
        "preferred_locations": ["Bangalore", "Pune", "Remote"],
        "job_type": "both",
        "skills": [
            "java", "python", "sql", "postgresql", "mysql", "bash",
            "spring boot", "rest apis", "redis", "fastapi", "concurrency",
            "multithreading", "data structures & algorithms", "object-oriented design",
            "distributed systems", "aws", "docker", "git", "linux", "jwt"
        ],
        "projects": [
            {
                "name": "BioLock",
                "technologies": ["Java", "Redis", "AWS", "Spring Boot"],
                "concepts": ["transaction integrity", "authorization", "replay protection", "concurrency"]
            }
        ]
    }


def test_false_positive_trap_golang_iam(candidate_ishita):
    """Verifies that an experienced Golang/IAM role is REJECTED for a Java fresher."""
    cand = extract_candidate_evidence(candidate_ishita)
    job_iam = {
        "title": "Software Engineer - IAM",
        "company": "Rubrik",
        "url": "https://rubrik.com/iam",
        "location": "Pune",
        "min_years_experience": 3,
        "required_skills": ["Golang", "OIDC / OAuth 2.0", "SAML 2.0", "Active Directory", "PKI / Cryptography"],
        "preferred_skills": ["C# / .NET", "Redis"],
        "description": "Seeking Golang developer with practical experience in OIDC, SAML 2.0, Active Directory, PKI, and Windows C# companion app with 3+ years experience."
    }
    spec = atomize_job_requirements(job_iam)
    eval_res = evaluate_candidate_against_job(cand, spec)

    # 1. Eligibility MUST fail due to 3+ years experience requirement
    assert eval_res["eligibility_status"] == "FAIL", f"Expected FAIL, got {eval_res['eligibility_status']}"

    # 2. Final score MUST be low (penalized)
    assert eval_res["final_score"] <= 30, f"Score too high for un-matched role: {eval_res['final_score']}"

    # 3. Golang MUST NOT be matched
    matched_claims = [r["claim"] for r in eval_res["matched_requirements"]]
    assert "golang" not in matched_claims, "Golang should not be matched for Java candidate"


def test_true_positive_winter_internship(candidate_ishita):
    """Verifies that a Winter Intern role matching candidate's stack is prioritized as Top Match."""
    cand = extract_candidate_evidence(candidate_ishita)
    job_intern = {
        "title": "Software Engineer - Winter Intern",
        "company": "Rubrik",
        "url": "https://rubrik.com/intern",
        "location": "Bangalore",
        "min_years_experience": 0,
        "required_skills": ["Java", "Python", "REST APIs", "Data Structures & Algorithms"],
        "preferred_skills": ["Docker", "AWS"],
        "description": "Looking for Winter Interns graduating in 2026/2027 with strong Java or Python, REST APIs, and DSA fundamentals."
    }
    spec = atomize_job_requirements(job_intern)
    eval_res = evaluate_candidate_against_job(cand, spec)

    # 1. Eligibility MUST pass for internship
    assert eval_res["eligibility_status"] == "PASS"

    # 2. Score should be strong (>= 75)
    assert eval_res["final_score"] >= 75, f"Score unexpectedly low: {eval_res['final_score']}"

    # 3. Key skills must be verified in evidence trace
    matched_originals = [r["original"] for r in eval_res["matched_requirements"]]
    assert "Java" in matched_originals
    assert "Python" in matched_originals
    assert "REST APIs" in matched_originals


def test_unknown_handling_absence_from_resume(candidate_ishita):
    """Verifies that an unmentioned technology is classified as UNKNOWN (insufficient evidence)."""
    cand = extract_candidate_evidence(candidate_ishita)
    job_k8s = {
        "title": "Cloud Backend Intern",
        "company": "TechCorp",
        "url": "https://techcorp.com/job",
        "location": "Remote",
        "min_years_experience": 0,
        "required_skills": ["Java", "Kubernetes"],
        "description": "Backend intern working with Java and Kubernetes microservices."
    }
    spec = atomize_job_requirements(job_k8s)
    eval_res = evaluate_candidate_against_job(cand, spec)

    unknown_claims = [r["claim"] for r in eval_res["unknown_requirements"]]
    matched_claims = [r["claim"] for r in eval_res["matched_requirements"]]

    assert "kubernetes" in unknown_claims, "Kubernetes should be UNKNOWN (insufficient evidence)"
    assert "kubernetes" not in matched_claims, "Kubernetes should NOT be falsely matched"
    assert "java" in matched_claims, "Java should be MATCHED"


def test_ontology_relationships():
    """Tests the hierarchical skill ontology relationships."""
    # Equivalent
    assert get_skill_relation("postgres", "postgresql") == "EQUIVALENT"
    assert get_skill_relation("psql", "postgresql") == "EQUIVALENT"

    # Component / Specialized
    assert get_skill_relation("spring boot", "java") == "SPECIALIZED"

    # Parent
    assert get_skill_relation("java", "spring boot") == "PARENT"

    # Related via shared SQL
    assert get_skill_relation("postgresql", "mysql") == "RELATED"

    # Unrelated
    assert get_skill_relation("golang", "java") == "UNRELATED"
    assert get_skill_relation("python", "ruby") == "UNRELATED"


def test_evidence_report_formatting(candidate_ishita):
    """Verifies that the generated evidence report contains no hallucinations and cites real evidence."""
    cand = extract_candidate_evidence(candidate_ishita)
    job = {
        "title": "Software Engineer - Winter Intern",
        "company": "Rubrik",
        "url": "https://rubrik.com/intern",
        "location": "Bangalore",
        "min_years_experience": 0,
        "required_skills": ["Java", "REST APIs"],
        "preferred_skills": ["Redis"],
        "description": "Winter intern for backend distributed systems."
    }
    spec = atomize_job_requirements(job)
    eval_res = evaluate_candidate_against_job(cand, spec)
    report = format_evidence_report(eval_res)

    # Check key sections exist
    assert "REQUIRED REQUIREMENTS" in report
    assert "✓ Java" in report
    assert "ELIGIBILITY: PASS" in report
    assert "EVIDENCE TRACE" in report
    assert "Supported by" in report


def test_contradiction_gate_validator():
    """Verifies that inconsistent evaluation states are caught and normalized."""
    from evidence_engine import validate_and_correct_consistency

    # Dummy contradictory evaluation: FAIL eligibility but high score and 'Apply'
    bad_eval = {
        "final_score": 90,
        "eligibility_status": "FAIL",
        "recommendation": "Apply ✅",
        "recruiter_take": "You are a great match!"
    }
    fixed = validate_and_correct_consistency(bad_eval)

    # Must be corrected
    assert fixed["final_score"] <= 25, "Score should be capped on FAIL"
    assert "Skip" in fixed["recommendation"], "Recommendation should be Skip on FAIL"
    assert "strict experience/seniority" in fixed["recruiter_take"]
