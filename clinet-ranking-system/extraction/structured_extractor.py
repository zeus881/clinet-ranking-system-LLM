"""
LLM-based structured extraction using Ollama.
NO regex fallback — LLM failure means the company is skipped.

Performance design:
  - Text pre-filtered to ≤1500 chars of relevant content before LLM call
  - Timeout 25 s; retry once with 900 chars on failure
  - num_predict=350 (JSON output is small)
  - Prompt is intentionally short (~300 chars of instructions)
  - Metrics tracked per-session
"""
from __future__ import annotations

import json
import os
import re
import time
import requests
from dataclasses import dataclass, field
from typing import Optional

OLLAMA_API   = "http://localhost:11434/api/generate"
OFFLINE_MODE = "CRS_OFFLINE_MODE"
LLM_MODEL    = os.getenv("CRS_LLM_MODEL", "llama3:latest")

LLM_TIMEOUT      = int(os.getenv("CRS_LLM_TIMEOUT", "25"))  # seconds per attempt
LLM_MAX_CHARS    = int(os.getenv("CRS_LLM_MAX_CHARS", "900"))  # chars sent to LLM (attempt 1)
LLM_RETRY_CHARS  = 600                                          # chars on retry (attempt 2)


# ── Prompt ─────────────────────────────────────────────────────────────────────
# Short and strict — long prompts slow tokenisation on local LLMs.

_PROMPT = """\
Extract B2B company data. Return ONLY valid JSON (no markdown, no explanation):
{{"products":[],"services":[],"technologies":[],"industry":"","use_cases":[]}}

STRICT RULES:

products — ONLY real named product or platform brands.
  GOOD: "FleetOS", "NaviCore", "Palladyne IQ", "EZ10", "SwarmOS"
  BAD:  "Introducing Keylo", "Your Remote", "Client Interaction", "AI Platform",
        "Our Solution", "New Product", anything starting with a verb or adjective.
  Max 5. Return [] if no clear branded names exist.

technologies — specific tools, frameworks, or algorithms ONLY.
  GOOD: "ROS2", "LiDAR", "SLAM", "PyTorch", "Computer Vision", "Sensor Fusion", "OpenCV", "YOLOv8"
  BAD:  "Technology", "Intelligent software", "advanced AI", "smart system", "innovative platform"
  Return [] if no specific tech tools are mentioned. Max 8 items.

services — professional services explicitly stated (e.g. "system integration"). Else [].

industry — ONE short label for the company's PRIMARY technical domain.
  GOOD: "Autonomous Vehicles", "Drone / UAV", "Computer Vision AI", "Defense AI",
        "Warehouse Robotics", "AgriTech", "Industrial Inspection", "AI / ML Platform"
  BAD:  "Autonomous Document Processing" for a computer vision company — use "Computer Vision AI".
        Match the dominant TECHNICAL domain, not a product use-case phrase.

use_cases — 2–4 real-world applications, 2–5 words, matching the company's domain.
  GOOD: "autonomous navigation", "drone inspection", "crop monitoring", "object detection"
  BAD:  "warehouse automation" for a drone company unless explicitly stated.

TEXT:
{text}

JSON:"""


# ── Relevant-line keywords ──────────────────────────────────────────────────────
# Lines containing these are sent to the LLM; others are deprioritised.

_RELEVANT_KW = frozenset([
    "product", "platform", "solution", "technology", "technolog",
    "ai", "robot", "autonom", "machine learning", "deep learning",
    "computer vision", "lidar", "slam", "ros", "drone", "uav",
    "sensor", "navigation", "defense", "warehouse", "logistics",
    "software", "hardware", "system", "service", "industry",
    "inference", "embedded", "edge", "fleet", "autonomous",
])


# ── Technology inference map ───────────────────────────────────────────────────

_TECH_INFER: dict[str, str] = {
    "ros2":                    "ROS2",
    " ros ":                   "ROS",
    "lidar":                   "LiDAR",
    "slam":                    "SLAM",
    "computer vision":         "Computer Vision",
    "machine learning":        "Machine Learning",
    " ml ":                    "Machine Learning",
    "deep learning":           "Deep Learning",
    "neural network":          "Neural Networks",
    "neural net":              "Neural Networks",
    "sensor fusion":           "Sensor Fusion",
    "edge ai":                 "Edge AI",
    "edge computing":          "Edge Computing",
    "edge compute":            "Edge Computing",
    "pytorch":                 "PyTorch",
    "tensorflow":              "TensorFlow",
    "cuda":                    "CUDA",
    "opencv":                  "OpenCV",
    "path planning":           "Path Planning",
    "object detection":        "Object Detection",
    "localization":            "Localization",
    "3d perception":           "3D Perception",
    "autonomous navigation":   "Autonomous Navigation",
    "autonomous mobile robot": "AMR",
    " amr ":                   "AMR",
    " agv ":                   "AGV",
    "real-time control":       "Real-time Control",
    "fleet management":        "Fleet Management",
    "warehouse management":    "Warehouse Management",
    "robotics":                "Robotics",
    " robot ":                 "Robotics",
    "drone":                   "Drone Systems",
    " uav ":                   "UAV",
    " uas ":                   "UAS",
    "autonomous":              "Autonomous Systems",
    "automation":              "Automation",
    "artificial intelligence": "AI",
}


# ── Validation sets ────────────────────────────────────────────────────────────

