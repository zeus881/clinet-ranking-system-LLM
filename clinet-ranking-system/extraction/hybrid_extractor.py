from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional

from llm.summarizer import summarize_text

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
PRICING_RE = re.compile(r"(?:[$₹]\s?\d[\d,]*(?:\.\d{1,2})?)")

TECH_KEYWORDS = (
    "ai",
    "cloud",
    "robotics",
    "automation",
    "platform",
    "api",
    "machine learning",
    "data",
    "analytics",
)

PRODUCT_HINTS = ("product", "products", "services", "solutions", "platform")
SPEC_HINTS = ("spec", "feature", "supports", "includes", "version", "model", "capacity")

SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")

# TitleCase sequence followed by a product descriptor or action verb — likely a product name
_PROPER_NOUN_RE = re.compile(
    r'\b([A-Z][A-Za-z0-9][A-Za-z0-9\-]*(?:\s+[A-Z][A-Za-z0-9][A-Za-z0-9\-]*){0,4})'
    r'(?=\s+(?:platform\b|solution\b|software\b|system\b|suite\b|tool\b|product\b|service\b'
    r'|\bapp\b|\bapi\b|\bsdk\b'
    r'|is\b|are\b|enables\b|helps\b|allows\b|provides\b|offers\b|delivers\b|powers\b|automates\b))'
)
# "Our/Meet/Introducing [ProductName]" — no IGNORECASE so [A-Z] stays uppercase-only
_INTRO_RE = re.compile(
    r'(?:[Oo]ur|[Mm]eet|[Ii]ntroducing|[Pp]resenting|[Ll]aunch(?:ing)?)\s+'
    r'([A-Z][A-Za-z0-9][A-Za-z0-9\-]*(?:\s+[A-Z][A-Za-z0-9][A-Za-z0-9\-]*){0,4})',
)

# Leading sentence words that are not part of a product name
_LEADING_WORDS = frozenset([
    "Our", "The", "A", "An", "This", "These", "Those", "We", "They", "It",
    "Meet", "Introducing", "Presenting", "Launching",
])

_SKIP_PREFIXES = frozenset([
    "by continuing", "please read", "these terms", "this agreement", "you agree",
    "we reserve", "copyright", "all rights", "privacy", "last updated", "effective date",
    "cookie", "if you have", "for any questions", "click here", "learn more",
    "about us", "our team", "our company", "senior ", "junior ",
])

_GENERIC_SINGLE = frozenset([
    "platform", "solution", "software", "system", "service", "product", "tool",
    "application", "suite", "framework", "engine", "module", "api", "technology",
    "technologies", "company", "team", "about", "contact", "terms", "privacy",
    "policy", "agreement", "cookie",
])

# Stop-words that end a product name when scanning word-by-word
_NAME_STOP = frozenset([
    "is", "are", "was", "were", "has", "have", "had", "will", "would", "can",
    "enables", "helps", "allows", "provides", "offers", "delivers", "powers",
    "to", "for", "and", "or", "but", "with", "by", "that", "which", "who",
    "in", "on", "at", "from", "of", "the", "a", "an",
])


@dataclass
class ExtractedProfile:
    summary: str
    products: list[str]
    product_specifications: list[str]
    price_range: str | None
    contact_email: str | None
    phone: str | None
    technologies: list[str]
    confidence: dict[str, str]


def extract_profile(clean_text: str, allow_llm_fallback: bool = True) -> ExtractedProfile:
    text = (clean_text or "").strip()

    products = _extract_products(text)
    specs = _extract_specs(text)
    pricing = _extract_pricing(text)
    email = _extract_email(text)
    phone = _extract_phone(text)
    technologies = _extract_tech(text)
    summary = _fast_summary(text)

    confidence = {
        "summary": _confidence_label(summary, low=45, high=140),
        "products": _confidence_label(" ".join(products), low=5, high=20),
        "product_specifications": _confidence_label(" ".join(specs), low=8, high=35),
        "price_range": "high" if pricing else "low",
        "contact_email": "high" if email else "low",
        "phone": "high" if phone else "low",
        "technologies": _confidence_label(" ".join(technologies), low=3, high=14),
    }

    need_llm = allow_llm_fallback and (
        confidence["summary"] == "low" or (not products and not specs)
    )
    if need_llm:
        llm_summary = summarize_text(text, max_chars=320)
        if llm_summary:
            summary = llm_summary
            confidence["summary"] = "medium"

    # Apply confidence filtering: only hide if truly low-confidence
    # Keep products/specs if they exist, even if confidence is low
    if confidence["products"] == "low" and not products:
        products = []
    if confidence["product_specifications"] == "low" and not specs:
        specs = []
    if confidence["technologies"] == "low":
        technologies = []

    return ExtractedProfile(
        summary=summary,
        products=products[:5],
        product_specifications=specs[:5],
        price_range=pricing,
        contact_email=email,
        phone=phone,
        technologies=technologies[:6],
        confidence=confidence,
    )


