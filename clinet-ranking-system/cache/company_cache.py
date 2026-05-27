from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

CACHE_DIR = Path("output/cache")
CACHE_TTL_SECONDS = 24 * 60 * 60


def _safe_key(website: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", (website or "").lower()).strip("_")
    return normalized or "unknown"


def _cache_path(website: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{_safe_key(website)}.json"


def load_cached_company(website: str) -> dict[str, Any] | None:
    path = _cache_path(website)
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    cached_at = float(payload.get("cached_at", 0.0) or 0.0)
    if time.time() - cached_at > CACHE_TTL_SECONDS:
        return None

    return payload.get("data") if isinstance(payload.get("data"), dict) else None


def save_cached_company(website: str, data: dict[str, Any]) -> None:
    path = _cache_path(website)
    payload = {
        "cached_at": time.time(),
        "data": data,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
