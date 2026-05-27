from __future__ import annotations

import json
import os
import re
from collections import deque
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
RELEVANT_KEYWORDS = ("products", "solutions", "services", "platform", "technology")
VISIBLE_SECTION_KEYWORDS = ("product", "solution", "service", "technology")
DEFAULT_TIMEOUT = 12
MAX_DEPTH = 2
MAX_PAGES = 8
OLLAMA_API = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2"
OFFLINE_MODE_ENV = "CRS_OFFLINE_MODE"


def crawl_website(url: str, max_depth: int = MAX_DEPTH, max_pages: int = MAX_PAGES) -> list[str]:
    normalized_url = _normalize_url(url)
    base_domain = _domain(normalized_url)
    visited: set[str] = set()
    queued: set[str] = {normalized_url}
    queue: deque[tuple[str, int]] = deque([(normalized_url, 0)])
    relevant_pages: list[str] = []

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        }
    )

    while queue and len(relevant_pages) < max_pages:
        current_url, depth = queue.popleft()
        queued.discard(current_url)
        if current_url in visited:
            continue
        visited.add(current_url)

        html = _safe_get(session, current_url)
        if not html:
            continue

        if depth == 0 or _is_relevant_url(current_url):
            relevant_pages.append(html)

        if depth >= max_depth:
            continue

        for next_url in _extract_links(current_url, html):
            if next_url in visited or next_url in queued:
                continue
            if _domain(next_url) != base_domain:
                continue
            if not _is_relevant_url(next_url):
                continue
            queue.append((next_url, depth + 1))
            queued.add(next_url)

    return relevant_pages


def extract_visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for tag_name in ("script", "style", "noscript", "nav", "footer", "header", "svg"):
        for tag in soup.find_all(tag_name):
            tag.decompose()

    text = " ".join(soup.stripped_strings)
    return re.sub(r"\s+", " ", text).strip()


def extract_relevant_sections(text: str) -> str:
    if not text:
        return ""

    chunks = re.split(r"(?<=[.!?])\s+|\n+", text)
    selected = [
        chunk.strip()
        for chunk in chunks
        if chunk.strip()
        and any(keyword in chunk.lower() for keyword in VISIBLE_SECTION_KEYWORDS)
    ]
    return "\n".join(_deduplicate_preserve_order(selected))


def extract_with_llm(text: str) -> dict[str, Any]:
    empty_result = {"products": [], "technologies": [], "industry": ""}
    if not text.strip():
        return empty_result
    if os.getenv(OFFLINE_MODE_ENV, "0").strip() == "1":
        return empty_result

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
        f"Text:\n{text[:8000]}"
    )

    try:
        response = requests.post(
            OLLAMA_API,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        raw = (payload.get("response") or "").strip()
        parsed = json.loads(_extract_json_object(raw))
    except Exception:
        return empty_result

    return {
        "products": _normalize_list(parsed.get("products")),
        "technologies": _normalize_list(parsed.get("technologies")),
        "industry": _normalize_string(parsed.get("industry")),
    }


def merge_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    merged_products: list[str] = []
    merged_technologies: list[str] = []
    industries: list[str] = []

    for result in results:
        merged_products.extend(_normalize_list(result.get("products")))
        merged_technologies.extend(_normalize_list(result.get("technologies")))
        industry = _normalize_string(result.get("industry"))
        if industry:
            industries.append(industry)

    return {
        "products": _deduplicate_preserve_order(merged_products),
        "technologies": _deduplicate_preserve_order(merged_technologies),
        "industry": industries[0] if industries else "",
    }


def calculate_confidence(results: list[dict[str, Any]], total_pages: int) -> float:
    if total_pages <= 0:
        return 0.0

    pages_with_data = sum(
        1
        for result in results
        if _normalize_list(result.get("products"))
        or _normalize_list(result.get("technologies"))
        or _normalize_string(result.get("industry"))
    )
    return round(pages_with_data / total_pages, 4)


def extract_company_data(company_url: str) -> dict[str, Any]:
    pages = crawl_website(company_url)
    extracted_results: list[dict[str, Any]] = []

    for html in pages:
        visible_text = extract_visible_text(html)
        relevant_text = extract_relevant_sections(visible_text)
        extracted_results.append(extract_with_llm(relevant_text))

    merged = merge_results(extracted_results)
    return {
        "company_url": _normalize_url(company_url),
        "products": merged["products"],
        "technologies": merged["technologies"],
        "industry": merged["industry"],
        "confidence": calculate_confidence(extracted_results, len(pages)),
    }


def _safe_get(session: requests.Session, url: str) -> str | None:
    try:
        response = session.get(url, timeout=DEFAULT_TIMEOUT, allow_redirects=True)
        if response.status_code in {401, 403}:
            return None
        response.raise_for_status()
        return response.text
    except requests.RequestException:
        return None


def _extract_links(base_url: str, html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []

    for anchor in soup.find_all("a", href=True):
        href = (anchor.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        candidate = _normalize_url(urljoin(base_url, href))
        links.append(candidate)

    return _deduplicate_preserve_order(links)


def _normalize_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    parsed = urlparse(url)
    normalized = parsed._replace(fragment="", query="")
    return normalized.geturl().rstrip("/")


def _domain(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def _is_relevant_url(url: str) -> bool:
    lowered = url.lower()
    return any(keyword in lowered for keyword in RELEVANT_KEYWORDS)


def _extract_json_object(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return "{}"
    return match.group(0)


def _normalize_list(value: Any) -> list[str]:
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return _deduplicate_preserve_order(items)
    if isinstance(value, str) and value.strip():
        parts = [part.strip() for part in value.split(",") if part.strip()]
        return _deduplicate_preserve_order(parts)
    return []


def _normalize_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _deduplicate_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output
