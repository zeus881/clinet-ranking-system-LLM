from __future__ import annotations

import json
import os
import re
from typing import Dict, Optional

import requests


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
PRODUCT_NAME_RE = re.compile(r"\b([A-Z][A-Za-z0-9&+\-]*(?:\s+[A-Z][A-Za-z0-9&+\-]*)*)\b")
SPEC_HINTS = (
    "support",
    "supports",
    "include",
    "includes",
    "feature",
    "features",
    "automation",
    "manage",
    "manages",
    "provide",
    "provides",
    "deliver",
    "delivers",
    "offer",
    "offers",
    "enable",
    "enables",
)
JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)
LLM_API = "http://localhost:11434/api/generate"
LLM_MODEL = "llama3.2"
LLM_SECTION_KEYWORDS = ("product", "products", "solution", "solutions", "service", "services", "technology", "technologies")
OFFLINE_MODE_ENV = "CRS_OFFLINE_MODE"


def extract_structured_company_info(
    company_name: str, website: str, cleaned_text: str
) -> Dict[str, Optional[str]]:
    text = cleaned_text or ""
    lowered = text.lower()
    if not text:
        print(f"[EXTRACTOR] Empty cleaned_text for {company_name} ({website})")

    llm_text = _extract_llm_candidate_text(text)
    llm_structured = _extract_with_llm_strict(llm_text)

    industry = llm_structured["industry"] or _infer_industry(lowered)
    cleaned_extraction_text = _clean_extraction_text(llm_text or text)
    structured_products = _extract_structured_products(cleaned_extraction_text)
    if not structured_products:
        fallback_products = _join_non_empty(llm_structured["products"]) or _infer_products(text)
        structured_products = _fallback_products_to_structured(fallback_products)
    structured_products = _finalize_structured_products(structured_products)

    products = _format_structured_products_json(structured_products)
    technologies = _join_non_empty(llm_structured["technologies"]) or _infer_technologies(lowered)
    product_specifications = _format_product_specifications(structured_products) or _infer_product_specifications(text)
    price_range = _infer_price_range(lowered)
    contact_email = _extract_email(text)
    phone = _extract_phone(text)
    address = _infer_address(text)
    description = _build_description(text)

    structured = {
        "company_name": company_name or None,
        "website": website or None,
        "industry": industry,
        "products": products,
        "product_specifications": product_specifications,
        "technologies": technologies,
        "price_range": price_range,
        "contact_email": contact_email,
        "phone": phone,
        "address": address,
        "description": description,
    }
    populated = [key for key, value in structured.items() if value and key not in {"company_name", "website"}]
    print(
        f"[EXTRACTOR] {company_name}: populated fields={populated if populated else 'none'}"
    )
    return structured


def _clean_extraction_text(text: str) -> str:
    if not text:
        return ""
    segments = [segment.strip() for segment in re.split(r"(?<=[.!?])\s+|\n+", text) if segment.strip()]
    cleaned: list[str] = []
    seen_signatures: set[str] = set()

    for segment in segments:
        normalized = _normalize_line(segment)
        if not normalized:
            continue
        if len(normalized.split()) > 22:
            # Drop paragraph-like lines to keep extraction input concise.
            continue
        signature = _line_signature(normalized)
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        cleaned.append(normalized)
        if len(cleaned) >= 4:
            break

    return "\n".join(cleaned)


def _normalize_line(text: str) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip(" ,.;:-")
    return compact


