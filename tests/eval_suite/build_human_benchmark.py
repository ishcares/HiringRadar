"""
Independent Human-Labeled Semantic Benchmark Dataset.
Contains ground-truth evidence rankings, relevance tiers (0-3), and classification labels
specifically designed to benchmark Qwen-3 Embedding retrieval and BGE Reranker ranking quality:
- Recall@1, Recall@3, Recall@5
- MRR (Mean Reciprocal Rank)
- nDCG@5 (Normalized Discounted Cumulative Gain)
"""

import os
import json

def create_human_labeled_benchmark():
    items = [
        # --- ISHITA (Java, Spring Boot, Redis, BioLock) ---
        {
            "id": "SEM-001",
            "candidate_id": "ishita_2027",
            "requirement": "Experience with distributed locking mechanisms",
            "category": "SEMANTIC_EVIDENCE",
            "evidence_pool": [
                {"id": "EV-01", "text": "Implemented Redis-based distributed locking to guarantee transaction integrity and replay protection", "relevance": 3},
                {"id": "EV-02", "text": "Engineered biometric authorization service with sub-100ms response time using Java 17 and Spring Boot", "relevance": 1},
                {"id": "EV-03", "text": "Core skills: Java, Python, SQL, PostgreSQL, Redis, Spring Boot", "relevance": 1},
                {"id": "EV-04", "text": "Built Telegram bot using FastAPI with webhook polling", "relevance": 0},
                {"id": "EV-05", "text": "Configured AWS EC2 instances and IAM role policies", "relevance": 0}
            ],
            "ground_truth_top_evidence_id": "EV-01",
            "expected_classification": "MATCHED",
            "notes": "Direct evidence in BioLock bullet #2"
        },
        {
            "id": "SEM-002",
            "candidate_id": "ishita_2027",
            "requirement": "Knowledge of cryptographic signing and asymmetric algorithms",
            "category": "SEMANTIC_EVIDENCE",
            "evidence_pool": [
                {"id": "EV-01", "text": "Enforced OWASP API security standards and ECDSA cryptographic signature verification", "relevance": 3},
                {"id": "EV-02", "text": "Security skills: JWT, OWASP API security, JCA, ECDSA, threat modeling", "relevance": 2},
                {"id": "EV-03", "text": "Implemented Redis-based distributed locking to guarantee transaction integrity", "relevance": 0},
                {"id": "EV-04", "text": "Engineered biometric authorization service using Java 17", "relevance": 1},
                {"id": "EV-05", "text": "Database: PostgreSQL, MySQL, Redis", "relevance": 0}
            ],
            "ground_truth_top_evidence_id": "EV-01",
            "expected_classification": "MATCHED",
            "notes": "ECDSA & JCA cryptographic signatures in BioLock"
        },
        {
            "id": "SEM-003",
            "candidate_id": "ishita_2027",
            "requirement": "Building scalable backend microservices using Java and Spring",
            "category": "DIRECT_MATCH",
            "evidence_pool": [
                {"id": "EV-01", "text": "Engineered biometric authorization service with sub-100ms response time using Java 17 and Spring Boot", "relevance": 3},
                {"id": "EV-02", "text": "Backend skills: Java, Spring Boot, REST APIs, Redis, FastAPI, Concurrency", "relevance": 2},
                {"id": "EV-03", "text": "Enforced OWASP API security standards and ECDSA cryptographic signature verification", "relevance": 1},
                {"id": "EV-04", "text": "Deployed services on AWS EC2 and configured IAM", "relevance": 0},
                {"id": "EV-05", "text": "Built Telegram bot using Python and FastAPI", "relevance": 0}
            ],
            "ground_truth_top_evidence_id": "EV-01",
            "expected_classification": "MATCHED",
            "notes": "BioLock primary tech stack"
        },
        {
            "id": "SEM-004",
            "candidate_id": "ishita_2027",
            "requirement": "High-throughput asynchronous message consumption using Apache Kafka",
            "category": "INSUFFICIENT_EVIDENCE",
            "evidence_pool": [
                {"id": "EV-01", "text": "Implemented Redis-based distributed locking to guarantee transaction integrity", "relevance": 1},
                {"id": "EV-02", "text": "Core skills: Java, Python, SQL, PostgreSQL, Redis, Concurrency", "relevance": 0},
                {"id": "EV-03", "text": "Engineered biometric authorization service with sub-100ms response time using Java 17", "relevance": 0},
                {"id": "EV-04", "text": "Built Telegram bot using FastAPI with webhook polling", "relevance": 0}
            ],
            "ground_truth_top_evidence_id": None,
            "expected_classification": "UNKNOWN",
            "notes": "No Kafka evidence on resume"
        },
        {
            "id": "SEM-005",
            "candidate_id": "ishita_2027",
            "requirement": "Hands-on production programming in Golang",
            "category": "CROSS_STACK_TRAP",
            "evidence_pool": [
                {"id": "EV-01", "text": "Engineered biometric authorization service using Java 17 and Spring Boot", "relevance": 0},
                {"id": "EV-02", "text": "Languages: Java, Python, SQL, Bash", "relevance": 0},
                {"id": "EV-03", "text": "Implemented Redis-based distributed locking for transaction integrity", "relevance": 0},
                {"id": "EV-04", "text": "AWS IAM security and cloud deployment", "relevance": 0}
            ],
            "ground_truth_top_evidence_id": None,
            "expected_classification": "NOT_MATCHED",
            "notes": "Java != Golang -> Must be NOT_MATCHED"
        },
        {
            "id": "SEM-006",
            "candidate_id": "ishita_2027",
            "requirement": "Identity protocol internals: SAML 2.0 and Active Directory LDAP integration",
            "category": "CROSS_STACK_TRAP",
            "evidence_pool": [
                {"id": "EV-01", "text": "Cloud skills: AWS, EC2, S3, AWS IAM, Docker", "relevance": 1},
                {"id": "EV-02", "text": "Security: JWT security, OWASP API security, threat modeling", "relevance": 1},
                {"id": "EV-03", "text": "Implemented Redis-based distributed locking", "relevance": 0},
                {"id": "EV-04", "text": "Engineered biometric authorization service using Java 17", "relevance": 0}
            ],
            "ground_truth_top_evidence_id": None,
            "expected_classification": "NOT_MATCHED",
            "notes": "AWS IAM cloud permissions != Enterprise SAML/Active Directory engine"
        },
        {
            "id": "SEM-007",
            "candidate_id": "ishita_2027",
            "requirement": "Relational database schema design and ACID transaction isolation",
            "category": "SEMANTIC_EVIDENCE",
            "evidence_pool": [
                {"id": "EV-01", "text": "Implemented Redis-based distributed locking to guarantee transaction integrity and replay protection", "relevance": 2},
                {"id": "EV-02", "text": "Databases: PostgreSQL, MySQL, Redis, SQL", "relevance": 3},
                {"id": "EV-03", "text": "Engineered biometric authorization service with sub-100ms response time using Java 17", "relevance": 1},
                {"id": "EV-04", "text": "AWS S3, EC2 cloud deployment", "relevance": 0}
            ],
            "ground_truth_top_evidence_id": "EV-02",
            "expected_classification": "MATCHED",
            "notes": "PostgreSQL & MySQL skills + transaction integrity in BioLock"
        },
        # --- FRONTEND (React, Next.js, TypeScript, Tailwind) ---
        {
            "id": "SEM-008",
            "candidate_id": "frontend_2026",
            "requirement": "Building modern responsive user interfaces with React and Next.js",
            "category": "DIRECT_MATCH",
            "evidence_pool": [
                {"id": "EV-01", "text": "Built high-performance responsive storefront using Next.js 14 and Tailwind CSS", "relevance": 3},
                {"id": "EV-02", "text": "Core skills: JavaScript, TypeScript, React, Next.js, Redux, Tailwind CSS", "relevance": 2},
                {"id": "EV-03", "text": "Optimized Core Web Vitals to achieve 98+ Google Lighthouse score", "relevance": 2},
                {"id": "EV-04", "text": "Tools: Vite, Webpack, Jest, Git, Figma", "relevance": 1}
            ],
            "ground_truth_top_evidence_id": "EV-01",
            "expected_classification": "MATCHED",
            "notes": "ShopWave direct Next.js project"
        },
        {
            "id": "SEM-009",
            "candidate_id": "frontend_2026",
            "requirement": "Web performance optimization, SSR, and Core Web Vitals",
            "category": "SEMANTIC_EVIDENCE",
            "evidence_pool": [
                {"id": "EV-01", "text": "Optimized Core Web Vitals to achieve 98+ Google Lighthouse score", "relevance": 3},
                {"id": "EV-02", "text": "Built high-performance responsive storefront using Next.js 14 and Tailwind CSS with server-side rendering", "relevance": 2},
                {"id": "EV-03", "text": "Frontend skills: React, Next.js, TypeScript, Redux, Tailwind", "relevance": 1},
                {"id": "EV-04", "text": "Tools: Webpack, Vite, Jest, Figma", "relevance": 0}
            ],
            "ground_truth_top_evidence_id": "EV-01",
            "expected_classification": "MATCHED",
            "notes": "BioLock/ShopWave lighthouse optimization"
        },
        {
            "id": "SEM-010",
            "candidate_id": "frontend_2026",
            "requirement": "Deep experience with PyTorch and CUDA kernel programming",
            "category": "CROSS_STACK_TRAP",
            "evidence_pool": [
                {"id": "EV-01", "text": "Built high-performance responsive storefront using Next.js 14", "relevance": 0},
                {"id": "EV-02", "text": "Frontend skills: React, TypeScript, Next.js, Redux", "relevance": 0},
                {"id": "EV-03", "text": "Tools: Vite, Webpack, Jest, Figma", "relevance": 0}
            ],
            "ground_truth_top_evidence_id": None,
            "expected_classification": "NOT_MATCHED",
            "notes": "Frontend != PyTorch/CUDA"
        },
        # --- ML / AI (Python, PyTorch, RAG, HuggingFace) ---
        {
            "id": "SEM-011",
            "candidate_id": "ml_ai_2026",
            "requirement": "Retrieval-Augmented Generation (RAG) and dense vector search pipelines",
            "category": "SEMANTIC_EVIDENCE",
            "evidence_pool": [
                {"id": "EV-01", "text": "Implemented hybrid retrieval RAG pipeline over medical corpus achieving 91% recall", "relevance": 3},
                {"id": "EV-02", "text": "Fine-tuned domain-specific embedding model on clinical note pairs", "relevance": 2},
                {"id": "EV-03", "text": "ML skills: Python, PyTorch, Hugging Face, Sentence-Transformers, Chroma, Pinecone", "relevance": 2},
                {"id": "EV-04", "text": "Tools: Docker, Git, SQL, Pandas, NumPy", "relevance": 0}
            ],
            "ground_truth_top_evidence_id": "EV-01",
            "expected_classification": "MATCHED",
            "notes": "MedRAG core implementation"
        },
        {
            "id": "SEM-012",
            "candidate_id": "ml_ai_2026",
            "requirement": "Fine-tuning transformer embeddings and dense representation models",
            "category": "SEMANTIC_EVIDENCE",
            "evidence_pool": [
                {"id": "EV-01", "text": "Fine-tuned domain-specific embedding model on clinical note pairs", "relevance": 3},
                {"id": "EV-02", "text": "Implemented hybrid retrieval RAG pipeline over medical corpus achieving 91% recall", "relevance": 2},
                {"id": "EV-03", "text": "ML tools: Hugging Face, Sentence-Transformers, PyTorch, ChromaDB", "relevance": 2},
                {"id": "EV-04", "text": "Data manipulation: Pandas, NumPy, Scikit-Learn", "relevance": 0}
            ],
            "ground_truth_top_evidence_id": "EV-01",
            "expected_classification": "MATCHED",
            "notes": "Clinical notes embedding fine-tuning"
        },
        # --- SENIOR GOLANG LEAD (Vikram) ---
        {
            "id": "SEM-013",
            "candidate_id": "senior_golang_lead",
            "requirement": "High-throughput enterprise identity federation and SAML 2.0 / OIDC integrations",
            "category": "DIRECT_MATCH",
            "evidence_pool": [
                {"id": "EV-01", "text": "Implemented SAML 2.0 and OIDC identity provider bridges with Active Directory", "relevance": 3},
                {"id": "EV-02", "text": "Architected enterprise identity federation engine handling 50k req/sec in Golang", "relevance": 3},
                {"id": "EV-03", "text": "Security skills: Active Directory, PKI, X.509, SAML, OIDC, Linux", "relevance": 2},
                {"id": "EV-04", "text": "Infrastructure: Kubernetes, Docker, Terraform, Prometheus", "relevance": 1}
            ],
            "ground_truth_top_evidence_id": "EV-01",
            "expected_classification": "MATCHED",
            "notes": "AuthMesh SAML/OIDC implementation"
        },
        {
            "id": "SEM-014",
            "candidate_id": "senior_golang_lead",
            "requirement": "Distributed systems engineering in Golang with high concurrency",
            "category": "DIRECT_MATCH",
            "evidence_pool": [
                {"id": "EV-01", "text": "Architected enterprise identity federation engine handling 50k req/sec in Golang", "relevance": 3},
                {"id": "EV-02", "text": "Core skills: Golang, Kubernetes, gRPC, Distributed Systems, Kafka", "relevance": 2},
                {"id": "EV-03", "text": "Implemented SAML 2.0 and OIDC identity provider bridges with Active Directory", "relevance": 1},
                {"id": "EV-04", "text": "Terraform and Prometheus monitoring", "relevance": 0}
            ],
            "ground_truth_top_evidence_id": "EV-01",
            "expected_classification": "MATCHED",
            "notes": "Golang 50k req/sec distributed engine"
        },
        {
            "id": "SEM-015",
            "candidate_id": "senior_golang_lead",
            "requirement": "Expertise in iOS mobile development with Swift and SwiftUI",
            "category": "CROSS_STACK_TRAP",
            "evidence_pool": [
                {"id": "EV-01", "text": "Architected enterprise identity federation engine handling 50k req/sec in Golang", "relevance": 0},
                {"id": "EV-02", "text": "Backend skills: Golang, Kubernetes, Docker, Kafka, PostgreSQL", "relevance": 0},
                {"id": "EV-03", "text": "Security: Active Directory, PKI, SAML, OIDC", "relevance": 0}
            ],
            "ground_truth_top_evidence_id": None,
            "expected_classification": "NOT_MATCHED",
            "notes": "Golang backend != iOS Swift"
        }
    ]

    out_path = os.path.join(os.path.dirname(__file__), "human_semantic_benchmark.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)

    print(f"Created {len(items)} human-labeled semantic benchmark test cases -> {out_path}")

if __name__ == "__main__":
    create_human_labeled_benchmark()
