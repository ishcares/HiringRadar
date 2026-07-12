import os
import math
import requests


def calculate_cosine_similarity(v1: list, v2: list) -> float:
    """Calculates cosine similarity between two vectors."""
    dot_product = sum(x * y for x, y in zip(v1, v2))
    magnitude1 = math.sqrt(sum(x * x for x in v1))
    magnitude2 = math.sqrt(sum(x * x for x in v2))
    if not magnitude1 or not magnitude2:
        return 0.0
    return dot_product / (magnitude1 * magnitude2)


def get_embeddings_from_gemini(texts: list) -> list:
    """Gets text embeddings from the Google Gemini API."""
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        return []
    try:
        import google.generativeai as genai
        genai.configure(api_key=gemini_key)
        response = genai.embed_content(
            model="models/text-embedding-004",
            contents=texts,
            task_type="retrieval_document"
        )
        # Gemini returns a list of floats (for single text) or list of lists (for multiple)
        embeddings = response.get('embedding', [])
        # If single text, wrap it in a list to match HF list-of-vectors format
        if len(texts) == 1 and embeddings and isinstance(embeddings[0], float):
            return [embeddings]
        return embeddings
    except Exception as e:
        print(f"Failed to fetch embeddings from Gemini API: {e}")
        return []


def get_embeddings_from_hf(texts: list) -> list:
    """Gets text embeddings from Hugging Face Inference API."""
    # Attempt Gemini first for stability
    gemini_embs = get_embeddings_from_gemini(texts)
    if gemini_embs:
        return gemini_embs

    api_url = "https://api-inference.huggingface.co/models/sentence-transformers/all-MiniLM-L6-v2"
    headers = {}
    hf_token = os.getenv("HF_TOKEN")
    if hf_token:
        headers["Authorization"] = f"Bearer {hf_token}"

    try:
        # Shorter timeout (5s) to prevent bot hanging, but wait for model load if cold
        payload = {
            "inputs": texts,
            "options": {"wait_for_model": True}
        }
        response = requests.post(api_url, headers=headers, json=payload, timeout=5)
        if response.status_code == 200:
            return response.json()
        print(f"HF API error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Failed to fetch embeddings from HF API: {e}")
    return []

