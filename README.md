<p align="center">
  <img src="logo.png" width="160" alt="HiringRadar Logo">
</p>

<h1 align="center">HiringRadar 🎯</h1>

<p align="center">
  🤖 <b>Live Demo:</b> <a href="https://t.me/Hiringradar_bot">Try the Telegram Bot</a>
</p>

HiringRadar is an automated, real-time job matching and alert system engineered for college students and freshers. It continuously monitors job boards across **60+ top-tier product companies and hyper-growth startups**, extracts atomic technical requirements, executes a **multi-stage evidence-based semantic matching pipeline**, and delivers high-signal alerts instantly via Telegram.

---

## 🚀 Key Features

*   **Multi-Platform Automated Scrapers:** Continuous scraping engine tracking Greenhouse, Lever, Ashby, Keka Hire, iCIMS, Workday, and custom APIs (Amazon Jobs).
*   **Multi-Stage Semantic Matching Engine:**
    *   **Stage 1 (Retrieval):** Serverless vector embeddings powered by `@cf/qwen/qwen3-embedding-0.6b` on Cloudflare Workers AI.
    *   **Stage 2 (Reranking):** Deep cross-encoder reranking via `@cf/baai/bge-reranker-base` to capture semantic nuances and transferrable skills.
    *   **Stage 3 (Evidence Verification):** Explicit skill ontology checks (`EQUIVALENT`, `COMPONENT_OF`, `RELATED`, `UNRELATED`) to eliminate cross-stack false positives.
*   **Fresher & 2027 Student Guardrails:** 
    *   **Pre-Final Year (2027 Batch) Intelligence:** Direct +30% score boost for verified internships and heavy penalties for senior full-time roles.
    *   **Strict Seniority Gatekeeper:** Filters out mid/senior roles (3+ YoE) before alerts can reach fresher feeds.
    *   Deterministic multi-claim evaluation producing `MATCHED`, `UNKNOWN`, and `NOT_MATCHED` evidence states.
*   **Serverless Database & Connection Pool:** Built on **Neon Serverless PostgreSQL** with pooled connections, automatic reconnection handling, and fallback support for Supabase.
*   **Instant Notifications:** Low-latency Telegram Bot API integration delivering matches and verified evidence summaries directly to candidate chatrooms.

---

## 🎯 Target Companies Tracked

HiringRadar is configured and optimized to fetch, parse, and match listings from high-growth technology companies and startups:

*   **Big Tech & Core Product:** Amazon, Stripe, Rubrik, Visa, Mastercard
*   **High-Growth Startups & FinTech:** Razorpay, PhonePe, CRED, Groww, Paytm, Meesho, and more.

---

## ⚙️ Target SDE Requirement Alignment

HiringRadar's matching engine aligns candidate profiles to the distinct hiring criteria of our target company segments:

### 1. FAANG & Big Tech (Amazon)
*   **The Bar:** Deep focus on Data Structures & Algorithms (DSA), system design foundations, and horizontal scaling.
*   **HiringRadar Alignment:** Flags target graduation batch years (e.g., *2027 grads*), matches core programming paradigms (Python, C++, Java), and identifies containerization and cloud scaling experience (AWS, Docker, Kubernetes).

### 2. High-Bar Fintech & Systems (Stripe, Rubrik, Visa, Mastercard)
*   **The Bar:** Low-latency API design, data resiliency, high-throughput database design, and cloud container orchestration.
*   **HiringRadar Alignment:** Ranks candidates on backend frameworks (FastAPI, Spring Boot, Node.js), query design (PostgreSQL/SQL, indexing), secure authentication (JWT, OAuth), caching layers (Redis), and distributed systems patterns.

---

## 📐 System Architecture

