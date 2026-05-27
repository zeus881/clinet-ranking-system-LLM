from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from models.output_schema import OutputCompanyRecord
from models.schemas import RankedCompany

FIELDNAMES = [
    "company_name",
    "website",
    "score",
    "category",
    "industry",
    "products",
    "services",
    "technologies",
    "use_cases",
    "product_specifications",
    "price_range",
    "contact_email",
    "phone",
    "address",
    "description",
    "summary",
    "breakdown",
    "confidence",
    "recommended_products",
    "reason",
]


def write_ranked_to_csv(items: Iterable[RankedCompany], output_path: str) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for item in items:
            writer.writerow(_to_csv_row(_validate_record(item)))


def write_ranked_to_json(items: Iterable[RankedCompany], output_path: str) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = [_to_json_row(_validate_record(item)) for item in items]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _split_values(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _parse_products(value: str | None) -> list[dict[str, str]]:
    """Accept JSON string or comma-separated plain string."""
    if not value:
        return []
    raw = value.strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            normalized: list[dict[str, str]] = []
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                specs = str(item.get("specifications", "")).strip()
                if name:
                    normalized.append({"name": name, "specifications": specs})
            return normalized
    except Exception:
        pass
    return [{"name": part, "specifications": ""} for part in _split_values(raw)]


def _validate_record(item: RankedCompany) -> OutputCompanyRecord:
    return OutputCompanyRecord(
        company_name=item.company.name,
        website=item.company.website,
        industry=item.industry,
        products=_parse_products(item.products),
        services=_split_values(item.services),
        product_specifications=_split_values(item.product_specifications),
        technologies=_split_values(item.technologies),
        use_cases=list(item.use_cases or []),
        price_range=item.price_range,
        contact_email=item.contact_email,
        phone=item.phone,
        address=item.address,
        description=item.description,
        summary=item.summary,
        score=round(float(item.score), 4),
        breakdown=item.breakdown or {},
        confidence=round(float(item.confidence), 4),
        category=item.category,
        recommended_products=item.recommended_products,
        reason=item.reason,
    )


def _to_csv_row(record: OutputCompanyRecord) -> dict[str, str | float]:
    return {
        "company_name": record.company_name,
        "website": record.website,
        "score": record.score,
        "category": record.category or "",
        "industry": record.industry or "",
        "products": json.dumps(record.products, ensure_ascii=False),
        "services": ", ".join(record.services),
        "technologies": ", ".join(record.technologies),
        "use_cases": ", ".join(record.use_cases),
        "product_specifications": ", ".join(record.product_specifications),
        "price_range": record.price_range or "",
        "contact_email": record.contact_email or "",
        "phone": record.phone or "",
        "address": record.address or "",
        "description": record.description or "",
        "summary": record.summary or "",
        "breakdown": json.dumps(record.breakdown, ensure_ascii=False),
        "confidence": record.confidence,
        "recommended_products": ", ".join(record.recommended_products or []),
        "reason": record.reason or "",
    }


def _to_json_row(record: OutputCompanyRecord) -> dict:
    return {
        "name": record.company_name,
        "website": record.website,
        "score": record.score,
        "category": record.category,
        "breakdown": record.breakdown,
        "confidence": record.confidence,
        "industry": record.industry,
        "products": [p["name"] for p in record.products],
        "services": record.services,
        "technologies": record.technologies,
        "use_cases": record.use_cases,
        "product_specifications": record.product_specifications,
        "price_range": record.price_range,
        "contact_email": record.contact_email,
        "phone": record.phone,
        "summary": record.summary,
        "recommended_products": record.recommended_products,
        "reason": record.reason,
    }
