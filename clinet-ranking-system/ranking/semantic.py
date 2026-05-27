from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

import numpy as np

from embedding.embeddings import cosine_similarity, generate_embeddings

CACHE_PATH = Path("output/cache/embedding_cache.json")


def _text_key(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()


def _load_cache() -> dict[str, list[float]]:
    if not CACHE_PATH.exists():
        return {}
    try:
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    out: dict[str, list[float]] = {}
    for key, value in payload.items():
        if isinstance(key, str) and isinstance(value, list):
            out[key] = [float(x) for x in value]
    return out


def _save_cache(cache: dict[str, list[float]]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")


def get_embeddings_for_texts(texts: Iterable[str], max_chars: int = 1200) -> np.ndarray:
    text_list = [(text or "").strip()[:max_chars] for text in texts]
    if not text_list:
        return np.empty((0, 0), dtype=float)

    cache = _load_cache()
    missing_texts: list[str] = []
    missing_keys: list[str] = []

    vectors: list[np.ndarray | None] = []
    for text in text_list:
        key = _text_key(text)
        cached = cache.get(key)
        if cached:
            vectors.append(np.asarray(cached, dtype=float))
        else:
            vectors.append(None)
            missing_texts.append(text)
            missing_keys.append(key)

    if missing_texts:
        generated = generate_embeddings(missing_texts)
        for key, vec in zip(missing_keys, generated):
            cache[key] = vec.tolist()
        _save_cache(cache)

        gen_iter = iter(generated)
        for index, vec in enumerate(vectors):
            if vec is None:
                vectors[index] = np.asarray(next(gen_iter), dtype=float)

    return np.asarray([v for v in vectors if v is not None], dtype=float)


def semantic_scores(company_texts: list[str], query: str) -> list[float]:
    if not company_texts:
        return []
    query_text = (query or "").strip()
    if not query_text:
        return [0.0 for _ in company_texts]

    vectors = get_embeddings_for_texts(company_texts + [query_text])
    if len(vectors) < 2:
        return [0.0 for _ in company_texts]

    query_vec = vectors[-1]
    scores: list[float] = []
    for company_vec in vectors[:-1]:
        score = cosine_similarity(company_vec, query_vec)
        scores.append(round(max(0.0, min(1.0, score)) * 100.0, 2))
    return scores
