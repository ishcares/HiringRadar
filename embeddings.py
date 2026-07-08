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


def get_embeddings_from_hf(texts: list) -> list:
    """Gets text embeddings from Hugging Face Inference API."""
    api_url = "https://api-inference.huggingface.co/models/sentence-transformers/all-MiniLM-L6-v2"
    headers = {}
    hf_token = os.getenv("HF_TOKEN")
    if hf_token:
        headers["Authorization"] = f"Bearer {hf_token}"

    try:
        response = requests.post(api_url, headers=headers, json={"inputs": texts}, timeout=15)
        if response.status_code == 200:
            return response.json()
        print(f"HF API error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Failed to fetch embeddings from HF API: {e}")
    return []
