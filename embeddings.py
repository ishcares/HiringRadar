import os
import math
import logging
from collections import Counter
import re
import json
import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cloudflare Workers AI Configuration
# Can use either:
# 1) CLOUDFLARE_WORKER_URL (deployed serverless worker)
# 2) CLOUDFLARE_ACCOUNT_ID + CLOUDFLARE_API_TOKEN (direct REST API)
# ---------------------------------------------------------------------------
_CF_WORKER_URL = os.getenv("CLOUDFLARE_WORKER_URL", "").rstrip("/")
_CF_ACCOUNT = os.getenv("CLOUDFLARE_ACCOUNT_ID")
_CF_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")

# Tier 2: Gemini API Fallback
try:
    import google.generativeai as genai
    _gemini_key = os.getenv("GEMINI_API_KEY")
    if _gemini_key:
        genai.configure(api_key=_gemini_key)
        _HAS_GEMINI = True
    else:
        _HAS_GEMINI = False
except Exception:
    _HAS_GEMINI = False


def calculate_cosine_similarity(v1: list, v2: list) -> float:
    """Calculates cosine similarity between two vectors."""
    if not v1 or not v2:
        return 0.0
    dot_product = sum(x * y for x, y in zip(v1, v2))
    magnitude1 = math.sqrt(sum(x * x for x in v1))
    magnitude2 = math.sqrt(sum(y * y for y in v2))
    if not magnitude1 or not magnitude2:
        return 0.0
    return dot_product / (magnitude1 * magnitude2)


def _text_to_vector(text: str) -> dict:
    """Lightweight pure-python TF-IDF bag-of-words vector representation."""
    words = re.findall(r"\w+", text.lower())
    return Counter(words)


def _get_qwen3_embeddings_cf(texts: list) -> list:
    """Retrieves Qwen3-Embedding-0.6B embeddings via Cloudflare."""
    # Option A: Cloudflare Worker Endpoint
    if _CF_WORKER_URL:
        try:
            res = requests.post(
                f"{_CF_WORKER_URL}/embed",
                json={"texts": texts},
                timeout=8,
            )
            if res.status_code == 200:
                data = res.json()
                embeddings = data.get("embeddings", [])
                if embeddings and isinstance(embeddings, list) and len(embeddings) > 0:
                    return embeddings
        except Exception as e:
            logger.warning("Cloudflare Worker embed endpoint failed: %s", e)

    # Option B: Direct Cloudflare Workers AI REST API
    if _CF_ACCOUNT and _CF_TOKEN:
        url = f"https://api.cloudflare.com/client/v4/accounts/{_CF_ACCOUNT}/ai/run/@cf/qwen/qwen3-embedding-0.6b"
        headers = {"Authorization": f"Bearer {_CF_TOKEN}"}
        try:
            res = requests.post(url, headers=headers, json={"text": texts}, timeout=8)
            if res.status_code == 200:
                data = res.json()
                return data.get("result", {}).get("data", [])
        except Exception as e:
            logger.warning("Cloudflare Qwen3 Workers AI REST call failed: %s", e)

    return []


def get_embeddings_from_hf(texts: list) -> list:
    """
    Zero-Memory Structured Embedding Engine.
    Tier 1: Cloudflare Workers AI (@cf/qwen/qwen3-embedding-0.6b)
    Tier 2: Gemini Embedding API (models/gemini-embedding-001)
    Tier 3: Pure Python TF-IDF Vectorizer
    """
    if not texts:
        return []

    # Tier 1: Cloudflare Qwen3-0.6B (Worker or REST)
    if _CF_WORKER_URL or (_CF_ACCOUNT and _CF_TOKEN):
        cf_vectors = _get_qwen3_embeddings_cf(texts)
        if cf_vectors:
            return cf_vectors

    # Tier 2: Gemini API
    if _HAS_GEMINI:
        try:
            res = genai.embed_content(
                model="models/gemini-embedding-001",
                content=texts
            )
            if "embedding" in res:
                embeddings = res["embedding"]
                if isinstance(embeddings[0], float):
                    return [embeddings]
                return embeddings
        except Exception as e:
            logger.warning("Gemini embedding API fallback triggered: %s", e)

    # Tier 3: Lightweight Pure-Python TF-IDF Projection
    dummy_vectors = []
    for text in texts:
        vec = _text_to_vector(text)
        proj = [0.0] * 384
        for word, count in vec.items():
            idx = abs(hash(word)) % 384
            proj[idx] += count
        mag = math.sqrt(sum(x * x for x in proj)) or 1.0
        dummy_vectors.append([x / mag for x in proj])

    return dummy_vectors


