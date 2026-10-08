"""
HiringRadar Skill & Domain Ontology.
Provides relationships:
- EQUIVALENT (Postgres == PostgreSQL)
- COMPONENT_OF (Spring Boot -> Java, React -> JavaScript)
- TRANSFERABLE (FastAPI -> Flask, MySQL -> PostgreSQL)
- DOMAIN TAXONOMY (FinTech, Security, Distributed Systems)
"""

# Canonical skill normalization map
SYNONYM_MAP = {
    "py": "python",
    "python3": "python",
    "golang": "go",
    "js": "javascript",
    "ts": "typescript",
    "postgres": "postgresql",
    "psql": "postgresql",
    "pg": "postgresql",
    "mongo": "mongodb",
    "elastic": "elasticsearch",
    "es": "elasticsearch",
    "k8s": "kubernetes",
    "kube": "kubernetes",
    "docker-compose": "docker",
    "reactjs": "react",
    "nextjs": "next.js",
    "spring": "spring boot",
    "springboot": "spring boot",
    "fastapi": "fastapi",
    "express": "express.js",
    "iam": "aws iam",
    "active directory": "active directory / ldap",
    "ad": "active directory / ldap",
    "dsa": "data structures & algorithms",
    "oop": "object-oriented design",
    "ood": "object-oriented design",
}

# Skill Hierarchies & Component Relationships
# Child -> Parent ecosystem
SKILL_PARENTS = {
    "spring boot": "java",
    "spring security": "java",
    "hibernate": "java",
    "maven": "java",
    "gradle": "java",
    "fastapi": "python",
    "django": "python",
    "flask": "python",
    "react": "javascript",
    "next.js": "javascript",
    "express.js": "nodejs",
    "postgresql": "sql",
    "mysql": "sql",
    "sqlite": "sql",
    "aws iam": "aws",
    "ec2": "aws",
    "s3": "aws",
    "dynamodb": "aws",
}

# Domain Taxonomy
DOMAIN_TAXONOMY = {
    "fintech": [
        "payments", "transaction", "banking", "ledger", "fraud", "risk",
        "settlement", "checkout", "trading", "crypto", "blockchain",
        "concurrency", "distributed transactions", "replay protection"
    ],
    "backend_systems": [
        "microservices", "rest apis", "grpc", "distributed systems", "concurrency",
        "multithreading", "caching", "redis", "database", "sql", "message queue",
        "kafka", "rabbitmq", "scalability", "high availability"
    ],
    "security": [
        "authentication", "authorization", "oauth", "oidc", "saml", "pki",
        "x.509", "jwt", "tls", "cryptography", "threat modeling", "owasp",
        "rbac", "iam", "active directory", "identity"
    ],
    "cloud_infrastructure": [
        "docker", "kubernetes", "aws", "gcp", "azure", "ci/cd", "terraform",
        "linux", "bash", "monitoring", "prometheus", "grafana"
    ],
    "data_ai": [
        "machine learning", "deep learning", "nlp", "llm", "embeddings",
        "pytorch", "tensorflow", "scikit-learn", "data pipeline", "etl"
    ]
}


def normalize_skill(skill_str: str) -> str:
    """Normalizes a skill name to its canonical form."""
    if not skill_str:
        return ""
    clean = str(skill_str).lower().strip()
    return SYNONYM_MAP.get(clean, clean)


def get_skill_relation(candidate_skill: str, target_skill: str) -> str:
    """
    Returns relation:
    - 'EQUIVALENT': Exact match or synonym
    - 'SPECIALIZED': Candidate has parent/child (e.g. Java candidate vs Java requirement)
    - 'RELATED': Shares parent ecosystem (e.g. FastAPI and Python)
    - 'UNRELATED': No direct relationship
    """
    c = normalize_skill(candidate_skill)
    t = normalize_skill(target_skill)

    if c == t:
        return "EQUIVALENT"

    if SKILL_PARENTS.get(c) == t:
        return "SPECIALIZED"  # e.g., candidate knows Spring Boot, role requires Java

    if SKILL_PARENTS.get(t) == c:
        return "PARENT"  # e.g., candidate knows Java, role requires Spring Boot

    if SKILL_PARENTS.get(c) and SKILL_PARENTS.get(c) == SKILL_PARENTS.get(t):
        return "RELATED"  # e.g., Postgres & MySQL share SQL

    return "UNRELATED"


def detect_domains(text: str) -> list[str]:
    """Detects active engineering domains from a JD or candidate profile."""
    text_lower = text.lower()
    matched_domains = []
    for domain, keywords in DOMAIN_TAXONOMY.items():
        count = sum(1 for kw in keywords if kw in text_lower)
        if count >= 2:
            matched_domains.append(domain)
    return matched_domains
