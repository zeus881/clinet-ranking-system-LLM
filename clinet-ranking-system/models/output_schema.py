from __future__ import annotations

from pydantic import BaseModel, Field


class OutputCompanyRecord(BaseModel):
    company_name: str
    website: str
    industry: str | None = None
    products: list[dict[str, str]] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    product_specifications: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    use_cases: list[str] = Field(default_factory=list)
    price_range: str | None = None
    contact_email: str | None = None
    phone: str | None = None
    address: str | None = None
    description: str | None = None
    summary: str | None = None
    score: float
    breakdown: dict[str, float] = Field(default_factory=dict)
    confidence: float = 0.0
    # Rebhu client targeting fields
    category: str | None = None
    recommended_products: list[str] | None = None
    reason: str | None = None
