from __future__ import annotations

import re
from bs4 import BeautifulSoup

WHITESPACE_RE = re.compile(r"\s+")
NON_TEXT_RE = re.compile(r"[^\w\s.,;:!?()'\"/-]")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def clean_text(text: str) -> str:
    if not text:
        return ""

    normalized = NON_TEXT_RE.sub(" ", text)
    normalized = WHITESPACE_RE.sub(" ", normalized).strip()
    return normalized


def extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")

    meta = soup.find("meta", {"name": "description"})
    meta_text = meta["content"].strip() if meta and meta.get("content") else ""

    headings = []
    blacklist = ["subscribe", "browser", "country", "search"]

    for h in soup.find_all(["h1", "h2", "h3"]):
        text = h.get_text().strip()

        if (
            len(text) > 15 and
            len(text) < 120 and
            not any(b in text.lower() for b in blacklist)
        ):
            headings.append(text)

    headings = list(dict.fromkeys(headings))[:10]
    return (meta_text + " " + " ".join(headings)).strip()


def generate_summary(text: str) -> str:
    if not text or len(text) < 50:
        return "No meaningful content available."

    sentences = text.split(".")
    clean = [s.strip() for s in sentences if len(s) > 40]

    return ". ".join(clean[:2]) + "."


def merge_page_texts(page_map: dict[str, str], max_chars: int = 2800) -> str:
    ordered_text = [value for _, value in sorted(page_map.items(), key=lambda x: x[0])]
    merged = clean_text("\n\n".join(ordered_text))

    sentences = [segment.strip() for segment in SENTENCE_SPLIT_RE.split(merged) if segment.strip()]
    seen: set[str] = set()
    kept: list[str] = []

    for sentence in sentences:
        if len(sentence) < 40:
            continue
        signature = _signature(sentence)
        if signature in seen:
            continue
        seen.add(signature)
        kept.append(sentence)
        if len(" ".join(kept)) >= max_chars:
            break

    final_text = WHITESPACE_RE.sub(" ", " ".join(kept)).strip()
    return final_text[:max_chars]


def build_summary(text: str, max_chars: int = 420) -> str:
    if not text:
        return ""
    sentences = [segment.strip() for segment in SENTENCE_SPLIT_RE.split(text) if segment.strip()]
    chosen = " ".join(sentences[:3]).strip()
    chosen = WHITESPACE_RE.sub(" ", chosen)
    return chosen[:max_chars].rstrip(" ,;:") + ("." if chosen else "")


def _signature(text: str) -> str:
    lowered = re.sub(r"[^a-z0-9\s]", "", text.lower())
    lowered = WHITESPACE_RE.sub(" ", lowered).strip()
    return " ".join(lowered.split()[:14])
