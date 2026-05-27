from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import requests


@dataclass
class HealthReport:
    input_file_exists: bool
    spreadsheet_readable: bool
    company_count: int
    internet_connectivity: bool


def check_system_health(input_path: str = "data/companies.xlsx") -> HealthReport:
    path = Path(input_path)
    input_file_exists = path.exists()

    spreadsheet_readable = False
    company_count = 0
    if input_file_exists:
        try:
            df = pd.read_excel(path)
            spreadsheet_readable = True
            company_count = len(df)
        except Exception:
            spreadsheet_readable = False

    internet_connectivity = False
    if os.getenv("CRS_OFFLINE_MODE", "0").strip() != "1":
        try:
            requests.get("https://www.google.com", timeout=5)
            internet_connectivity = True
        except Exception:
            internet_connectivity = False

    return HealthReport(
        input_file_exists=input_file_exists,
        spreadsheet_readable=spreadsheet_readable,
        company_count=company_count,
        internet_connectivity=internet_connectivity,
    )


def print_health_report(report: HealthReport) -> None:
    print("\n========== SYSTEM HEALTH ==========")
    print("Input file exists" if report.input_file_exists else "Input file missing")
    print(
        f"Spreadsheet {'readable' if report.spreadsheet_readable else 'error'}"
        + (f" | Total companies: {report.company_count}" if report.spreadsheet_readable else "")
    )
    print(
        "Internet connectivity OK"
        if report.internet_connectivity
        else "Internet connectivity problem"
    )
    print("===================================\n")