def _line_signature(text: str) -> str:
    lowered = text.lower()
    lowered = re.sub(r"[^a-z0-9\s]", "", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    tokens = lowered.split()
    return " ".join(tokens[:10])


def _extract_llm_candidate_text(text: str) -> str:
    if not text:
        return ""
    sentences = [segment.strip() for segment in re.split(r"(?<=[.!?])\s+|\n+", text) if segment.strip()]
    selected = [
        sentence for sentence in sentences if any(keyword in sentence.lower() for keyword in LLM_SECTION_KEYWORDS)
    ]
    return " ".join(selected[:80])


def _extract_with_llm_strict(text: str) -> dict[str, object]:
    empty = {"products": [], "technologies": [], "industry": ""}
    if not text.strip():
        return empty
    if _offline_mode_enabled():
        return empty

    prompt = (
        "Extract ONLY factual data from the text.\n\n"
        "Rules:\n"
        "* Do NOT guess\n"
        "* Do NOT generate\n"
        "* Only use given text\n"
        "* If not found, return empty\n\n"
        "Return JSON:\n"
        "{\n"
        '"products": [],\n'
        '"technologies": [],\n'
        '"industry": ""\n'
        "}\n\n"
        f"Text:\n{text[:7000]}"
    )

    try:
        response = requests.post(
            LLM_API,
            json={"model": LLM_MODEL, "prompt": prompt, "stream": False},
            timeout=25,
        )
        if response.status_code != 200:
            return empty
        payload = response.json()
        raw_text = (payload.get("response") or "").strip()
        parsed = _safe_parse_llm_json(raw_text)
    except Exception:
        return empty

    products = _normalize_llm_list(parsed.get("products"))
    technologies = _normalize_llm_list(parsed.get("technologies"))
    industry = _normalize_llm_str(parsed.get("industry"))

    source_lower = text.lower()
    products = [item for item in products if item.lower() in source_lower]
    technologies = [item for item in technologies if item.lower() in source_lower]
    if industry and industry.lower() not in source_lower:
        industry = ""

    return {
        "products": _uniq(products),
        "technologies": _uniq(technologies),
        "industry": industry,
    }


def _safe_parse_llm_json(raw_text: str) -> dict[str, object]:
    match = JSON_OBJECT_RE.search(raw_text)
    if not match:
        return {}
    try:
        payload = json.loads(match.group(0))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _normalize_llm_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [segment.strip() for segment in value.split(",") if segment.strip()]
    return []


def _normalize_llm_str(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _join_non_empty(values: object) -> Optional[str]:
    if isinstance(values, list):
        normalized = [str(item).strip() for item in values if str(item).strip()]
        return ", ".join(_uniq(normalized)) if normalized else None
    return None


def _extract_email(text: str) -> Optional[str]:
    match = EMAIL_RE.search(text)
    return match.group(0) if match else None


def _extract_phone(text: str) -> Optional[str]:
    match = PHONE_RE.search(text)
    return match.group(0).strip() if match else None


def _infer_industry(lowered: str) -> Optional[str]:
    ordered_mapping = [
        ("semiconductor", "Semiconductor / AI"),
        ("gpu", "Semiconductor / AI"),
        ("chip", "Semiconductor / AI"),
        ("ai", "AI / Software"),
        ("machine learning", "AI / Software"),
        ("ml ", "AI / Software"),
        ("energy", "Energy"),
        ("solar", "Energy"),
        ("power", "Energy"),
        ("aerospace", "Aerospace"),
        ("drone", "Aerospace"),
        ("robot", "Robotics"),
        ("automation", "Industrial Automation"),
        ("analytics", "Analytics"),
        ("software", "Software"),
        ("manufacturing", "Manufacturing"),
        ("motion control", "Industrial Automation"),
    ]
    for key, value in ordered_mapping:
        if key in lowered:
            return value
    return None


def _infer_products(text: str) -> Optional[str]:
    candidates = []
    product_terms = [
        "platform",
        "controller",
        "stage",
        "robot",
        "software",
        "system",
        "solution",
        "sensor",
    ]
    words = re.findall(r"[A-Za-z][A-Za-z0-9-]+", text)
    for i, token in enumerate(words[:-1]):
        if words[i + 1].lower() in product_terms:
            candidates.append(f"{token} {words[i + 1]}")
        if token.lower() in product_terms:
            candidates.append(token)
    uniq = _uniq([item for item in candidates if _is_meaningful_product(item)])
    return ", ".join(uniq[:5]) if uniq else None


def _extract_structured_products(text: str) -> list[dict[str, str]]:
    if not text:
        return []

    sentences = [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", text) if segment.strip()]
    results: list[dict[str, str]] = []

    for index, sentence in enumerate(sentences):
        lowered = sentence.lower()
        if not any(keyword in lowered for keyword in ("product", "platform", "solution", "service", "crm", "suite")):
            continue

        candidates = PRODUCT_NAME_RE.findall(sentence)
        for candidate in candidates:
            name = _clean_product_name(candidate)
            if not _is_plausible_product_name(name):
                continue

            specs = _extract_product_spec_fragment(sentence, name)
            nearby = _extract_nearby_spec_fragment(sentences, index)
            specs = _merge_spec_fragments(specs, nearby)
            if not specs:
                continue
            results.append({"name": name, "specifications": specs})

    cleaned = _dedupe_structured_products(results)
    return cleaned[:6]


def _format_structured_products_json(items: list[dict[str, str]]) -> Optional[str]:
    if not items:
        return None
    normalized = [{"name": item["name"], "specifications": item["specifications"]} for item in items if item.get("name")]
    if not normalized:
        return None
    return json.dumps(normalized[:6], ensure_ascii=False)


def _format_product_specifications(items: list[dict[str, str]]) -> Optional[str]:
    specs = [item["specifications"] for item in items if item.get("specifications")]
    return ", ".join(_uniq(specs[:5])) if specs else None


def _infer_technologies(lowered: str) -> Optional[str]:
    tech_terms = ["ai", "machine learning", "robotics", "automation", "motion control", "vision", "cloud"]
    found = []
    for term in tech_terms:
        if term in lowered:
            found.append(term.upper() if term == "ai" else term.title())
    uniq = _uniq(found)
    return ", ".join(uniq) if uniq else None


def _infer_product_specifications(text: str) -> Optional[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    spec_words = ("precision", "accuracy", "specification", "speed", "torque", "performance")
    for sentence in sentences:
        if any(word in sentence.lower() for word in spec_words):
            clean = sentence.strip()
            if clean:
                return clean[:240]
    return None


def _infer_price_range(lowered: str) -> Optional[str]:
    if "enterprise" in lowered or "premium" in lowered or "high-end" in lowered:
        return "High-end"
    if "affordable" in lowered or "low cost" in lowered or "budget" in lowered:
        return "Budget"
    if "$" in lowered or "pricing" in lowered or "quote" in lowered:
        return "Quoted"
    return None


def _infer_address(text: str) -> Optional[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    address_hints = ("street", "st.", "road", "ave", "avenue", "blvd", "suite", "zip")
    for line in lines:
        low = line.lower()
        if any(h in low for h in address_hints) and any(ch.isdigit() for ch in line):
            return line[:200]
    return None


def _build_description(text: str) -> Optional[str]:
    if not text:
        return None
    sentences = re.split(r"(?<=[.!?])\s+", text)
    kept = [s.strip() for s in sentences if len(s.strip().split()) >= 6]
    if not kept:
        return None
    return " ".join(kept[:2])[:500]


def _uniq(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _clean_product_name(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value or "").strip(" ,.;:-")
    return cleaned


def _is_plausible_product_name(name: str) -> bool:
    if not name:
        return False
    blocked = {
        "It",
        "Its",
        "This",
        "That",
        "These",
        "Those",
        "The",
    }
    if name in blocked:
        return False
    if len(name) < 3 or len(name) > 60:
        return False
    tokens = re.findall(r"[A-Za-z0-9&+\-]+", name)
    if len(tokens) < 2 or len(tokens) > 6:
        return False

    # Product names should look title-like/capitalized and not generic labels.
    if not any(token[:1].isupper() for token in tokens if token):
        return False
    generic_tokens = {
        "product",
        "products",
        "solution",
        "solutions",
        "service",
        "services",
        "platform",
        "platforms",
        "technology",
        "technologies",
        "software",
        "system",
        "systems",
        "suite",
    }
    lowered = [token.lower() for token in tokens]
    if all(token in generic_tokens for token in lowered):
        return False

    return True


def _extract_product_spec_fragment(sentence: str, product_name: str) -> str:
    normalized = sentence.strip()
    if not normalized:
        return ""

    working = normalized.replace(product_name, "", 1).strip(" ,.;:-")
    if not working:
        return ""

    lowered = working.lower()
    if not any(hint in lowered for hint in SPEC_HINTS):
        return ""

    for prefix in (
        "helps",
        "support",
        "supports",
        "includes",
        "include",
        "features",
        "feature",
        "provides",
        "provide",
        "delivers",
        "deliver",
        "offers",
        "offer",
        "enables",
        "enable",
    ):
        if lowered.startswith(prefix):
            return _sanitize_spec_text(working)
    return _sanitize_spec_text(working)


def _extract_nearby_spec_fragment(sentences: list[str], index: int) -> str:
    for offset in (1, -1):
        neighbor_index = index + offset
        if neighbor_index < 0 or neighbor_index >= len(sentences):
            continue
        neighbor = _normalize_line(sentences[neighbor_index])
        if not neighbor:
            continue
        lowered = neighbor.lower()
        if any(hint in lowered for hint in SPEC_HINTS):
            return _sanitize_spec_text(neighbor)
        if lowered.startswith(("it ", "it.", "this ", "these ")):
            return _sanitize_spec_text(neighbor)
    return ""


def _merge_spec_fragments(primary: str, nearby: str) -> str:
    parts = [part.strip() for part in (primary, nearby) if part and part.strip()]
    if not parts:
        return ""
    merged = _uniq(parts)
    return _sanitize_spec_text(", ".join(merged), max_words=26, max_chars=180)


def _dedupe_structured_products(items: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []
    for item in items:
        key = (item["name"].lower(), item["specifications"].lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _finalize_structured_products(items: list[dict[str, str]], limit: int = 6) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    seen_names: set[str] = set()
    for item in items:
        name = _normalize_line(str(item.get("name", "")))
        specs = _sanitize_spec_text(str(item.get("specifications", "")))
        if not name or not _is_plausible_product_name(name):
            continue
        name_key = name.lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        specs = _collapse_repetition(specs)
        output.append({"name": name, "specifications": specs})
        if len(output) >= limit:
            break
    return output


def _collapse_repetition(text: str) -> str:
    if not text:
        return ""
    parts = [part.strip() for part in re.split(r"[,;]\s*", text) if part.strip()]
    deduped = _uniq(parts)
    return ", ".join(deduped)


def _sanitize_spec_text(text: str, max_words: int = 20, max_chars: int = 140) -> str:
    words = text.split()
    compact = " ".join(words[:max_words]).strip(" ,.;:-")
    compact = compact[:max_chars].strip(" ,.;:-")
    return compact


def _fallback_products_to_structured(products: Optional[str]) -> list[dict[str, str]]:
    if not products:
        return []
    names = [part.strip() for part in products.split(",") if part.strip()]
    output: list[dict[str, str]] = []
    for name in _uniq(names):
        normalized_name = _title_case_product_name(name)
        if not normalized_name:
            continue
        if len(normalized_name.split()) < 2 or len(normalized_name.split()) > 6:
            continue
        output.append(
            {
                "name": normalized_name,
                "specifications": "",
            }
        )
        if len(output) >= 6:
            break
    return output


def _title_case_product_name(value: str) -> str:
    tokens = [token for token in re.findall(r"[A-Za-z0-9&+\-]+", value or "")]
    if not tokens:
        return ""
    titled = [token if token.isupper() else token.capitalize() for token in tokens]
    return " ".join(titled)


def _is_meaningful_product(value: str) -> bool:
    generic = {"solution", "system", "platform"}
    tokens = [t.lower() for t in re.findall(r"[A-Za-z0-9-]+", value)]
    if not tokens:
        return False
    if tokens[0] in {"the", "this", "that", "these", "those", "it"}:
        return False
    if len(tokens) == 1 and tokens[0] in generic:
        return False
    if all(token in generic for token in tokens):
        return False
    return True


def _offline_mode_enabled() -> bool:
    return os.getenv(OFFLINE_MODE_ENV, "0").strip() == "1"
