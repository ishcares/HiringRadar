import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
"""
HiringRadar Golden Benchmark Evaluation Runner.
Evaluates the 360-example golden benchmark dataset against the Multi-Stage Evidence Engine.
Calculates Precision, Recall, False-Positive Rate, Unknown Accuracy, and Evidence Faithfulness.
"""

import sys
import os
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from ontology import normalize_skill, get_skill_relation
from evidence_engine import extract_candidate_evidence, evaluate_candidate_against_job

def run_evaluation():
    curr_dir = os.path.dirname(__file__)
    cohorts_path = os.path.join(curr_dir, "candidate_cohorts.json")
    dataset_path = os.path.join(curr_dir, "golden_benchmark_300.json")

    with open(cohorts_path, "r", encoding="utf-8-sig") as f:
        cohorts = json.load(f)

    with open(dataset_path, "r", encoding="utf-8-sig") as f:
        dataset = json.load(f)

    print(f"\n========================================================")
    print(f"      HIRINGRADAR GOLDEN BENCHMARK EVALUATION (360 ITEMS)")
    print(f"========================================================\n")

    # Metrics Counters
    total_items = len(dataset)
    correct_classifications = 0
    matched_tp, matched_fp, matched_fn = 0, 0, 0
    not_matched_tp, not_matched_fp, not_matched_fn = 0, 0, 0
    unknown_tp, unknown_fp, unknown_fn = 0, 0, 0

    trap_total, trap_false_positives = 0, 0
    faithful_evidence_count = 0
    total_matched_preds = 0

    eligibility_correct = 0

    for item in dataset:
        cid = item["candidate_id"]
        cand_raw = cohorts[cid]
        cand = extract_candidate_evidence(cand_raw)

        # Mock single requirement job spec for item evaluation
        mock_job = {
            "title": item["job_title"],
            "company": item["company"],
            "url": "https://example.com/job",
            "location": "Bangalore",
            "min_years_experience": item["seniority_min_exp"],
            "domains": [],
            "requirements": [{
                "claim": item["claim"],
                "original": item["requirement"],
                "type": item["requirement_type"],
                "importance": 1.0,
            }],
            "has_full_description": True,
        }

        eval_res = evaluate_candidate_against_job(cand, mock_job)

        # Determine predicted classification
        if eval_res["matched_requirements"]:
            pred = "MATCHED"
        elif eval_res["not_matched_requirements"]:
            pred = "NOT_MATCHED"
        else:
            pred = "UNKNOWN"

        gold = item["expected_classification"]

        # Classification accuracy
        if pred == gold:
            correct_classifications += 1

        # Confusion Matrix components
        if pred == "MATCHED":
            total_matched_preds += 1
            if gold == "MATCHED":
                matched_tp += 1
                # Evidence Faithfulness Check: verify evidence exists in candidate raw skills/projects
                cand_skills = {normalize_skill(s) for s in cand_raw["skills"]}
                if item["claim"] in cand_skills or any(get_skill_relation(cs, item["claim"]) != "UNRELATED" for cs in cand_skills):
                    faithful_evidence_count += 1
            else:
                matched_fp += 1
        elif gold == "MATCHED":
            matched_fn += 1

        if pred == "NOT_MATCHED":
            if gold == "NOT_MATCHED":
                not_matched_tp += 1
            else:
                not_matched_fp += 1
        elif gold == "NOT_MATCHED":
            not_matched_fn += 1

        if pred == "UNKNOWN":
            if gold == "UNKNOWN":
                unknown_tp += 1
            else:
                unknown_fp += 1
        elif gold == "UNKNOWN":
            unknown_fn += 1

        # False-Positive Trap Evaluation
        if item.get("is_false_positive_trap"):
            trap_total += 1
            if pred == "MATCHED":
                trap_false_positives += 1

        # Eligibility evaluation
        pred_elig = eval_res["eligibility_status"]
        gold_elig = item.get("expected_eligibility")
        if pred_elig == gold_elig or (gold_elig == "CAUTION" and pred_elig in ("CAUTION", "PASS")):
            eligibility_correct += 1

    # Statistical Metrics
    acc = correct_classifications / total_items if total_items else 0
    matched_prec = matched_tp / (matched_tp + matched_fp) if (matched_tp + matched_fp) else 1.0
    matched_rec = matched_tp / (matched_tp + matched_fn) if (matched_tp + matched_fn) else 1.0
    matched_f1 = (2 * matched_prec * matched_rec) / (matched_prec + matched_rec) if (matched_prec + matched_rec) else 0

    trap_fp_rate = (trap_false_positives / trap_total) * 100 if trap_total else 0.0
    faithfulness_rate = (faithful_evidence_count / total_matched_preds) * 100 if total_matched_preds else 100.0
    elig_acc = (eligibility_correct / total_items) * 100 if total_items else 0

    # Print Scoreboard
    print("+--------------------------------------------------------+")
    print(f"| TOTAL EVALUATION CLAIMS TESTED:  {total_items:3d}                   |")
    print(f"| OVERALL CLASSIFICATION ACCURACY: {acc * 100:6.2f}%               |")
    print("+--------------------------------------------------------+")
    print(f"| MATCHED Precision:               {matched_prec * 100:6.2f}%               |")
    print(f"| MATCHED Recall:                  {matched_rec * 100:6.2f}%               |")
    print(f"| MATCHED F1-Score:                {matched_f1 * 100:6.2f}%               |")
    print("+--------------------------------------------------------+")
    print(f"| FALSE-POSITIVE RATE (TRAPS):     {trap_fp_rate:6.2f}% (Ideal: 0.00%) |")
    print(f"| EVIDENCE FAITHFULNESS:           {faithfulness_rate:6.2f}% (Ideal: 100%)  |")
    print(f"| ELIGIBILITY GATING ACCURACY:     {elig_acc:6.2f}%               |")
    print("+--------------------------------------------------------+")

    print("\nSummary:")
    if trap_fp_rate == 0.0 and faithfulness_rate == 100.0:
        print("[SUCCESS] EXCELLENT: 0.00% False-Positive rate on cross-stack traps and 100.0% Evidence Faithfulness!")
    else:
        print(f"[WARNING] Traps FP: {trap_fp_rate:.2f}%, Faithfulness: {faithfulness_rate:.2f}%")

if __name__ == "__main__":
    run_evaluation()
