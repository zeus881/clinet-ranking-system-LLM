from __future__ import annotations

from pathlib import Path
import re
from typing import List

import pandas as pd

from models.schemas import Company

REQUIRED_COLUMNS = {"Company", "Website"}
COMPANY_COLUMN_ALIASES = ("Company", "Company Name")
SCHEME_PREFIX_RE = re.compile(r"^https?://", re.IGNORECASE)
WWW_PREFIX_RE = re.compile(r"^www\.", re.IGNORECASE)


def load_companies(file_path: str) -> List[Company]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {file_path}")

    df = pd.read_excel(path)
    company_column = _resolve_company_column(df.columns)
    if company_column is None or "Website" not in df.columns:
        raise ValueError(
            "Spreadsheet must contain required columns: "
            + ", ".join(sorted(REQUIRED_COLUMNS))
        )

    # Keep only non-empty rows.
    records = (
        df.loc[:, [company_column, "Website"]]
        .rename(columns={company_column: "Company"})
        .dropna(subset=["Company", "Website"])
        .assign(
            Company=lambda x: x["Company"].astype(str).str.strip(),
            Website=lambda x: x["Website"].astype(str).str.strip(),
        )
    )
    records = records[(records["Company"] != "") & (records["Website"] != "")]
    records = records.assign(
        _website_key=lambda x: x["Website"].map(_normalize_website_for_key),
        _company_key=lambda x: x["Company"].str.lower(),
    ).drop_duplicates(subset=["_company_key", "_website_key"], keep="first")

    return [Company(name=row.Company, website=row.Website) for row in records.itertuples()]


def _normalize_website_for_key(website: str) -> str:
    normalized = (website or "").strip().lower()
    normalized = SCHEME_PREFIX_RE.sub("", normalized)
    normalized = WWW_PREFIX_RE.sub("", normalized)
    normalized = normalized.split("/", 1)[0]
    return normalized


def _resolve_company_column(columns) -> str | None:
    for alias in COMPANY_COLUMN_ALIASES:
        if alias in columns:
            return alias
    return None