```mermaid
graph TD
    A[Scraper Engine: 60+ Companies] -->|Scrapes JDs| B(Job Hydration & Atomization)
    B -->|Persist & Cache| C[(Neon Serverless PostgreSQL)]
    D[Telegram Bot] -->|Candidate Profile & Resume| E[Candidate Evidence Profiler]
    C --> F[Stage 1: Qwen-3 Embedding Retrieval]
    E --> F
    F --> G[Stage 2: BGE Cross-Encoder Reranker]
    G --> H{Stage 3: Ontology & Eligibility Gate}
    H -->|Cross-Stack Traps Java != Golang| I[Drop / Penalize]
    H -->|Verified Evidence MATCHED| J[Deterministic Scorer]
    J -->|Passes Threshold + 2027 Boost| K[Instant Telegram Job Alert]
```

---

## 🛠️ Technology Stack

`Python` · `FastAPI` · `Cloudflare Workers AI` (`Qwen3-0.6B` + `BGE-Reranker`) · `Neon PostgreSQL` · `Supabase` · `python-telegram-bot` · `BeautifulSoup` · `Docker` · `Gemini API`

---

## ⚡ Real Production Challenges Solved

*   **Cross-Stack Language Trap Elimination:** Vector embeddings alone yielded a high 0.72 cosine similarity between Java and Golang (both being backend languages). Implemented an explicit hierarchical ontology gatekeeper (`ontology.py`) that dropped cross-stack false positives to **0.00%**.
*   **Zero-RAM Serverless ML Footprint:** Replaced heavy local PyTorch dependencies with Cloudflare Workers AI serverless endpoints (`@cf/qwen/qwen3-embedding-0.6b` and `@cf/baai/bge-reranker-base`), keeping host memory consumption under 150 MB with zero cold-start bottlenecks.
*   **Serverless DB Connection Liveness:** Overcame serverless pool idle timeouts (`server closed the connection unexpectedly`) by adding connection liveness pings (`SELECT 1`) and automatic reconnection logic in `neon_client.py`.
*   **Zero-Skill-Extraction Scoring Guard:** Eliminated silent failure modes where unextracted JD requirements produced distorted match scores, introducing neutral baselines and atomic claim validation.
*   **Per-Student Delivery Dedup:** Implemented idempotent notification tracking keyed on `(chat_id, job_url_hash)` to prevent redundant alerts across scrape cycles.

---

## 📈 Status & Ops

*   **Live in Production:** Hosted in containerized environment, actively serving verified SDE matches to **58+ active subscribers**.
*   **Active Features:** Multi-stage evidence verification, 2027 batch internship weighting, and automated diagnostic evaluation suite.
*   *Built solo, end to end — scraping, backend pipelines, ML matching, deployment, and ops.*

---

## 🏃 Setup & Running

### 1. Installation
Clone the repository and install the dependencies:
```bash
git clone https://github.com/ishcares/HiringRadar.git
cd HiringRadar
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment Variables
Create a `.env` file in the root directory:
```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
DATABASE_URL=postgresql://user:password@ep-pooler.neon.tech/neondb?sslmode=require
CLOUDFLARE_WORKER_URL=https://your-worker.workers.dev
GEMINI_API_KEY=your_gemini_api_key
```

### 3. Run Locally
To run the Telegram Bot:
```bash
python bot.py
```

To manually trigger scraping and hydration:
```bash
python -m scratch.trigger_scrape
```

---

## 📁 Project Structure

*   `bot.py` - Telegram bot handler for subscriber management, resume uploading, and feed dispatch.
*   `matching.py` - Multi-stage matching pipeline: vector retrieval, cross-encoder reranking, and evidence scoring.
*   `evidence_engine.py` - 3-state requirement atomization, candidate evidence extractor, and eligibility gates.
*   `ontology.py` - Canonical skill synonym graph and cross-stack trap relationships.
*   `embeddings.py` - Cloudflare Workers AI Qwen-3 embedding and BGE reranker client with tiered fallbacks.
*   `neon_client.py` - Resilient Neon PostgreSQL client with connection pooling and liveness ping.
*   `scraper.py` - Scraper engine for Greenhouse, Lever, Ashby, Keka, iCIMS, Workday, and Amazon.
*   `db.py` - Database operations interface supporting Neon and Supabase.
