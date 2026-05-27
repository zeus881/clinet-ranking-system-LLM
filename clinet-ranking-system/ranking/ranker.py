"""
REBHU COMPUTING — INTELLIGENT CLIENT SCORING
============================================
Score = 0.30·D + 0.25·P + 0.20·A + 0.15·U + 0.10·N   (max 100)

  D = Domain match        — does the company operate in Rebhu's target sectors?
  P = Product relevance   — do their products need real-time AI/autonomous compute?
  A = AI capability       — how deeply embedded is AI/ML in their stack?
  U = Use-case alignment  — do their applications map to Rebhu's deployment targets?
  N = Need for Rebhu      — LLM semantic fit score against Rebhu ICP

Each sub-score is 0–100; the weight converts it to the final contribution.
breakdown["domain"] = D * 0.30  (max 30 pts), etc.
"""
from __future__ import annotations

from typing import Iterable, List

from models.schemas import Company, RankedCompany

# ── Signal sets ───────────────────────────────────────────────────────────────

# D — Domain: sectors Rebhu serves
_D_STRONG = frozenset([
    "autonomous", "autonomy", "self-driving", "navigation", "robotics", "robot",
    "drone", "uav", "uas", "unmanned", "defense", "military", "tactical",
    "aerial vehicle", "ground vehicle",
])
_D_MEDIUM = frozenset([
    "automation", "automated", "industrial automation", "manufacturing",
    "warehouse", "logistics", "fleet", "vehicles", "aerospace",
    "inspection", "surveillance", "edge computing", "embedded",
])

# P — Product fit: product types Rebhu's hardware accelerates
_P_STRONG = frozenset([
    "robotics", "drone", "uav", "autonomous vehicle", "agv", "amr",
    "navigation system", "vision system", "edge compute", "lidar",
    "perception system", "flight controller",
])
_P_MEDIUM = frozenset([
    "ai platform", "machine learning platform", "computer vision platform",
    "automation system", "control system", "embedded system", "sensor",
    "real-time system", "inference engine",
])

# A — AI capability signals
_A_STRONG = frozenset([
    "computer vision", "deep learning", "neural network", "lidar",
    "sensor fusion", "slam", "edge ai", "embedded ai", "convolutional",
    "object detection", "image recognition", "3d perception",
])
_A_MEDIUM = frozenset([
    "artificial intelligence", "machine learning", "inference",
    "perception", "ai", "ml", "nlp", "reinforcement learning",
])

# U — Use-case alignment: score per matched use case (0-100 per use case)
_USE_CASE_SCORES: dict[str, int] = {
    "autonomous navigation": 100,
    "warehouse automation": 95,
    "drone delivery": 100,
    "last-mile delivery": 85,
    "industrial inspection": 80,
    "defense": 100,
    "slam": 95,
    "mapping": 80,
    "precision agriculture": 75,
    "factory automation": 82,
    "fleet management": 70,
    "predictive maintenance": 68,
    "quality control": 65,
    "surveillance": 78,
    "search and rescue": 90,
    "logistics automation": 82,
}

# Recommended Rebhu products by profile type
_RECOMMENDED: dict[str, list[str]] = {
    "robotics_drone": [
        "Autonomous Navigation System",
        "Computer Vision Platform",
        "Real-time Control Engine",
    ],
    "ai_vision": [
        "Computer Vision Platform",
        "AI Inference Accelerator",
        "Data Pipeline System",
    ],
    "automation": [
        "Automation Control System",
        "Real-time Processing Platform",
        "Edge Compute Module",
    ],
    "general": [
        "Embedded Systems Framework",
        "Real-time Compute Platform",
    ],
}


# ── Factor D: Domain match (raw 0-100) ───────────────────────────────────────

def _domain_raw(text: str, industry: str, use_cases: list[str]) -> float:
    probe = f"{text} {industry} {' '.join(use_cases)}".lower()
    strong = sum(1 for kw in _D_STRONG if kw in probe)
    medium = sum(1 for kw in _D_MEDIUM if kw in probe)
    return float(min(strong * 28 + medium * 10, 100))


