from __future__ import annotations

from dataclasses import dataclass

from embedding.embeddings import cosine_similarity, generate_embeddings

CATEGORIES = [
    "Technology",
    "Finance",
    "Healthcare",
    "Defense",
    "E-commerce",
    "Manufacturing",
    "Logistics",
    "Energy",
    "Education",
    "Other",
]

CATEGORY_DESCRIPTIONS = {
    "Technology": "software platforms, cloud, AI, data, digital products, SaaS, engineering tools",
    "Finance": "banking, payments, insurance, investment, fintech, lending, financial services",
    "Healthcare": "medical devices, pharmaceuticals, hospitals, diagnostics, biotech, patient care",
    "Defense": "military systems, security solutions, defense technology, surveillance, tactical systems",
    "E-commerce": "online store, retail marketplace, shopping cart, digital commerce, consumer products",
    "Manufacturing": "industrial production, factory operations, components, machinery, fabrication",
    "Logistics": "supply chain, transportation, warehousing, fleet operations, shipping and delivery",
    "Energy": "power systems, renewable energy, oil and gas, utilities, grid infrastructure",
    "Education": "learning platform, courses, schools, universities, training, educational technology",
    "Other": "general business services and corporate information",
}

KEYWORD_HINTS = {
    "Technology": ("software", "platform", "cloud", "api", "ai", "saas"),
    "Finance": ("bank", "fintech", "payments", "insurance", "lending", "investment"),
    "Healthcare": ("medical", "healthcare", "clinical", "biotech", "patient", "pharma"),
    "Defense": ("defense", "military", "surveillance", "security", "tactical"),
    "E-commerce": ("ecommerce", "retail", "shop", "marketplace", "cart", "checkout"),
    "Manufacturing": ("manufacturing", "factory", "industrial", "production", "components"),
    "Logistics": ("logistics", "supply chain", "shipping", "delivery", "transport"),
    "Energy": ("energy", "power", "renewable", "solar", "grid", "utility"),
    "Education": ("education", "learning", "course", "students", "training", "university"),
}


@dataclass
class IndustryDecision:
    industry: str
    confidence: float


def classify_industry(text: str) -> IndustryDecision:
    source = (text or "").strip()
    if not source:
        return IndustryDecision(industry="Other", confidence=0.0)

    category_texts = [CATEGORY_DESCRIPTIONS[category] for category in CATEGORIES]
    vectors = generate_embeddings([source] + category_texts)
    source_vec = vectors[0]

    scores: dict[str, float] = {}
    lowered = source.lower()

    for index, category in enumerate(CATEGORIES, start=1):
        semantic = cosine_similarity(source_vec, vectors[index])
        keyword_bonus = sum(0.03 for token in KEYWORD_HINTS.get(category, ()) if token in lowered)
        scores[category] = semantic + keyword_bonus

    best = max(scores.items(), key=lambda item: item[1])
    confidence = max(0.0, min(1.0, best[1]))
    return IndustryDecision(industry=best[0], confidence=round(confidence, 4))