_GENERIC_TERMS = frozenset([
    "platform", "solution", "solutions", "software", "system", "systems",
    "service", "services", "product", "products", "tool", "tools",
    "application", "applications", "suite", "framework", "engine", "module",
    "api", "technology", "technologies", "company", "team", "about", "contact",
    "terms", "privacy", "policy", "information", "data", "management",
    "the platform", "our platform", "our solution", "the system", "our system",
    "industry", "offering", "offerings", "innovation", "infrastructure",
    "integration", "interoperability", "optimization", "consulting",
    "digital transformation", "system integration", "cloud services",
    "cloud", "saas", "paas", "iaas",
])

_SENTENCE_STARTERS = frozenset([
    "our", "the", "a", "an", "this", "these", "those", "we", "they",
    "it", "its", "their", "your", "with", "by", "for", "at", "from",
    "how", "what", "when", "where", "which", "who",
])

_VERBS = frozenset([
    "is", "are", "was", "were", "can", "will", "does", "has", "have",
    "enables", "provides", "helps", "allows", "offers", "delivers",
    "powers", "automates", "supports", "includes", "uses", "builds",
    "creates", "develops", "designed", "built", "used", "based",
    "means", "takes", "make", "makes", "get", "gets", "achieve",
    "maximize", "improve", "transform", "seamlessly",
])

_FAKE_SERVICES = frozenset([
    "platform integration", "interoperability", "optimization", "consulting",
    "digital transformation", "system integration", "api integration",
    "analytics", "reporting", "cloud services", "data services",
    "monitoring", "intelligence", "automation services",
])

# Words that look like product names but are actually sentence openers or marketing verbs
_PRODUCT_VERB_PREFIXES = frozenset([
    "introducing", "meet", "announcing", "presenting", "discover", "explore",
    "welcome", "try", "get", "learn", "see", "find", "choose", "use",
    "featuring", "offering", "providing", "delivering", "enabling", "building",
    "creating", "powering", "designed", "trusted", "loved", "used",
])

# Tokens that appear in product names as meaningful suffixes (brand-like)
_BRAND_LIKE_SUFFIXES = frozenset([
    "os", "ai", "iq", "nav", "bot", "core", "edge", "sense", "vision",
    "pilot", "forge", "lab", "labs", "works", "io", "net", "hub",
])

# Generic nouns that don't make a product name on their own
_GENERIC_PRODUCT_NOUNS = frozenset([
    "remote", "system", "platform", "solution", "service", "management",
    "control", "tool", "hub", "center", "analytics", "intelligence",
    "insight", "insights", "interaction", "experience", "journey",
    "approach", "method", "framework", "strategy", "process",
    # Common nouns that appear in bad two-word "product" extractions
    "energy", "grid", "power", "network", "market", "access",
    "future", "next", "base", "field", "zone", "area", "space",
    "world", "digital", "customers", "customer", "client", "clients",
    "users", "user", "business", "enterprise", "partner", "partners",
    "provider", "cloud", "edge", "node", "link", "bridge", "flow",
    "stream", "view", "track", "monitor", "guard", "shield", "layer",
    "connect", "smart", "data", "report", "result", "output", "input",
])

_PRODUCT_INDICATORS = frozenset([
    "engine", "suite", "studio", "hub", "os", "core", "platform",
    "system", "module", "framework", "sdk", "api", "controller",
])

_PROD_GENERIC = frozenset([
    "platform", "suite", "engine", "system", "solution", "software",
    "management", "integration", "intelligence", "hub", "center",
    "pro", "plus", "max", "go", "one", "air", "api", "sdk",
])


# ── Session metrics ────────────────────────────────────────────────────────────

class _Metrics:
    def __init__(self) -> None:
        self.total = 0
        self.success = 0
        self.timeouts = 0
        self.retries = 0
        self.times: list[float] = []

    def record(self, success: bool, elapsed: float, retried: bool = False) -> None:
        self.total += 1
        if success:
            self.success += 1
        else:
            self.timeouts += 1
        if retried:
            self.retries += 1
        self.times.append(elapsed)

    def report(self) -> str:
        avg = sum(self.times) / len(self.times) if self.times else 0
        rate = self.success / self.total * 100 if self.total else 0
        return (
            f"LLM: {self.success}/{self.total} ok ({rate:.0f}%) | "
            f"avg {avg:.1f}s | timeouts {self.timeouts} | retries {self.retries}"
        )


# Module-level metrics — reset by calling metrics.reset() if needed
metrics = _Metrics()


# ── Public dataclass ───────────────────────────────────────────────────────────

@dataclass
class StructuredProfile:
    products:      list[str] = field(default_factory=list)
    services:      list[str] = field(default_factory=list)
    technologies:  list[str] = field(default_factory=list)
    industry:      str = ""
    use_cases:     list[str] = field(default_factory=list)
    confidence:    float = 0.0
    price_range:   Optional[str] = None
    contact_email: Optional[str] = None
    phone:         Optional[str] = None


# ── Industry inference map (used by fallback) ──────────────────────────────────

