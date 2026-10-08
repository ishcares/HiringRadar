import sys
import os
import json
import re

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from ontology import normalize_skill, get_skill_relation
from evidence_engine import atomize_job_requirements
import db

def build_golden_dataset():
    cohorts_path = os.path.join(os.path.dirname(__file__), "candidate_cohorts.json")
    with open(cohorts_path, "r", encoding="utf-8-sig") as f:
        cohorts = json.load(f)

    jobs = db.get_cached_jobs()
    valid_jobs = [j for j in jobs if (j.get("description") or "").strip() and len(j.get("description", "")) > 100]
    print(f"Loaded {len(jobs)} jobs. Rich descriptions: {len(valid_jobs)}")

    eval_items = []
    item_id = 1

    # 1. Ishita (2027 Java/Backend) - 150 items
    cand_ishita = cohorts["ishita_2027"]
    ishita_skills = {normalize_skill(s) for s in cand_ishita["skills"]}

    for job in valid_jobs:
        spec = atomize_job_requirements(job)
        title = spec["title"]
        min_exp = spec["min_years_experience"]
        for r in spec["requirements"]:
            claim = r["claim"]
            orig = r["original"]
            rtype = r["type"]

            if claim in ishita_skills:
                expected = "MATCHED"
                evidence = f"Candidate Skill: {claim}"
                is_trap = False
            elif any(get_skill_relation(cs, claim) in ("SPECIALIZED", "PARENT", "EQUIVALENT") for cs in ishita_skills):
                expected = "MATCHED"
                evidence = f"Ontology Relationship for {claim}"
                is_trap = False
            elif claim in ["golang", "c++", "ruby", "c#", "swift", "php", "rust", "react", "vue", "angular"]:
                expected = "NOT_MATCHED"
                evidence = None
                is_trap = True
            else:
                expected = "UNKNOWN"
                evidence = None
                is_trap = False

            is_senior = any(w in title.lower() for w in ["senior", "lead", "principal", "manager", "staff", "director"]) or min_exp >= 3
            is_intern = any(w in title.lower() for w in ["intern", "internship", "trainee"])
            expected_elig = "FAIL" if is_senior else ("PASS" if is_intern else "CAUTION")

            eval_items.append({
                "id": f"BENCH-{item_id:04d}",
                "job_title": title,
                "company": spec["company"],
                "candidate_id": "ishita_2027",
                "requirement": orig,
                "claim": claim,
                "requirement_type": rtype,
                "seniority_min_exp": min_exp,
                "expected_classification": expected,
                "expected_evidence_ref": evidence,
                "expected_eligibility": expected_elig,
                "is_false_positive_trap": is_trap,
            })
            item_id += 1
            if len([x for x in eval_items if x["candidate_id"] == "ishita_2027"]) >= 150:
                break
        if len([x for x in eval_items if x["candidate_id"] == "ishita_2027"]) >= 150:
            break

    # 2. Vikram (Senior Golang Lead) - 75 items
    cand_vikram = cohorts["senior_golang_lead"]
    vikram_skills = {normalize_skill(s) for s in cand_vikram["skills"]}
    for job in valid_jobs[40:]:
        spec = atomize_job_requirements(job)
        for r in spec["requirements"]:
            claim = r["claim"]
            orig = r["original"]
            expected = "MATCHED" if claim in vikram_skills else ("NOT_MATCHED" if claim in ["react", "vue", "angular", "swift"] else "UNKNOWN")
            eval_items.append({
                "id": f"BENCH-{item_id:04d}",
                "job_title": spec["title"],
                "company": spec["company"],
                "candidate_id": "senior_golang_lead",
                "requirement": orig,
                "claim": claim,
                "requirement_type": r["type"],
                "seniority_min_exp": spec["min_years_experience"],
                "expected_classification": expected,
                "expected_evidence_ref": f"Vikram Skill: {claim}" if expected == "MATCHED" else None,
                "expected_eligibility": "PASS",
                "is_false_positive_trap": False,
            })
            item_id += 1
            if len([x for x in eval_items if x["candidate_id"] == "senior_golang_lead"]) >= 75:
                break
        if len([x for x in eval_items if x["candidate_id"] == "senior_golang_lead"]) >= 75:
            break

    # 3. Alex (Frontend 2026) - 75 items
    cand_alex = cohorts["frontend_2026"]
    alex_skills = {normalize_skill(s) for s in cand_alex["skills"]}
    for job in valid_jobs[80:]:
        spec = atomize_job_requirements(job)
        for r in spec["requirements"]:
            claim = r["claim"]
            orig = r["original"]
            expected = "MATCHED" if claim in alex_skills else ("NOT_MATCHED" if claim in ["java", "golang", "c++", "pytorch"] else "UNKNOWN")
            is_trap = expected == "NOT_MATCHED"
            eval_items.append({
                "id": f"BENCH-{item_id:04d}",
                "job_title": spec["title"],
                "company": spec["company"],
                "candidate_id": "frontend_2026",
                "requirement": orig,
                "claim": claim,
                "requirement_type": r["type"],
                "seniority_min_exp": spec["min_years_experience"],
                "expected_classification": expected,
                "expected_evidence_ref": f"Alex Skill: {claim}" if expected == "MATCHED" else None,
                "expected_eligibility": "PASS" if spec["min_years_experience"] <= 1 else "FAIL",
                "is_false_positive_trap": is_trap,
            })
            item_id += 1
            if len([x for x in eval_items if x["candidate_id"] == "frontend_2026"]) >= 75:
                break
        if len([x for x in eval_items if x["candidate_id"] == "frontend_2026"]) >= 75:
            break

    # 4. Rohan (ML/AI 2026) - 60 items
    cand_rohan = cohorts["ml_ai_2026"]
    rohan_skills = {normalize_skill(s) for s in cand_rohan["skills"]}
    for job in valid_jobs[120:]:
        spec = atomize_job_requirements(job)
        for r in spec["requirements"]:
            claim = r["claim"]
            orig = r["original"]
            expected = "MATCHED" if claim in rohan_skills else ("NOT_MATCHED" if claim in ["golang", "c#", "react"] else "UNKNOWN")
            eval_items.append({
                "id": f"BENCH-{item_id:04d}",
                "job_title": spec["title"],
                "company": spec["company"],
                "candidate_id": "ml_ai_2026",
                "requirement": orig,
                "claim": claim,
                "requirement_type": r["type"],
                "seniority_min_exp": spec["min_years_experience"],
                "expected_classification": expected,
                "expected_evidence_ref": f"Rohan Skill: {claim}" if expected == "MATCHED" else None,
                "expected_eligibility": "PASS" if spec["min_years_experience"] <= 1 else "FAIL",
                "is_false_positive_trap": expected == "NOT_MATCHED",
            })
            item_id += 1
            if len([x for x in eval_items if x["candidate_id"] == "ml_ai_2026"]) >= 60:
                break
        if len([x for x in eval_items if x["candidate_id"] == "ml_ai_2026"]) >= 60:
            break

    out_path = os.path.join(os.path.dirname(__file__), "golden_benchmark_300.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(eval_items, f, indent=2)

    print(f"Generated {len(eval_items)} golden benchmark items -> {out_path}")
    return len(eval_items)

if __name__ == "__main__":
    build_golden_dataset()