# ── Factor P: Product relevance (raw 0-100) ───────────────────────────────────

def _product_raw(text: str, products: list[str], services: list[str]) -> float:
    probe = f"{text} {' '.join(products)} {' '.join(services)}".lower()
    strong = sum(1 for kw in _P_STRONG if kw in probe)
    medium = sum(1 for kw in _P_MEDIUM if kw in probe)
    # Named products bonus: a company with actual named products is better ranked
    named_bonus = min(len([p for p in products if len(p) > 3]) * 8, 24)
    return float(min(strong * 25 + medium * 10 + named_bonus, 100))


# ── Factor A: AI capability (raw 0-100) ──────────────────────────────────────

def _ai_raw(text: str, technologies: list[str]) -> float:
    probe = f"{text} {' '.join(technologies)}".lower()
    strong = sum(1 for kw in _A_STRONG if kw in probe)
    medium = sum(1 for kw in _A_MEDIUM if kw in probe)
    return float(min(strong * 22 + medium * 8, 100))


# ── Factor U: Use-case alignment (raw 0-100) ─────────────────────────────────

def _use_case_raw(text: str, use_cases: list[str]) -> float:
    probe = f"{text} {' '.join(use_cases)}".lower()
    best = 0
    for uc, score in _USE_CASE_SCORES.items():
        if uc in probe:
            best = max(best, score)
    return float(best)


# ── Factor N: Need score (keyword-based) ─────────────────────────────────────

def _semantic_need_raw(profile_text: str) -> float:
    """Keyword-based need score (no LLM call — avoids double Ollama load)."""
    return _keyword_need_raw(profile_text)


def _keyword_need_raw(text: str) -> float:
    """Keyword fallback for N when Ollama is down."""
    lowered = text.lower()
    signals = [
        "autonomous", "navigation", "robotics", "drone", "uav", "defense",
        "edge ai", "embedded", "real-time", "sensor fusion", "computer vision",
        "machine learning", "warehouse", "automation", "fleet", "lidar",
    ]
    matches = sum(1 for kw in signals if kw in lowered)
    return float(min(matches * 9, 100))


# ── Master scorer ─────────────────────────────────────────────────────────────

def _compute_score(
    text: str,
    industry: str,
    products: list[str],
    services: list[str],
    technologies: list[str],
    use_cases: list[str],
) -> tuple[float, dict[str, float]]:
    """
    Base score (before confidence × penalty):
      Score = 0.35·D + 0.25·P + 0.20·A + 0.20·U   (max 100)

    Each raw factor is 0–100. Weighted contributions are stored
    in breakdown so the UI can show the breakdown per factor.
    """
    D = _domain_raw(text, industry, use_cases)
    P = _product_raw(text, products, services)
    A = _ai_raw(text, technologies)
    U = _use_case_raw(text, use_cases)

    breakdown = {
        "domain":   round(D * 0.35, 2),
        "product":  round(P * 0.25, 2),
        "ai":       round(A * 0.20, 2),
        "use_case": round(U * 0.20, 2),
    }
    total = round(min(sum(breakdown.values()), 100.0), 2)
    return total, breakdown


# ── Helper classifiers ────────────────────────────────────────────────────────

def _get_category(score: float) -> str:
    if score >= 75:
        return "High Potential"
    if score >= 55:
        return "Good Potential"
    if score >= 35:
        return "Moderate"
    return "Low Potential"


def _get_recommended_products(text: str, products: list[str]) -> list[str]:
    probe = f"{text} {' '.join(products)}".lower()
    if any(kw in probe for kw in ["robotics", "drone", "uav", "robot", "navigation"]):
        return _RECOMMENDED["robotics_drone"]
    if any(kw in probe for kw in ["computer vision", "deep learning", "neural"]):
        return _RECOMMENDED["ai_vision"]
    if "automation" in probe:
        return _RECOMMENDED["automation"]
    return _RECOMMENDED["general"]