_INDUSTRY_SIGNALS: list[tuple[str, str, int]] = [
    # (keyword, label, weight) — higher weight = stronger evidence
    # Autonomous / Robotics
    ("autonomous vehicle",    "Autonomous Vehicles",       12),
    ("autonomous vehicles",   "Autonomous Vehicles",       12),
    ("autonomous shuttle",    "Autonomous Vehicles",       11),
    ("self-driving",          "Autonomous Vehicles",       12),
    ("autonomous mobile robot","Autonomous Vehicles",      11),
    (" amr ",                 "Autonomous Vehicles",       10),
    ("drone",                 "Drone / UAV",               12),
    ("uav",                   "Drone / UAV",               12),
    (" uas ",                 "Drone / UAV",               10),
    ("unmanned aerial",       "Drone / UAV",               12),
    ("robotics",              "Robotics",                  12),
    (" robot ",               "Robotics",                  10),
    # Defense / Security
    ("defense",               "Defense AI",                12),
    ("military",              "Defense AI",                11),
    ("tactical",              "Defense AI",                10),
    ("surveillance",          "Security / Surveillance",    8),
    # Agriculture
    ("precision agriculture",  "AgriTech",                 12),
    ("agriculture",            "AgriTech",                 10),
    ("crop monitoring",        "AgriTech",                 12),
    ("crop",                   "AgriTech",                  7),
    # Healthcare
    ("medical imaging",        "Healthcare AI",            12),
    ("healthcare",             "Healthcare AI",            10),
    ("medical",                "Healthcare AI",             8),
    ("clinical",               "Healthcare AI",             8),
    # Industrial / Manufacturing
    ("manufacturing",          "Industrial Automation",    10),
    ("industrial",             "Industrial Automation",     8),
    ("factory",                "Industrial Automation",     9),
    ("quality inspection",     "Industrial Automation",    11),
    # Inspection
    ("inspection",             "Inspection / NDT",          9),
    ("non-destructive",        "Inspection / NDT",         12),
    ("ndt",                    "Inspection / NDT",         12),
    # Geospatial / Mapping
    ("geospatial",             "Geospatial / Mapping",     12),
    ("lidar mapping",          "Geospatial / Mapping",     12),
    ("point cloud",            "Geospatial / Mapping",     10),
    ("mapping",                "Geospatial / Mapping",      8),
    ("surveying",              "Geospatial / Mapping",      9),
    # Logistics / Warehouse
    ("warehouse automation",   "Warehouse Automation",     12),
    ("warehouse",              "Warehouse Automation",      8),
    ("logistics",              "Logistics",                 9),
    ("last-mile",              "Logistics",                10),
    ("supply chain",           "Logistics",                 9),
    # Retail
    ("retail",                 "Retail Technology",         9),
    ("checkout",               "Retail Technology",        10),
    # AI / Computer Vision (matched after domain-specific above)
    ("computer vision",        "Computer Vision AI",       10),
    ("image recognition",      "Computer Vision AI",       10),
    ("visual ai",              "Computer Vision AI",       11),
    ("deep learning",          "AI / ML Platform",          8),
    ("machine learning",       "AI / ML Platform",          8),
    ("ai platform",            "AI / ML Platform",         11),
    ("model training",         "AI / ML Platform",          9),
    ("edge ai",                "Edge AI",                  11),
    ("edge computing",         "Edge AI",                   9),
    # Embedded
    ("embedded",               "Embedded Systems",          8),
    # Fintech (low weight — avoid misclassifying AI companies)
    ("financial services",     "FinTech",                   9),
    ("fintech",                "FinTech",                  10),
    # Generic fallback (lowest weight)
    ("software",               "Software / SaaS",           5),
]

_USE_CASE_SIGNALS: list[tuple[str, str, int]] = [
    # (keyword, canonical_use_case, weight)
    # Autonomous / Navigation
    ("autonomous navigation",    "autonomous navigation",     12),
    ("path planning",            "autonomous navigation",     10),
    ("slam",                     "SLAM navigation",           10),
    ("localization",             "SLAM navigation",            8),
    # Drone / UAV specific
    ("drone delivery",           "drone delivery",            12),
    ("drone inspection",         "drone inspection",          12),
    ("aerial inspection",        "aerial inspection",         12),
    ("aerial mapping",           "aerial mapping",            12),
    ("uav survey",               "UAV surveying",             12),
    # Warehouse / Logistics
    ("warehouse automation",     "warehouse automation",      10),
    ("last-mile delivery",       "last-mile delivery",        10),
    ("logistics automation",     "logistics automation",       9),
    # Industrial / Manufacturing
    ("factory automation",       "factory automation",         9),
    ("industrial inspection",    "industrial inspection",     11),
    ("quality control",          "quality control",            9),
    ("predictive maintenance",   "predictive maintenance",    10),
    ("anomaly detection",        "anomaly detection",          9),
    ("visual inspection",        "visual inspection",         10),
    ("non-destructive testing",  "non-destructive testing",   12),
    # Defense / Security
    ("border security",          "border security",           11),
    ("perimeter security",       "perimeter security",        11),
    ("surveillance",             "surveillance",               8),
    ("force protection",         "force protection",          11),
    # Agriculture
    ("crop monitoring",          "crop monitoring",           11),
    ("precision agriculture",    "precision agriculture",     12),
    ("field mapping",            "field mapping",              9),
    # Computer Vision / AI
    ("object detection",         "object detection",           9),
    ("image segmentation",       "image segmentation",         9),
    ("face recognition",         "face recognition",          10),
    ("pose estimation",          "pose estimation",            9),
    ("data labeling",            "data labeling",              8),
    ("data annotation",          "data annotation",            8),
    ("model training",           "model training",             7),
    # Healthcare
    ("medical imaging",          "medical imaging",           11),
    ("diagnostic ai",            "AI diagnostics",            11),
    # Retail
    ("checkout automation",      "checkout automation",       11),
    ("retail analytics",         "retail analytics",          10),
    ("inventory management",     "inventory management",       8),
    # Mapping / Survey
    ("mapping",                  "mapping and surveying",      7),
    ("survey",                   "mapping and surveying",      7),
    # General
    ("fleet management",         "fleet management",           8),
    ("search and rescue",        "search and rescue",         11),
    ("real-time tracking",       "real-time tracking",         8),
    ("edge inference",           "edge inference",             9),
]


