"""
Production-grade web crawler for the Client Ranking System.

Design decisions:
- Single retry loop (no double-retry from Retry adapter + manual loop)
- Exponential backoff: 1s, 2s, 4s
- Two header profiles: standard + browser-mimicry (for 403s)
- Hard skip: PDFs, binaries, login/contact/careers pages
- Quality flags: GOOD (≥1000 chars) / LOW (≥200) / FAILED
"""
from __future__ import annotations

import os
import re
import time
from typing import Dict, Optional
from urllib.parse import urljoin, urlparse, urlunparse

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── Configuration ──────────────────────────────────────────────────────────────

OFFLINE_MODE_ENV  = "CRS_OFFLINE_MODE"
REQUEST_TIMEOUT   = 10       # seconds — enough for slow servers
MAX_RETRIES       = 2        # attempts per URL (total: 3)
MAX_PAGES         = 8        # pages per company
MAX_TEXT_CHARS    = 4000     # chars kept per page
QUALITY_GOOD      = 1000     # chars threshold for GOOD
QUALITY_LOW       = 200      # chars threshold for LOW (else FAILED)

TARGET_PATH_HINTS = (
    "/about", "/company", "/products", "/services",
    "/solutions", "/technology", "/platform", "/features", "/what-we-do",
)

_AVOID = frozenset([
    # Legal / compliance
    "tos", "terms", "privacy", "legal", "policy", "cookie", "gdpr",
    "warranty", "refund", "disclaimer",
    # Marketing noise
    "blog", "news", "press", "media", "events", "webinar", "podcast",
    "customer-stories", "case-studies", "testimonials",
    # Auth / account
    "login", "signin", "sign-in", "signup", "sign-up", "register", "account",
    # HR / admin
    "careers", "jobs", "team", "leadership", "investors", "investor",
    "partners", "partner",
    # Commerce / support
    "pricing", "contact", "support", "help", "faq", "cart", "checkout",
    "regions", "locations", "metrics", "status",
])

# Extensions that will never yield useful text
_BINARY_EXTS = frozenset([
    ".pdf", ".docx", ".xlsx", ".pptx", ".zip", ".tar", ".gz",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    ".mp4", ".mp3", ".avi", ".mov",
    ".exe", ".msi", ".dmg",
])

_HEADERS_STANDARD = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Cache-Control": "no-cache",
}

# Extra headers that bypass some 403 protections
_HEADERS_BROWSER = {
    **_HEADERS_STANDARD,
    "Referer": "https://www.google.com/",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}


# ── URL helpers ────────────────────────────────────────────────────────────────

def _normalize_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    parsed = urlparse(value)
    return urlunparse(parsed._replace(query="", fragment="")).rstrip("/")


def _domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _same_domain(candidate: str, base: str) -> bool:
    return _domain(candidate) == _domain(base)


def _is_binary_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in _BINARY_EXTS)


def _should_skip(url: str) -> bool:
    lowered = url.lower()
    return _is_binary_url(url) or any(kw in lowered for kw in _AVOID)


# ── HTTP fetch ─────────────────────────────────────────────────────────────────

def _fetch(url: str) -> Optional[str]:
    """
    Fetch URL with up to MAX_RETRIES+1 attempts and exponential backoff.
    Tries standard headers first, then browser-mimicry headers on 403.
    Returns HTML string or None.
    """
    header_profiles = [_HEADERS_STANDARD, _HEADERS_BROWSER]

    for attempt in range(MAX_RETRIES + 1):
        headers = header_profiles[min(attempt, len(header_profiles) - 1)]
        try:
            resp = requests.get(
                url,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
                verify=False,
                allow_redirects=True,
            )

            if resp.status_code == 200:
                if len(resp.text) > 100:
                    print(f"[CRAWLER] Successfully fetched {url} (attempt {attempt + 1})")
                    return resp.text
                # Got 200 but empty body — not retryable
                print(f"[CRAWLER] Empty body from {url}")
                return None

            if resp.status_code in (301, 302, 307, 308):
                # requests follows redirects automatically; this shouldn't happen
                return None

            if resp.status_code in (403, 429):
                print(f"[CRAWLER] HTTP {resp.status_code} for {url} (attempt {attempt + 1})")
                # 403: retry with better headers; 429: back off
                if attempt < MAX_RETRIES:
                    time.sleep(2 ** attempt)
                continue

            # 404, 410, 5xx etc.
            print(f"[CRAWLER] HTTP {resp.status_code} for {url} (attempt {attempt + 1})")
            if resp.status_code in (404, 410):
                return None  # Not retryable
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)

        except requests.exceptions.Timeout:
            print(f"[CRAWLER] Timeout for {url} (attempt {attempt + 1})")
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)

        except requests.exceptions.ConnectionError as exc:
            print(f"[CRAWLER] Connection error for {url}: {exc} (attempt {attempt + 1})")
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)

        except requests.RequestException as exc:
            print(f"[CRAWLER] Request error for {url}: {exc} (attempt {attempt + 1})")
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)

    print(f"[CRAWLER] Failed after {MAX_RETRIES + 1} attempts: {url}")
    return None


