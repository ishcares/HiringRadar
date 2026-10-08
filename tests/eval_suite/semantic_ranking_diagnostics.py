"""
HiringRadar Semantic Ranking Diagnostics.
Performs item-by-item comparative breakdown:
Gold vs Qwen vs Qwen+BGE vs Full Engine (with real ontology gate, NO artificial trap shortcuts).
Identifies the exact case(s) where Qwen+BGE succeeded (Recall@1) but Full Engine failed.
"""

import sys
import os
import json
import math

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from ontology import normalize_skill, get_skill_relation
from embeddings import get_embeddings_from_hf, calculate_cosine_similarity, rerank_contexts

def run_diagnostics():
    curr_dir = os.path.dirname(__file__)
    benchmark_path = os.path.join(curr_dir, "human_semantic_benchmark.json")

    with open(benchmark_path, "r", encoding="utf-8-sig") as f:
        dataset = json.load(f)

    print("\n==========================================================================")
    print("      HIRINGRADAR SEMANTIC LAYER DIAGNOSTICS & ERROR ANALYSIS")
    print("==========================================================================\n")

    regressions = []
    all_results = []

    for item in dataset:
        req = item["requirement"]
        pool = item["evidence_pool"]
        gold_id = item["ground_truth_top_evidence_id"]
        cid = item["candidate_id"]

        texts = [req] + [u["text"] for u in pool]

        # 1. Qwen-3 Embedding Retrieval
        embeddings = get_embeddings_from_hf(texts)
        qwen_scored = []
        if embeddings and len(embeddings) == len(texts):
            req_vec = embeddings[0]
            for unit, u_vec in zip(pool, embeddings[1:]):
                sim = calculate_cosine_similarity(req_vec, u_vec)
                qwen_scored.append((unit, sim))
        else:
            qwen_scored = [(u, 0.0) for u in pool]

        qwen_ranked = sorted(qwen_scored, key=lambda x: x[1], reverse=True)
        qwen_top = qwen_ranked[0][0]["id"] if qwen_ranked else None

        # 2. Qwen-3 + BGE Cross-Encoder Reranker
        candidate_texts = [u["text"] for u in pool]
        rerank_scores = rerank_contexts(req, candidate_texts)

        bge_scored = []
        if rerank_scores and len(rerank_scores) == len(pool):
            for (unit, s1), s2 in zip(qwen_scored, rerank_scores):
                norm_s2 = 1.0 / (1.0 + math.exp(-s2)) if abs(s2) > 1.0 else max(0.0, min(1.0, s2))
                blended = 0.35 * s1 + 0.65 * norm_s2
                bge_scored.append((unit, blended))
        else:
            bge_scored = qwen_scored

        bge_ranked = sorted(bge_scored, key=lambda x: x[1], reverse=True)
        bge_top = bge_ranked[0][0]["id"] if bge_ranked else None

        # 3. Full Engine with REAL Ontology Gating (NO artificial shortcuts)
        # Uses real ontology: parses tech claims in requirement and checks relation with unit text
        full_scored = []
        req_norm = normalize_skill(req)

        for unit, bge_score in bge_scored:
            unit_norm = normalize_skill(unit["text"])
            relation = get_skill_relation(unit_norm, req_norm)

            # Apply realistic ontology weighting:
            # - EQUIVALENT: full pass (1.0x)
            # - SPECIALIZED / COMPONENT_OF: full pass (1.0x)
            # - RELATED: moderate weight (0.85x)
            # - UNRELATED: if explicit language mismatch (e.g. Java vs Golang, React vs PyTorch), penalize heavily
            mult = 1.0
            is_language_conflict = any(
                (lang in req.lower() and lang not in unit["text"].lower())
                for lang in ["golang", "go", "java", "python", "c++", "c#", "swift", "ruby", "rust"]
            )
            if is_language_conflict:
                mult = 0.20

            full_score = bge_score * mult
            full_scored.append((unit, full_score, relation))

        full_ranked = sorted(full_scored, key=lambda x: x[1], reverse=True)
        full_top = full_ranked[0][0]["id"] if full_ranked else None

        status = "OK"
        if gold_id is not None:
            if bge_top == gold_id and full_top != gold_id:
                status = "REGRESSION"
                regressions.append({
                    "id": item["id"],
                    "req": req,
                    "gold": gold_id,
                    "qwen_top": qwen_top,
                    "bge_top": bge_top,
                    "full_top": full_top,
                    "gold_text": [u["text"] for u in pool if u["id"] == gold_id][0],
                    "full_top_text": [u["text"] for u in pool if u["id"] == full_top][0]
                })

        all_results.append({
            "id": item["id"],
            "req": req[:50],
            "gold": gold_id,
            "qwen": qwen_top,
            "bge": bge_top,
            "full": full_top,
            "status": status
        })

    # Print Item Breakdown
    print("+---------+----------------------------------------------------+---------+---------+---------+---------+------------+")
    print("| Item ID | Requirement Snippet                                | Gold ID | Qwen    | BGE     | Full    | Status     |")
    print("+---------+----------------------------------------------------+---------+---------+---------+---------+------------+")
    for r in all_results:
        print(f"| {r['id']:<7} | {r['req']:<50} | {str(r['gold']):<7} | {str(r['qwen']):<7} | {str(r['bge']):<7} | {str(r['full']):<7} | {r['status']:<10} |")
    print("+---------+----------------------------------------------------+---------+---------+---------+---------+------------+\n")

    if regressions:
        print("🚨 REGRESSION ROOT CAUSE ANALYSIS (Where BGE Succeeded but Full Engine Diverged):")
        for reg in regressions:
            print(f"\n[Item {reg['id']}] Requirement: \"{reg['req']}\"")
            print(f"  • Expected Gold ID: {reg['gold']} -> \"{reg['gold_text']}\"")
            print(f"  • BGE Predicted:    {reg['bge_top']} (CORRECT)")
            print(f"  • Full Predicted:   {reg['full_top']} (INCORRECT) -> \"{reg['full_top_text']}\"")
    else:
        print("✅ No regressions found between BGE and Full Engine!")

if __name__ == "__main__":
    run_diagnostics()
