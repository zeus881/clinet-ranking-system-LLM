from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from flask import Flask, jsonify

try:
    from flask_cors import CORS
except Exception:  # pragma: no cover
    CORS = None


BASE_DIR = Path(__file__).resolve().parents[1]
CSV_PATH = BASE_DIR / "output" / "ranked_companies.csv"
JSON_PATH = BASE_DIR / "output" / "ranked_companies.json"
PIPELINE_ENTRY = BASE_DIR / "main.py"
COLUMN_ORDER = [
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
    "summary",
    "breakdown",
    "confidence",
    "recommended_products",
    "reason",
]
REQUIRED_COLUMNS = {"company_name", "website", "score"}

app = Flask(__name__)

if CORS is not None:
    CORS(app)


pipeline_status: dict[str, Any] = {
    "running": False,
    "last_run": None,
}
_pipeline_process: subprocess.Popen[str] | None = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sync_pipeline_state() -> None:
    global _pipeline_process

    if _pipeline_process is None:
        return

    return_code = _pipeline_process.poll()
    if return_code is None:
        pipeline_status["running"] = True
        return

    pipeline_status["running"] = False
    pipeline_status["last_run"] = _utc_now_iso()
    print(f"[API] Pipeline finished with exit code {return_code}")
    _pipeline_process = None


def run_pipeline_async() -> bool:
    global _pipeline_process

    _sync_pipeline_state()
    if pipeline_status["running"]:
        print("[API] Pipeline already running, skipping duplicate start")
        return False

    print("[API] Running pipeline...")
    _pipeline_process = subprocess.Popen(
        [sys.executable, str(PIPELINE_ENTRY)],
        cwd=BASE_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    pipeline_status["running"] = True
    return True


def is_data_stale(file_path: Path, max_age: int = 3600) -> bool:
    if not file_path.exists():
        return True

    try:
        age_seconds = time.time() - file_path.stat().st_mtime
    except OSError:
        return True

    return age_seconds > max_age


def load_data(file_path: Path) -> list[dict[str, Any]]:
    """Load ranked companies from JSON (preferred) or fall back to CSV."""
    # Prefer JSON — it has proper types (lists, dicts) not stringified CSV
    if JSON_PATH.exists():
        try:
            raw = json.loads(JSON_PATH.read_text(encoding="utf-8"))
            records = _normalize_json_records(raw)
            print(f"[API] Loaded {len(records)} rows from JSON")
            return records
        except Exception as exc:
            print(f"[API] JSON load failed ({exc}), falling back to CSV")

    if not file_path.exists():
        return []

    try:
        dataframe = pd.read_csv(file_path)
    except (pd.errors.EmptyDataError, FileNotFoundError):
        return []
    except Exception as exc:
        raise RuntimeError(f"Failed to load CSV: {exc}") from exc

    if dataframe.empty:
        return []

    dataframe.columns = (
        dataframe.columns.str.strip().str.lower().str.replace(" ", "_", regex=False)
    )
    missing_columns = REQUIRED_COLUMNS - set(dataframe.columns)
    if missing_columns:
        raise ValueError("Missing required columns: " + ", ".join(sorted(missing_columns)))

    # Keep only columns we know about, fill gaps with defaults
    available = [c for c in COLUMN_ORDER if c in dataframe.columns]
    response_frame = dataframe.loc[:, available].copy()
    text_columns = [c for c in response_frame.columns if c not in ("score", "confidence")]
    for column in text_columns:
        response_frame[column] = response_frame[column].fillna("").astype(str).str.strip()

    response_frame["company_name"] = response_frame["company_name"].replace("", "Unknown Company")
    response_frame["score"] = pd.to_numeric(response_frame["score"], errors="coerce").fillna(0.0).round(2)
    response_frame = response_frame.sort_values(by="score", ascending=False, na_position="last")

    print(f"[API] Loaded {len(response_frame)} rows from CSV")
    return response_frame.to_dict(orient="records")


def _normalize_json_records(raw: list[dict]) -> list[dict[str, Any]]:
    """Normalise JSON output rows into a consistent API-friendly shape."""
    out = []
    for row in raw:
        out.append({
            "company_name":         row.get("name") or row.get("company_name") or "Unknown",
            "website":              row.get("website", ""),
            "score":                round(float(row.get("score") or 0), 2),
            "category":             row.get("category") or "Low Potential",
            "industry":             row.get("industry") or "Other",
            "products":             row.get("products") or [],      # list[str]
            "services":             row.get("services") or [],
            "technologies":         row.get("technologies") or [],
            "use_cases":            row.get("use_cases") or [],
            "product_specifications": row.get("product_specifications") or [],
            "price_range":          row.get("price_range") or "",
            "contact_email":        row.get("contact_email") or "",
            "phone":                row.get("phone") or "",
            "summary":              row.get("summary") or "No summary available.",
            "breakdown":            row.get("breakdown") or {},     # dict
            "confidence":           round(float(row.get("confidence") or 0), 4),
            "recommended_products": row.get("recommended_products") or [],
            "reason":               row.get("reason") or "",
        })
    return sorted(out, key=lambda r: r["score"], reverse=True)


def _json_response(payload: dict[str, Any], status_code: int, started_at: float):
    response = jsonify(payload)
    response.status_code = status_code
    response._elapsed_time = time.perf_counter() - started_at
    return response


@app.after_request
def add_response_metadata(response):
    if CORS is None:
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET,OPTIONS"

    elapsed = getattr(response, "_elapsed_time", None)
    if elapsed is not None:
        print(f"[API] Response time: {elapsed:.3f}s")
    return response


@app.get("/companies")
def get_companies():
    started_at = time.perf_counter()
    try:
        _sync_pipeline_state()

        data_exists = JSON_PATH.exists() or CSV_PATH.exists()
        if not data_exists:
            run_pipeline_async()
            return _json_response(
                {
                    "status": "accepted",
                    "message": "Pipeline started in background. Data is not ready yet.",
                    "data": [],
                },
                202,
                started_at,
            )

        primary_path = JSON_PATH if JSON_PATH.exists() else CSV_PATH
        if is_data_stale(primary_path):
            print("[API] Data stale, refreshing...")
            run_pipeline_async()

        data = load_data(CSV_PATH)
        if not data and not pipeline_status["running"]:
            run_pipeline_async()
            return _json_response(
                {
                    "status": "accepted",
                    "message": "Pipeline started in background. Data is not ready yet.",
                    "data": [],
                },
                202,
                started_at,
            )

        print("[API] Returning data...")
        return _json_response({"status": "success", "data": data}, 200, started_at)
    except Exception as exc:  # pragma: no cover
        return _json_response(
            {
                "status": "error",
                "message": str(exc),
            },
            500,
            started_at,
        )


@app.get("/refresh")
def refresh_pipeline():
    started_at = time.perf_counter()
    try:
        run_pipeline_async()
        return _json_response(
            {
                "status": "success",
                "message": "Pipeline started in background",
            },
            200,
            started_at,
        )
    except Exception as exc:  # pragma: no cover
        return _json_response(
            {
                "status": "error",
                "message": str(exc),
            },
            500,
            started_at,
        )


@app.get("/status")
def get_status():
    started_at = time.perf_counter()
    try:
        _sync_pipeline_state()
        return _json_response(
            {
                "running": pipeline_status["running"],
                "last_run": pipeline_status["last_run"],
            },
            200,
            started_at,
        )
    except Exception as exc:  # pragma: no cover
        return _json_response(
            {
                "status": "error",
                "message": str(exc),
            },
            500,
            started_at,
        )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