def _generate_reason(
    breakdown: dict[str, float],
    industry: str,
    use_cases: list[str],
    score: float,
) -> str:
    signals: list[str] = []
    if breakdown.get("domain", 0) >= 12:
        signals.append(f"domain match ({industry or 'target sector'})")
    if breakdown.get("ai", 0) >= 8:
        signals.append("AI/vision capabilities")
    if breakdown.get("use_case", 0) >= 8:
        uc = use_cases[0] if use_cases else "aligned application"
        signals.append(f"use case: {uc}")
    if breakdown.get("use_case", 0) >= 10:
        signals.append("strong use-case alignment")
    if not signals:
        return "Weak signal — limited overlap with Rebhu ICP."
    return "Rebhu fit: " + "; ".join(signals) + f" (score {score})."


# ── Public API ────────────────────────────────────────────────────────────────

def compute_score(text: str, icp_text: str = "") -> float:
    """Backward-compatible single-text score."""
    score, _ = _compute_score(text, "", [], [], [], [])
    return score


def rank_companies(
    companies: Iterable[Company],
    summaries_by_company: dict[str, str],
    structured_by_company: dict[str, dict],
    icp_text: str = "",
    texts_by_company: dict[str, str] | None = None,
    query: str | None = None,
) -> List[RankedCompany]:
    """
    Rank companies by Rebhu client targeting score.
    structured_by_company values must contain both serialized strings (for output)
    and Python lists (keys ending in _list) for scoring.
    """
    ranked: List[RankedCompany] = []

    for company in companies:
        summary = summaries_by_company.get(company.website, "")
        full_text = (texts_by_company or {}).get(company.website, "")
        combined = f"{summary} {full_text}".strip()

        s = structured_by_company.get(company.website, {})

        # Lists for multi-factor scoring
        products_list: list[str] = s.get("products_list") or []
        services_list: list[str] = s.get("services_list") or []
        tech_list: list[str] = s.get("technologies_list") or []
        use_cases_list: list[str] = s.get("use_cases_list") or []
        industry: str = s.get("industry") or ""
        confidence: float = float(s.get("confidence") or 0.0)

        base_score, breakdown = _compute_score(
            combined, industry, products_list, services_list, tech_list, use_cases_list
        )

        # Apply penalty and multiplier from pipeline (LLM fallback / low confidence)
        score_multiplier: float = float(s.get("score_multiplier", 1.0))
        score_penalty: float    = float(s.get("score_penalty", 0))
        score = round(max(0.0, min(base_score * score_multiplier - score_penalty, 100.0)), 2)

        if score_penalty > 0 or score_multiplier < 1.0:
            llm_ok = s.get("llm_ok", True)
            reason_tag = "LLM-fallback" if not llm_ok else "low-confidence"
            print(
                f"[RANKER] {s.get('company_name','?')} — "
                f"base={base_score:.1f} × {score_multiplier} − {score_penalty:.0f} "
                f"= {score:.1f}  [{reason_tag}]"
            )

        category = _get_category(score)
        recommended = _get_recommended_products(combined, products_list)
        reason = _generate_reason(breakdown, industry, use_cases_list, score)

        item = RankedCompany(company=company, score=score, summary=summary)
        item.industry = industry or None
        item.products = s.get("products")                   # JSON string
        item.services = s.get("services")                   # comma string
        item.product_specifications = s.get("product_specifications")
        item.technologies = s.get("technologies")           # comma string
        item.use_cases = use_cases_list
        item.price_range = s.get("price_range")
        item.contact_email = s.get("contact_email")
        item.phone = s.get("phone")
        item.address = s.get("address")
        item.description = s.get("description")
        item.breakdown = breakdown
        item.confidence = confidence
        item.category = category
        item.recommended_products = recommended
        item.reason = reason

        ranked.append(item)

    return sorted(ranked, key=lambda x: float(x.score), reverse=True)