# ── HTML extraction ────────────────────────────────────────────────────────────

def _normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s.,;:!?()'\"/-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_main_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "nav", "footer", "svg", "iframe"]):
        tag.decompose()

    # Metadata
    texts: list[str] = []
    for meta_attr in [{"name": "description"}, {"property": "og:description"}]:
        m = soup.find("meta", meta_attr)
        if m and m.get("content", "").strip():
            texts.append(m["content"].strip())

    # Main content area
    root = soup.select_one("article, main, section") or soup.body or soup

    for h in root.find_all(["h1", "h2", "h3"]):
        t = h.get_text().strip()
        if 10 < len(t) < 200:
            texts.append(t)

    for elem in root.find_all(["p", "li", "span", "div"]):
        # Only leaf-ish nodes (skip containers with many children)
        if len(elem.find_all(recursive=False)) > 5:
            continue
        t = elem.get_text().strip()
        if 20 < len(t) < 800:
            texts.append(t)

    return _normalize_text(" ".join(texts))[:MAX_TEXT_CHARS]


def _extract_section(soup: BeautifulSoup, *selectors: str) -> str:
    texts: list[str] = []
    for sel in selectors:
        for elem in soup.select(sel):
            t = elem.get_text().strip()
            if 15 < len(t) < 1000:
                texts.append(t)
    return " ".join(texts[:5])


def _extract_specs(soup: BeautifulSoup) -> str:
    texts: list[str] = []
    for table in soup.find_all("table"):
        for row in table.find_all("tr")[:10]:
            cells = row.find_all(["td", "th"])
            row_text = " | ".join(c.get_text().strip() for c in cells)
            if 15 < len(row_text) < 500:
                texts.append(row_text)
    for ul in soup.find_all(["ul", "ol"]):
        for li in ul.find_all("li")[:10]:
            t = li.get_text().strip()
            if 15 < len(t) < 500:
                texts.append(t)
    return " ".join(texts[:10])


# ── Link extraction ────────────────────────────────────────────────────────────