# Priority tech→industry overrides: if ≥ min_matches tech signals present, use this label.
# Ordered by specificity — more specific checks first.
_TECH_INDUSTRY_OVERRIDES: list[tuple[frozenset, str, int]] = [
    (frozenset(["lidar", "slam", "ros2", "sensor fusion", "path planning", "amr", "agv"]),
     "Autonomous Robotics", 2),
    (frozenset(["drone", "uav", "uas", "unmanned aerial", "aerial"]),
     "Drone / UAV", 1),
    (frozenset(["computer vision", "opencv", "image recognition", "object detection", "yolo"]),
     "Computer Vision AI", 2),
    (frozenset(["deep learning", "neural network", "pytorch", "tensorflow", "machine learning"]),
     "AI / ML Platform", 2),
    (frozenset(["warehouse", "amr", "agv", "picking", "fulfillment"]),
     "Warehouse Automation", 2),
    (frozenset(["medical", "healthcare", "clinical", "pathology", "diagnostic"]),
     "Healthcare AI", 1),
    (frozenset(["defense", "military", "tactical", "ballistic"]),
     "Defense AI", 1),
]


def _validate_industry(llm_industry: str, technologies: list[str], source_text: str) -> str:
    """
    Validate the LLM-returned industry label against extracted technologies.
    Override when tech signals clearly point to a different primary domain.
    Catches cases like LandingAI → 'Autonomous Document Processing' when
    technologies=['Computer Vision', 'Deep Learning'] clearly indicate CV AI.
    """
    combined = " ".join(t.lower() for t in technologies) + " " + source_text.lower()[:800]

    for tech_signals, override_label, min_matches in _TECH_INDUSTRY_OVERRIDES:
        matches = sum(1 for kw in tech_signals if kw in combined)
        if matches >= min_matches:
            if llm_industry.lower() != override_label.lower():
                print(f"[EXTRACTOR] Industry override: {llm_industry!r} → {override_label!r} "
                      f"({matches} tech signals)")
            return override_label

    # If LLM label reads like a use-case phrase rather than an industry
    # (>4 words, or none of its key words appear in source), fall back to keyword inference
    if llm_industry:
        label_words = llm_industry.split()
        if len(label_words) > 4:
            inferred = _infer_industry(source_text)
            if inferred:
                print(f"[EXTRACTOR] Industry override (too long): {llm_industry!r} → {inferred!r}")
                return inferred
        # Check if at least one key word is anchored in source text
        key_words = [w.lower() for w in label_words if len(w) > 4]
        if key_words and not any(kw in source_text.lower() for kw in key_words):
            inferred = _infer_industry(source_text)
            if inferred:
                print(f"[EXTRACTOR] Industry override (unanchored): {llm_industry!r} → {inferred!r}")
                return inferred

    return llm_industry or _infer_industry(source_text)


def _infer_industry(text: str) -> str:
    """Score all industry signals by occurrence × weight; return highest-scoring label."""
    lower = text.lower()
    scores: dict[str, int] = {}
    for signal, label, weight in _INDUSTRY_SIGNALS:
        if signal in lower:
            # Up to 3× bonus for repeated mentions
            occurrences = min(lower.count(signal), 3)
            scores[label] = scores.get(label, 0) + weight * occurrences
    if not scores:
        return ""
    return max(scores, key=lambda k: scores[k])


def _infer_use_cases(text: str, industry: str = "") -> list[str]:
    """
    Score use cases by keyword occurrence × weight.
    Returns top 4 by score; single-word signals require ≥2 occurrences.
    """
    lower = text.lower()
    scores: dict[str, int] = {}
    for keyword, use_case, weight in _USE_CASE_SIGNALS:
        if keyword not in lower:
            continue
        count = lower.count(keyword)
        # Single-keyword signals (≤1 word) need at least 2 occurrences to count
        if " " not in keyword and count < 2:
            continue
        scores[use_case] = scores.get(use_case, 0) + weight * min(count, 3)

    ranked = sorted(scores, key=lambda k: scores[k], reverse=True)
    return ranked[:4]


# ── Public entry points ────────────────────────────────────────────────────────

def extract_structured(text: str) -> Optional[StructuredProfile]:
    """
    Filter → LLM (25 s) → retry with smaller input → validate → infer tech.
    Returns None if all attempts fail — caller should use extract_fallback().
    """
    if not text or len(text.strip()) < 100:
        print("[EXTRACTOR] Text too short — skipping")
        return None

    if os.getenv(OFFLINE_MODE, "0") == "1":
        print("[EXTRACTOR] Sandbox mode — using keyword fallback (no LLM)")
        return extract_fallback(text)

    return _call_with_retry(text)