def _fast_summary(text: str, max_chars: int = 320) -> str:
    if not text:
        return ""
    sentences = [s.strip() for s in SENTENCE_RE.split(text) if len(s.strip()) >= 40]
    summary = " ".join(sentences[:3]).strip()
    return summary[:max_chars].rstrip(" ,;:") + ("." if summary else "")


def _looks_like_product(name: str) -> bool:
    """Return True if `name` looks like a product/brand name rather than a plain adjective phrase."""
    parts = name.split()
    if len(parts) >= 2:
        return True
    # Single word: accept only if it has distinctive capitalization (mixed-case or ALL-CAPS)
    word = parts[0]
    if word.isupper():
        return True
    if word[0].isupper() and any(c.isupper() for c in word[1:]):
        return True
    return False


def _extract_products(text: str) -> list[str]:
    if not text:
        return []

    hits: list[str] = []

    # Strategy 1: regex — TitleCase phrases followed by a product descriptor or action verb
    for match in _PROPER_NOUN_RE.finditer(text):
        words = match.group(1).strip().split()
        while words and words[0] in _LEADING_WORDS:
            words.pop(0)
        name = " ".join(words)
        if 4 <= len(name) <= 60 and name.lower() not in _GENERIC_SINGLE and _looks_like_product(name):
            hits.append(name)

    # Strategy 2: "Our/Meet/Introducing [ProductName]" pattern
    for match in _INTRO_RE.finditer(text):
        name = match.group(1).strip()
        if 4 <= len(name) <= 60 and name.lower() not in _GENERIC_SINGLE and _looks_like_product(name):
            hits.append(name)

    # Strategy 3: sentence fallback — only when regex found nothing at all
    if len(hits) == 0:
        sentences = [s.strip() for s in SENTENCE_RE.split(text) if s.strip()]
        for sentence in sentences:
            lowered = sentence.lower()
            if any(lowered.startswith(p) for p in _SKIP_PREFIXES):
                continue
            if any(token in lowered for token in PRODUCT_HINTS):
                # Scan words left-to-right, stop at the first stop-word
                words = sentence.split()
                phrase_words: list[str] = []
                for w in words[:8]:
                    if w.lower().rstrip(".,;:") in _NAME_STOP:
                        break
                    phrase_words.append(w)
                phrase = " ".join(phrase_words).strip(" -|,;:.!?")
                if 6 <= len(phrase) <= 60 and phrase not in hits:
                    hits.append(phrase)

    return list(dict.fromkeys(hits))[:5]


def _extract_specs(text: str) -> list[str]:
    if not text:
        return []
    lines = [line.strip() for line in re.split(r"[\n•]", text) if line.strip()]
    specs: list[str] = []
    
    for line in lines:
        lowered = line.lower()
        # Check for specification keywords
        if any(token in lowered for token in SPEC_HINTS):
            # Keep lines with spec info
            if 15 <= len(line) <= 130:
                specs.append(line)
    
    # Also look for capability/feature words even if spec hints aren't explicit
    if not specs:
        for line in lines:
            lowered = line.lower()
            if any(word in lowered for word in ["enables", "supports", "provides", "includes", "offers", "features"]):
                if 15 <= len(line) <= 130:
                    specs.append(line)
    
    return list(dict.fromkeys(specs))[:5]


def _extract_pricing(text: str) -> Optional[str]:
    prices = PRICING_RE.findall(text or "")
    if not prices:
        return None
    uniq = list(dict.fromkeys(p.strip() for p in prices if p.strip()))
    if not uniq:
        return None
    return ", ".join(uniq[:3])


def _extract_email(text: str) -> Optional[str]:
    match = EMAIL_RE.search(text or "")
    return match.group(0) if match else None


def _extract_phone(text: str) -> Optional[str]:
    match = PHONE_RE.search(text or "")
    return match.group(0).strip() if match else None


def _extract_tech(text: str) -> list[str]:
    lowered = (text or "").lower()
    found = [token for token in TECH_KEYWORDS if token in lowered]
    return list(dict.fromkeys(found))


def _confidence_label(value: str, low: int, high: int) -> str:
    length = len((value or "").strip())
    if length >= high:
        return "high"
    if length >= low:
        return "medium"
    return "low"


def products_to_json(products: list[str]) -> str | None:
    if not products:
        return None
    payload = [{"name": p, "specifications": ""} for p in products]
    return json.dumps(payload, ensure_ascii=False)