def _rerank_with_gemini(query: str, contexts: list[str]) -> list[float]:
    """Fallback Stage 2 cross-encoder reranking using Gemini."""
    if not _HAS_GEMINI or not contexts:
        return []
    try:
        model = genai.GenerativeModel("gemini-3.5-flash-lite")
        items_text = "\n".join(f"[{i}] {ctx[:300]}" for i, ctx in enumerate(contexts))
        prompt = (
            f"You are a strict technical job matching reranker.\n"
            f"Candidate profile: {query}\n\n"
            f"Rank each job below on relevance to the candidate from 0.00 (irrelevant) to 1.00 (perfect fit):\n"
            f"{items_text}\n\n"
            f"Return ONLY a raw JSON array of float scores corresponding to the index order, e.g. [0.92, 0.45]."
        )
        resp = model.generate_content(prompt)
        text = resp.text.strip()
        text = re.sub(r"^```(?:json)?", "", text)
        text = re.sub(r"```$", "", text).strip()
        scores = json.loads(text)
        if isinstance(scores, list) and len(scores) == len(contexts):
            return [float(max(0.0, min(1.0, s))) for s in scores]
    except Exception as e:
        logger.warning("Gemini reranker fallback failed: %s", e)
    return []


def rerank_contexts(query: str, contexts: list[str]) -> list[float]:
    """
    Stage-2 Cross-Encoder Reranker.
    Tier 1: Cloudflare Workers AI (@cf/baai/bge-reranker-base) via Worker or REST
    Tier 2: Gemini Cross-Encoder Reranker
    """
    if not query or not contexts:
        return []

    # Tier 1 Option A: Cloudflare Worker Endpoint
    if _CF_WORKER_URL:
        try:
            res = requests.post(
                f"{_CF_WORKER_URL}/rerank",
                json={"query": query, "contexts": contexts},
                timeout=8,
            )
            if res.status_code == 200:
                data = res.json()
                results = data.get("results", [])
                if results and isinstance(results, list):
                    scores = [0.0] * len(contexts)
                    for item in results:
                        idx = item.get("index", 0)
                        if 0 <= idx < len(scores):
                            scores[idx] = float(item.get("score", 0.0))
                    return scores
        except Exception as e:
            logger.warning("Cloudflare Worker rerank failed: %s", e)

    # Tier 1 Option B: Direct Cloudflare Workers AI REST API
    if _CF_ACCOUNT and _CF_TOKEN:
        url = f"https://api.cloudflare.com/client/v4/accounts/{_CF_ACCOUNT}/ai/run/@cf/baai/bge-reranker-base"
        headers = {"Authorization": f"Bearer {_CF_TOKEN}"}
        try:
            res = requests.post(
                url,
                headers=headers,
                json={"query": query, "contexts": contexts},
                timeout=8,
            )
            if res.status_code == 200:
                data = res.json()
                results = data.get("result", {}).get("results", [])
                if results and isinstance(results, list):
                    scores = [0.0] * len(contexts)
                    for item in results:
                        idx = item.get("index", 0)
                        if 0 <= idx < len(scores):
                            scores[idx] = float(item.get("score", 0.0))
                    return scores
        except Exception as e:
            logger.warning("Cloudflare Workers AI REST rerank failed: %s", e)

    # Tier 2: Gemini Cross-Encoder Reranker Fallback
    gemini_scores = _rerank_with_gemini(query, contexts)
    if gemini_scores:
        return gemini_scores

    return []