def extract_fallback(text: str) -> StructuredProfile:
    """
    Keyword-based extraction when LLM is unavailable.
    Never returns None — always produces a partial profile.
    Confidence is capped at 0.40 to signal degraded quality.
    """
    technologies = _infer_technologies(text, [])
    products     = _rescue_products_from_text(text)
    industry     = _infer_industry(text)
    use_cases    = _infer_use_cases(text, industry=industry)

    # Fallback confidence: keyword signals only, floor=0.30, cap=0.40
    tech_lower = [t.lower() for t in technologies]
    specific_count = sum(1 for kw in _SPECIFIC_TECH if any(kw in t for t in tech_lower))
    tech_score = min(specific_count / 4.0, 1.0) * 0.18 + min(len(technologies) / 5.0, 1.0) * 0.10
    ind_score  = 0.07 if industry else 0.0
    uc_score   = min(len(use_cases) / 3.0, 1.0) * 0.08
    # Floor of 0.30: any company that survives the hard-skip threshold has at least
    # some domain signal; 0.11 is misleadingly low and distorts ranking unfairly.
    raw_conf   = tech_score + ind_score + uc_score
    confidence = round(min(max(raw_conf, 0.30), 0.40), 2)

    print(
        f"[EXTRACTOR] Fallback — "
        f"products={products} tech={technologies[:4]} "
        f"industry={industry!r} conf={confidence:.2f}"
    )

    return StructuredProfile(
        products=products,
        services=[],
        technologies=technologies[:8],
        industry=industry,
        use_cases=use_cases,
        confidence=confidence,
    )


# ── Text pre-filter ────────────────────────────────────────────────────────────

# Patterns that signal a product name is present in the sentence
_PRODUCT_NAME_RE = re.compile(
    r'\b[A-Z][a-z]+(?:[A-Z][a-z]*)+\b'  # CamelCase: SwarmOS, NaviCore, EasyMile
    r'|\b[A-Z]{2,}[0-9]+\b'              # Acronym+num: EZ10, ROS2
    r'|\b[A-Z][a-z]+ [A-Z][a-z]+\b'     # Title Case pair: Fast DDS, Palladyne IQ
)


def _filter_relevant(text: str, max_chars: int) -> str:
    """
    Three-tier ranking:
      tier1 — sentences containing product-name patterns (CamelCase / Title Case)
      tier2 — sentences containing domain keywords
      tier3 — everything else
    Falls back to raw truncation if filtering yields too little.
    """
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    tier1, tier2, tier3 = [], [], []

    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if _PRODUCT_NAME_RE.search(s):
            tier1.append(s)
        elif any(kw in s.lower() for kw in _RELEVANT_KW):
            tier2.append(s)
        else:
            tier3.append(s)

    result, budget = [], max_chars
    for p in tier1 + tier2 + tier3:
        if budget <= 0:
            break
        result.append(p[:budget])
        budget -= len(p) + 1

    filtered = " ".join(result).strip()
    if len(filtered) < 150:
        filtered = text[:max_chars]
    return filtered[:max_chars]


# ── Retry wrapper ──────────────────────────────────────────────────────────────

def _call_with_retry(full_text: str) -> Optional[StructuredProfile]:
    """
    Attempt 1: filtered 900 chars, 25 s timeout.
    Attempt 2: filtered 600 chars, 25 s timeout.
    """
    t0 = time.perf_counter()
    retried = False

    for attempt, max_chars in enumerate([LLM_MAX_CHARS, LLM_RETRY_CHARS], start=1):
        snippet = _filter_relevant(full_text, max_chars)
        result = _call_llm_once(snippet, source_text=full_text)

        if result is not None:
            elapsed = time.perf_counter() - t0
            metrics.record(success=True, elapsed=elapsed, retried=retried)
            return result

        if attempt == 1:
            print(f"[EXTRACTOR] Attempt 1 failed — retrying with {LLM_RETRY_CHARS} chars")
            retried = True

    elapsed = time.perf_counter() - t0
    metrics.record(success=False, elapsed=elapsed, retried=retried)
    return None


# ── Single LLM call ────────────────────────────────────────────────────────────

def _call_llm_once(text: str, source_text: str) -> Optional[StructuredProfile]:
    prompt = _PROMPT.format(text=text)
    payload = {
        "model":  LLM_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_predict": 350,   # JSON output is small — cap tokens
        },
    }

    try:
        t0 = time.perf_counter()
        resp = requests.post(OLLAMA_API, json=payload, timeout=LLM_TIMEOUT)
        elapsed = time.perf_counter() - t0
        print(f"[EXTRACTOR] Ollama responded in {elapsed:.1f}s")
    except requests.exceptions.ConnectionError:
        print(f"[EXTRACTOR] Cannot reach Ollama at {OLLAMA_API}")
        return None
    except requests.exceptions.Timeout:
        print(f"[EXTRACTOR] Timeout after {LLM_TIMEOUT}s")
        return None

    if resp.status_code == 404:
        print(f"[EXTRACTOR] 404 — model '{LLM_MODEL}' not found. Run: ollama pull {LLM_MODEL}")
        return None
    if resp.status_code != 200:
        print(f"[EXTRACTOR] HTTP {resp.status_code}: {resp.text[:120]}")
        return None

    raw = resp.json().get("response", "").strip()
    if not raw:
        print("[EXTRACTOR] Empty response")
        return None

    return _parse_validate(raw, source_text=source_text)


