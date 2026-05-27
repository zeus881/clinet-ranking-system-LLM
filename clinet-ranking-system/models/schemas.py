from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Company:
    name: str
    website: str


@dataclass
class RankedCompany:
    company: Company
    score: float
    summary: str
    industry: Optional[str] = None
    products: Optional[str] = None          # JSON string
    services: Optional[str] = None          # comma-separated
    product_specifications: Optional[str] = None
    technologies: Optional[str] = None      # comma-separated
    use_cases: Optional[list[str]] = None
    price_range: Optional[str] = None
    contact_email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    description: Optional[str] = None
    # Scoring breakdown (weighted contributions that sum to score)
    breakdown: Optional[dict[str, float]] = None
    confidence: float = 0.0
    # Rebhu client targeting fields
    category: Optional[str] = None
    recommended_products: Optional[list[str]] = None
    reason: Optional[str] = None
