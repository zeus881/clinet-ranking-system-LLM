from __future__ import annotations

import re
from collections import Counter
import os
from typing import Iterable

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine_similarity

try:
    from sentence_transformers import SentenceTransformer
except Exception:
    SentenceTransformer = None

TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")


def generate_embeddings(
    texts: Iterable[str], model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
) -> np.ndarray:
    text_list = [text or "" for text in texts]
    if not text_list:
        return np.empty((0, 0))

    # Primary path from project architecture: sentence-transformers.
    if SentenceTransformer is not None:
        try:
            local_only = os.getenv("EMBEDDING_LOCAL_ONLY", "1") == "1"
            model = SentenceTransformer(model_name, local_files_only=local_only)
            return np.asarray(model.encode(text_list))
        except Exception:
            pass

    # Fallback if model import/load is unavailable.
    return np.asarray([_hash_vector(text) for text in text_list])


def cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    if vec_a.size == 0 or vec_b.size == 0:
        return 0.0
    return float(sklearn_cosine_similarity([vec_a], [vec_b])[0][0])


def _build_token_counter(text: str) -> Counter[str]:
    tokens = [t.lower() for t in TOKEN_RE.findall(text)]
    return Counter(tokens)


def _hash_vector(text: str, size: int = 256) -> np.ndarray:
    vec = np.zeros((size,), dtype=float)
    counter = _build_token_counter(text)
    for token, count in counter.items():
        vec[hash(token) % size] += float(count)
    return vec