# ── Parse + validate + infer ───────────────────────────────────────────────────

def _parse_validate(raw: str, source_text: str) -> Optional[StructuredProfile]:
    raw = re.sub(r"```(?:json)?", "", raw).strip()
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        print(f"[EXTRACTOR] No JSON found: {raw[:100]!r}")
        return None

    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        print(f"[EXTRACTOR] JSON error: {exc}")
        return None

    # industry sometimes comes back as a list
    industry_raw = data.get("industry", "")
    if isinstance(industry_raw, list):
        industry_raw = industry_raw[0] if industry_raw else ""

    # Rescue named product systems misclassified as services
    raw_products, raw_services = _rescue_products_from_services(
        data.get("products", []), data.get("services", [])
    )

    products     = _clean_products(raw_products, source_text)
    services     = _clean_services(raw_services, source_text)
    technologies = _clean_tech(data.get("technologies", []))
    use_cases    = _clean_use_cases(data.get("use_cases", []))
    industry_raw_str = _clean_str(str(industry_raw), max_words=6)

    technologies = _infer_technologies(source_text, technologies)

    # Validate / override industry using tech signals before finalising
    industry = _validate_industry(industry_raw_str, technologies, source_text)

    # If LLM found no products, scan source text for proper-noun brand tokens
    if not products:
        products = _rescue_products_from_text(source_text)

    # Augment sparse LLM use-cases with keyword-based inference
    if len(use_cases) < 3:
        keyword_ucs = _infer_use_cases(source_text, industry=industry)
        for uc in keyword_ucs:
            if uc not in use_cases:
                use_cases.append(uc)
        use_cases = use_cases[:6]

    confidence = _compute_confidence(products, technologies, industry, use_cases, source_text)

    profile = StructuredProfile(
        products=products[:6],
        services=services[:5],
        technologies=technologies[:10],
        industry=industry,
        use_cases=use_cases[:6],
        confidence=confidence,
    )

    print(
        f"[EXTRACTOR] OK — "
        f"products={profile.products} "
        f"tech={profile.technologies} "
        f"industry={profile.industry!r} "
        f"conf={profile.confidence:.2f}"
    )
    return profile


# ── Rescue / clean helpers ─────────────────────────────────────────────────────

def _rescue_products_from_services(products: list, services: list) -> tuple[list, list]:
    rescued, remaining = [], []
    for svc in services:
        if not isinstance(svc, str):
            remaining.append(svc)
            continue
        words = svc.strip().split()
        if words and words[0][0].isupper() and words[-1].lower() in _PRODUCT_INDICATORS:
            rescued.append(svc)
        else:
            remaining.append(svc)
    return products + rescued, remaining


def _product_in_text(product: str, words: list[str], text_lower: str) -> bool:
    identifying = [w.lower() for w in words if len(w) > 4 and w.lower() not in _PROD_GENERIC]
    if not identifying:
        return product.lower() in text_lower
    return any(w in text_lower for w in identifying)


def _is_brand_token(token: str) -> bool:
    """True if the token looks like a brand/product identifier rather than a common word."""
    t = token.strip(".,;:!?")
    if not t:
        return False
    # CamelCase: SwarmOS, NaviCore, EasyMile
    if re.match(r'^[A-Z][a-z]+(?:[A-Z][a-z]*)+$', t):
        return True
    # All-caps acronym with optional digits: EZ10, ROS2, AMR, DDS
    if re.match(r'^[A-Z]{2,6}[0-9]{0,3}$', t):
        return True
    # Digit-containing mixed: Nano3, X200, Alpha4
    if re.search(r'[0-9]', t) and t[0].isupper():
        return True
    # Ends with a brand-like suffix (e.g. "FleetOS" already caught, but "NavEdge")
    if t[0].isupper() and t.lower().endswith(tuple(_BRAND_LIKE_SUFFIXES)) and len(t) > 4:
        return True
    return False


def _clean_products(items: list, source_text: str) -> list[str]:
    text_lower = source_text.lower()
    out: list[str] = []
    for raw in items:
        if not isinstance(raw, str):
            continue
        item = raw.strip().strip('"\'')
        if not item:
            continue
        words = item.split()
        if len(words) > 5 or len(words) < 1:
            continue
        first = words[0].lower().rstrip(".,;:!?")
        # Filter sentence starters ("Our X", "The X", "A X")
        if first in _SENTENCE_STARTERS:
            continue
        # Filter marketing verb openers ("Introducing X", "Meet X", "Powering X")
        if first in _PRODUCT_VERB_PREFIXES:
            continue
        # Filter gerunds at position 0: "Enabling X", "Building X"
        if first.endswith("ing") and len(first) > 5:
            continue
        # Filter past-participle openers: "Designed X", "Trusted X"
        if first.endswith("ed") and len(first) > 4 and first not in ("named", "called"):
            continue
        # Filter ANY word in the phrase being a sentence starter ("Customers Our", "Grid Our")
        if any(w.lower().rstrip(".,;:!?") in _SENTENCE_STARTERS for w in words[1:]):
            continue
        # Filter generic single-word or all-generic-noun phrases
        if item.lower() in _GENERIC_TERMS:
            continue
        # Must have at least one uppercase word
        if not any(w[0].isupper() for w in words if w):
            continue
        # Filter if a verb sneaks in ("FleetOS enables X")
        if any(w.lower().rstrip(".,;:!?") in _VERBS for w in words):
            continue
        # Filter if it reads like a sentence fragment
        if re.search(r"[.!?]\s", item):
            continue
        # If no brand-like token present, require the phrase is NOT just generic nouns
        if not any(_is_brand_token(w) for w in words):
            word_lowers = [w.lower().rstrip(".,;:!?") for w in words]
            # Two-word phrase with both words being generic nouns → skip
            if len(words) == 2 and all(w in _GENERIC_PRODUCT_NOUNS or w in _GENERIC_TERMS
                                       for w in word_lowers):
                continue
            # All words are common English words (no brand signal) → skip
            if all(w in _GENERIC_PRODUCT_NOUNS or w in _GENERIC_TERMS or
                   w in _SENTENCE_STARTERS or w in _VERBS for w in word_lowers):
                continue
        # Anti-hallucination: must appear in source text
        if not _product_in_text(item, words, text_lower):
            continue
        out.append(item)
    return list(dict.fromkeys(out))[:5]  # cap at 5 meaningful products


