import os
import math
from sentence_transformers import SentenceTransformer

_model = SentenceTransformer("BAAI/bge-small-en-v1.5")


def calculate_cosine_similarity(v1: list, v2: list) -> float:
    """Calculates cosine similarity between two vectors."""
    dot_product = sum(x * y for x, y in zip(v1, v2))
    magnitude1 = math.sqrt(sum(x * x for x in v1))
    magnitude2 = math.sqrt(sum(x * x for x in v2))
    if not magnitude1 or not magnitude2:
        return 0.0
    return dot_product / (magnitude1 * magnitude2)


def get_embeddings_from_hf(texts: list) -> list:
    """Local sentence-transformer embeddings — no network calls, no rate limits,
    no risk of dimension mismatch between providers."""
    if not texts:
        return []
    return _model.encode(texts).tolist()