def _extract_links(base_url: str, html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    scored: dict[str, int] = {}

    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue

        full = _normalize_url(urljoin(base_url, href))
        if not full or not _same_domain(full, base_url):
            continue
        if _should_skip(full):
            continue

        lowered = full.lower()
        anchor = a.get_text().strip().lower()
        score = 0

        for hint in TARGET_PATH_HINTS:
            if hint in lowered:
                score += 10
        for kw in ("product", "service", "solution", "about", "technology", "feature", "platform"):
            if kw in lowered or kw in anchor:
                score += 5

        if score > 0:
            scored[full] = max(scored.get(full, 0), score)

    sorted_links = sorted(scored, key=lambda u: scored[u], reverse=True)
    return list(dict.fromkeys(sorted_links[:6]))


# Public alias kept for backward compatibility with tests
extract_relevant_links = _extract_links


# ── Data quality ───────────────────────────────────────────────────────────────

def quality_flag(text: str) -> str:
    """Return GOOD / LOW / FAILED based on text length."""
    n = len(text)
    if n >= QUALITY_GOOD:
        return "GOOD"
    if n >= QUALITY_LOW:
        return "LOW"
    return "FAILED"


# ── Sandbox mock data ──────────────────────────────────────────────────────────

_SANDBOX_TEMPLATE = """\
{name} is a technology company focused on autonomous systems and AI-powered solutions.
The company develops advanced robotics platforms and machine learning software for industrial automation.
Their flagship product, {name} Platform, uses computer vision, LiDAR, and SLAM for real-time navigation.
{name} serves clients in warehouse automation, defense, drone delivery, and logistics sectors.
The technology stack includes ROS2, PyTorch, deep learning, sensor fusion, and edge AI.
Products include autonomous mobile robots (AMR), drone navigation systems, and AI inference engines.
Services offered: system integration, professional services, and technical support.
Use cases: warehouse automation, autonomous navigation, industrial inspection, fleet management.
The platform supports real-time control, path planning, and object detection at the edge.
Industry: Autonomous Systems and Robotics. Founded by engineers with expertise in embedded AI.
Contact: info@{domain} | Technology partners include NVIDIA, Intel, and leading sensor manufacturers.
The company has deployed solutions across 20+ countries with a focus on precision and reliability.
"""


def _sandbox_page_map(url: str) -> Dict[str, str]:
    """Return realistic mock data for sandbox/offline mode."""
    domain = _domain(_normalize_url(url)) or "company.com"
    name = domain.split(".")[0].replace("-", " ").title()
    text = _SANDBOX_TEMPLATE.format(name=name, domain=domain)
    print(f"[CRAWLER] Sandbox mode — mock data for {url} ({len(text)} chars)")
    return {
        "all":            text,
        "products":       f"{name} Platform autonomous navigation system with LiDAR.",
        "services":       "System integration and professional services.",
        "specifications": "ROS2, PyTorch, Computer Vision, SLAM, Edge AI.",
        "quality":        "GOOD",
    }


# ── Public API ─────────────────────────────────────────────────────────────────

def crawl_company_website(url: str, max_pages: int = MAX_PAGES) -> Dict[str, str]:
    """
    Crawl a company website. Returns dict with keys:
      all          — merged text from all pages
      products     — product-section text
      services     — service-section text
      specifications — spec/table text
      quality      — GOOD / LOW / FAILED
    """
    if os.getenv(OFFLINE_MODE_ENV, "0") == "1":
        return _sandbox_page_map(url)

    base_url = _normalize_url(url)
    if not base_url:
        print(f"[CRAWLER] Invalid URL: {url!r}")
        return {}

    visited: set[str] = {base_url}
    queue: list[str] = [base_url]
    all_texts: list[str] = []
    product_texts: list[str] = []
    service_texts: list[str] = []
    spec_texts: list[str] = []
    pages_crawled = 0

    while queue and pages_crawled < max_pages:
        current = queue.pop(0)
        pages_crawled += 1
        print(f"[CRAWLER] [{pages_crawled}/{max_pages}] {current}")

        html = _fetch(current)
        if not html:
            print(f"[CRAWLER] Skipping — fetch failed: {current}")
            continue

        text = _extract_main_text(html)
        if text:
            all_texts.append(text)
            print(f"[CRAWLER] ✓ {len(text)} chars — {current}")
        else:
            print(f"[CRAWLER] ✗ No text — {current}")

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        p = _extract_section(soup, "[class*='product']", "[id*='product']",
                             "[class*='solution']", "[id*='solution']")
        if p:
            product_texts.append(p)

        s = _extract_section(soup, "[class*='service']", "[id*='service']",
                             "[class*='offering']", "[id*='offering']")
        if s:
            service_texts.append(s)

        sp = _extract_specs(soup)
        if sp:
            spec_texts.append(sp)

        # Enqueue new links only from first two pages (avoid drift)
        if pages_crawled <= 2:
            for link in _extract_links(current, html):
                if link not in visited and len(visited) < max_pages * 2:
                    visited.add(link)
                    queue.append(link)

    merged = _normalize_text(" ".join(all_texts))[:MAX_TEXT_CHARS]
    flag = quality_flag(merged)
    print(f"[CRAWLER] Done — {pages_crawled} pages | {len(merged)} chars | quality={flag}")

    return {
        "all":            merged,
        "products":       _normalize_text(" ".join(product_texts))[:MAX_TEXT_CHARS],
        "services":       _normalize_text(" ".join(service_texts))[:MAX_TEXT_CHARS],
        "specifications": _normalize_text(" ".join(spec_texts))[:MAX_TEXT_CHARS],
        "quality":        flag,
    }