# Words that should never start a real technology term
_TECH_BAD_STARTERS = frozenset([
    "technology", "technologies", "intelligent", "advanced", "smart",
    "innovative", "powerful", "robust", "seamless", "comprehensive",
    "modern", "digital", "automated", "efficient", "flexible", "scalable",
    "integrated", "specialized", "customized", "cutting", "state", "next",
    "revolutionary", "groundbreaking", "proprietary", "patented", "unique",
    "superior", "real", "true", "pure", "full", "complete", "total",
])

# Partial keywords that signal a genuine multi-word tech phrase
_TECH_PARTIAL_KW = frozenset([
    "vision", "learning", "sensor", "planning", "detection", "fusion",
    "control", "network", "inference", "processing", "recognition",
    "navigation", "perception", "tracking", "segmentation", "estimation",
    "localization", "mapping", "reconstruction", "generation", "synthesis",
])


def _clean_tech(items: list) -> list[str]:
    known_canonical = {v.lower() for v in _TECH_INFER.values()} | _SPECIFIC_TECH
    out: list[str] = []
    for raw in items:
        if not isinstance(raw, str):
            continue
        item = raw.strip().strip('"\'')
        if not item:
            continue
        item_lower = item.lower()

        # Fast-pass: exact match with known canonical tech terms
        if item_lower in known_canonical:
            out.append(item)
            continue

        words = item.split()
        if len(words) > 4:
            continue
        if item_lower in _GENERIC_TERMS:
            continue

        first_lower = words[0].lower().rstrip(".,;:!?")
        if first_lower in _SENTENCE_STARTERS:
            continue
        # Block generic-adjective starters: "Intelligent software", "Advanced AI"
        if first_lower in _TECH_BAD_STARTERS:
            continue
        if any(w.lower().rstrip(".,;:!?") in _VERBS for w in words):
            continue

        # Multi-word phrases must contain a technical-looking word to pass
        if len(words) > 1:
            has_tech_word = any(
                # Known acronym / camelCase pattern
                re.match(r'^[A-Z]{2,}[0-9]*$|^[A-Z][a-z]+[A-Z]', w)
                for w in words
            ) or any(kw in item_lower for kw in _TECH_PARTIAL_KW)
            if not has_tech_word:
                continue

        out.append(item)
    return list(dict.fromkeys(out))


def _clean_services(items: list, source_text: str) -> list[str]:
    text_lower = source_text.lower()
    out: list[str] = []
    for raw in items:
        if not isinstance(raw, str):
            continue
        item = raw.strip().strip('"\'')
        if not item:
            continue
        words = item.split()
        if len(words) > 5:
            continue
        if item.lower() in _GENERIC_TERMS or item.lower() in _FAKE_SERVICES:
            continue
        if words[0].lower() in _SENTENCE_STARTERS:
            continue
        if any(w.lower().rstrip(".,;:!?") in _VERBS for w in words):
            continue
        sig = [w.lower().strip(".,;:!?") for w in words if len(w) > 3]
        if sig and sum(1 for w in sig if w in text_lower) < max(1, len(sig) // 2):
            continue
        out.append(item)
    return list(dict.fromkeys(out))


def _clean_use_cases(items: list) -> list[str]:
    _vague = frozenset([
        "maximize efficiency", "seamless integration", "digital transformation",
        "improve performance", "achieve goals", "best practices",
        "business growth", "operational excellence",
    ])
    out: list[str] = []
    for raw in items:
        if not isinstance(raw, str):
            continue
        item = raw.strip().strip('"\'').lower()
        if not item:
            continue
        words = item.split()
        if len(words) < 2 or len(words) > 6:
            continue
        if item in _vague or any(p in item for p in _vague):
            continue
        if any(w.rstrip(".,;:!?") in _VERBS for w in words):
            continue
        out.append(item)
    return list(dict.fromkeys(out))


def _clean_str(value: str, max_words: int = 5) -> str:
    value = (value or "").strip()
    if not value or len(value.split()) > max_words:
        return ""
    if value.split()[0].lower() in _SENTENCE_STARTERS:
        return ""
    return value


# ── Technology inference ───────────────────────────────────────────────────────

def _infer_technologies(source_text: str, existing: list[str]) -> list[str]:
    text_lower = " " + source_text.lower() + " "
    existing_lower = [t.lower() for t in existing]
    inferred: list[str] = []

    for keyword, canonical in _TECH_INFER.items():
        canonical_l = canonical.lower()
        if any(canonical_l == ex or canonical_l in ex or ex in canonical_l
               for ex in existing_lower):
            continue
        if keyword in text_lower:
            inferred_lower = [i.lower() for i in inferred]
            if not any(canonical_l == inf or canonical_l in inf or inf in canonical_l
                       for inf in inferred_lower):
                inferred.append(canonical)

    return list(dict.fromkeys(existing + inferred))


# ── Product rescue from source text ───────────────────────────────────────────

# Tokens that are almost certainly NOT product names even if capitalized
_RESCUE_SKIP = frozenset([
    "the", "and", "for", "with", "our", "your", "this", "that", "from",
    "into", "about", "more", "have", "been", "will", "are", "not", "all",
    "company", "team", "world", "global", "group", "inc", "ltd", "llc",
    "contact", "about", "home", "blog", "news", "careers", "learn",
    "solutions", "services", "products", "technology", "industries",
    "platform", "system", "systems", "software", "hardware",
])

# A product-name sentence contains one of these nearby
_PRODUCT_CONTEXT_RE = re.compile(
    r'\b(?:product|platform|software|system|solution|tool|suite|'
    r'robot|drone|vehicle|device|sensor|engine|sdk|api)\b',
    re.IGNORECASE,
)

# CamelCase or ALL-CAPS-short or Acronym+digits
_BRAND_TOKEN_RE = re.compile(
    r'\b([A-Z][a-z]+(?:[A-Z][a-z]*)+\b'       # CamelCase: SwarmOS, NaviCore
    r'|[A-Z]{2,5}(?:[0-9]+)?\b'               # EZ10, ROS2, DDS, IQ
    r'|[A-Z][a-z]+ [A-Z][a-z]+)'              # Title Case: Fast DDS, Palladyne IQ
)


def _rescue_products_from_text(source_text: str) -> list[str]:
    """
    Last-resort scan: find CamelCase / acronym tokens in sentences that also
    contain a product-context word. Return up to 3 candidates.
    """
    candidates: list[str] = []
    seen: set[str] = set()

    for sentence in re.split(r"[.!?\n]+", source_text):
        if not _PRODUCT_CONTEXT_RE.search(sentence):
            continue
        for m in _BRAND_TOKEN_RE.finditer(sentence):
            token = m.group(0).strip()
            token_l = token.lower()
            if token_l in _RESCUE_SKIP:
                continue
            if token_l in _GENERIC_TERMS:
                continue
            if len(token) < 3 or len(token) > 40:
                continue
            if token not in seen:
                seen.add(token)
                candidates.append(token)
        if len(candidates) >= 3:
            break

    # Remove tokens that are known technology names
    known_tech_lower = {v.lower() for v in _TECH_INFER.values()}
    candidates = [c for c in candidates if c.lower() not in known_tech_lower]

    if candidates:
        print(f"[EXTRACTOR] Rescued products from text: {candidates}")
    return candidates[:3]


# ── Confidence ─────────────────────────────────────────────────────────────────

_SPECIFIC_TECH = frozenset([
    "lidar", "slam", "ros2", "pytorch", "tensorflow", "cuda", "opencv",
    "sensor fusion", "3d perception", "object detection", "depth estimation",
    "amr", "agv", "path planning", "point cloud", "voxel", "imu",
    "computer vision", "deep learning", "machine learning", "neural network", "transformer",
    "convolutional", "yolo", "open3d", "pcl", "rtabmap", "cartographer",
])


def _compute_confidence(
    products: list[str], technologies: list[str],
    industry: str, use_cases: list[str],
    source_text: str = "",
) -> float:
    """
    Granular 0–1 confidence based on extraction completeness and signal specificity.

    Breakdown (max 1.0):
      products    0.35  — named brands found (quality weighted)
      tech        0.30  — specific tech signals (0.20 specific + 0.10 breadth)
      industry    0.12  — industry label present
      use_cases   0.13  — use case diversity
      text_length 0.10  — bonus for longer/richer source text
    """
    # Product score: named multi-token or CamelCase products score more
    named = [p for p in products if len(p.split()) >= 2 or any(_is_brand_token(w) for w in p.split())]
    prod_score = min(len(named) / 3.0, 1.0) * 0.28 + min(len(products) / 5.0, 1.0) * 0.07

    # Technology score: reward specificity
    tech_lower = [t.lower() for t in technologies]
    specific_count = sum(1 for kw in _SPECIFIC_TECH if any(kw in t for t in tech_lower))
    tech_specific = min(specific_count / 4.0, 1.0) * 0.22
    tech_breadth  = min(len(technologies) / 6.0, 1.0) * 0.10
    tech_score = tech_specific + tech_breadth

    # Industry and use-case scores
    ind_score = 0.12 if industry else 0.0
    uc_score  = min(len(use_cases) / 3.0, 1.0) * 0.11

    # Text quality bonus: more text → more reliable extraction
    text_len = len(source_text)
    if text_len >= 2000:
        text_bonus = 0.10
    elif text_len >= 1000:
        text_bonus = 0.06
    elif text_len >= 500:
        text_bonus = 0.03
    else:
        text_bonus = 0.0

    raw = prod_score + tech_score + ind_score + uc_score + text_bonus
    return round(min(raw, 1.0), 2)
