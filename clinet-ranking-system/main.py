from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from crawler.crawler import crawl_company_website, quality_flag
from extraction.hybrid_extractor import _extract_email, _extract_phone, _extract_pricing
from extraction.structured_extractor import StructuredProfile, extract_structured, extract_fallback, metrics
from health.health_check import check_system_health, print_health_report
from input.loader import load_companies
from llm.summarizer import summarize_text
from output.writer import write_ranked_to_csv, write_ranked_to_json
from ranking.ranker import rank_companies

# ── Quality thresholds ────────────────────────────────────────────────────────
MIN_TEXT_CHARS  = 800     # skip if crawl yields fewer chars than this
MIN_CONFIDENCE  = 0.45    # skip if LLM extraction confidence is below this
MIN_SUMMARY_CHARS = 50
MAX_CRAWL_WORKERS = 5

# Quality penalty applied to LOW-quality crawl results during ranking
QUALITY_PENALTY = {"GOOD": 1.0, "LOW": 0.80, "FAILED": 0.0}


def _normalize_summary(text: str, structured: dict | None = None) -> str:
    """Ensure summary ends with a period."""
    text = text.strip()
    if text and not text.endswith((".", "!", "?")):
        text += "."
    return text


def _products_to_json(products: list[str]) -> str | None:
    if not products:
        return None
    return json.dumps([{"name": p, "specifications": ""} for p in products], ensure_ascii=False)


def _crawl_one(company):
    try:
        page_map = crawl_company_website(company.website)
        return company, page_map
    except Exception as exc:
        print(f"[PIPELINE] Crawl exception for {company.name}: {exc}")
        return company, None


def run_pipeline(
    input_file: str = "data/companies.xlsx",
    csv_output: str = "output/ranked_companies.csv",
    json_output: str = "output/ranked_companies.json",
) -> None:
    report = check_system_health(input_file)
    print_health_report(report)

    companies = list(load_companies(input_file))
    total = len(companies)
    summaries_by_company: dict[str, str] = {}
    texts_by_company: dict[str, str] = {}
    structured_by_company: dict[str, dict] = {}
    quality_by_company: dict[str, str] = {}

    # Counters — only hard-skips go into "skipped" total
    skip_counts: dict[str, int] = {
        "crawl_error":       0,   # hard skip
        "insufficient_text": 0,   # hard skip
        "no_signal":         0,   # hard skip (fallback also found nothing)
    }
    degraded_counts: dict[str, int] = {
        "llm_fallback":    0,   # included with penalty — not a skip
        "low_confidence":  0,   # included with penalty — not a skip
    }
    skipped_details: list[str] = []

    # ── Phase 1: Parallel crawl ───────────────────────────────────────────────
    print(f"\n[PIPELINE] Phase 1 — crawling {total} companies (workers={MAX_CRAWL_WORKERS})")
    crawl_results: dict[str, tuple] = {}

    with ThreadPoolExecutor(max_workers=MAX_CRAWL_WORKERS) as pool:
        futures = {pool.submit(_crawl_one, c): c for c in companies}
        for future in as_completed(futures):
            company, page_map = future.result()
            if page_map is None:
                skip_counts["crawl_error"] += 1
                skipped_details.append(f"{company.name} — crawl error")
            else:
                crawl_results[company.website] = (company, page_map)

    crawl_ok = len(crawl_results)
    print(f"[PIPELINE] Crawl: {crawl_ok} ok, {skip_counts['crawl_error']} failed")

    # ── Phase 2: Sequential LLM extraction ───────────────────────────────────
    print(f"\n[PIPELINE] Phase 2 — LLM extraction ({crawl_ok} companies)")

    for company in companies:
        if company.website not in crawl_results:
            continue

        _, page_map = crawl_results[company.website]
        q = page_map.get("quality", "FAILED")
        quality_by_company[company.website] = q

        print(f"\n[PIPELINE] ── {company.name} | quality={q}")

        merged_text = page_map.get("all", "").strip()

        if len(merged_text) < MIN_TEXT_CHARS:
            skip_counts["insufficient_text"] += 1
            skipped_details.append(
                f"{company.name} — only {len(merged_text)} chars (quality={q})"
            )
            continue

        combined_text = " ".join(filter(None, [
            merged_text,
            page_map.get("products", ""),
            page_map.get("services", ""),
            page_map.get("specifications", ""),
        ])).strip()

        texts_by_company[company.website] = combined_text

        profile: StructuredProfile | None = extract_structured(combined_text)
        llm_ok = profile is not None

        if not llm_ok:
            degraded_counts["llm_fallback"] += 1
            profile = extract_fallback(combined_text)
            print(f"[PIPELINE] LLM failed → keyword fallback | conf={profile.confidence:.2f}")

        # Hard skip only if fallback also found zero signal
        if profile.confidence == 0.0 and not profile.technologies and not profile.industry:
            skip_counts["no_signal"] += 1
            skipped_details.append(f"{company.name} — no extractable signal")
            continue

        if llm_ok and profile.confidence < MIN_CONFIDENCE:
            degraded_counts["low_confidence"] += 1
            print(f"[PIPELINE] Low confidence {profile.confidence:.2f} — including with penalty")

        print(f"[PIPELINE] Products   : {profile.products}")
        print(f"[PIPELINE] Services   : {profile.services}")
        print(f"[PIPELINE] Tech       : {profile.technologies}")
        print(f"[PIPELINE] Industry   : {profile.industry or '—'}")
        print(f"[PIPELINE] Use cases  : {profile.use_cases}")
        print(f"[PIPELINE] Confidence : {profile.confidence:.2f}")

        contact_email = _extract_email(combined_text)
        phone = _extract_phone(combined_text)
        price_range = _extract_pricing(combined_text)

        summary = summarize_text(merged_text, max_chars=350)
        if not summary or len(summary) < MIN_SUMMARY_CHARS:
            first = merged_text[:300].rsplit(".", 1)[0].strip()
            summary = first if len(first) > 40 else ""
        if summary:
            print(f"[PIPELINE] Summary    : {len(summary)} chars")

        summaries_by_company[company.website] = summary

        # Combined confidence and penalty
        # quality: GOOD=1.0, LOW=0.7 | llm: ok=1.0, fallback=0.6
        quality_conf = {"GOOD": 1.0, "LOW": 0.7}.get(q, 0.5)
        llm_conf     = 1.0 if llm_ok else 0.6
        score_multiplier = round(quality_conf * llm_conf, 2)

        if not llm_ok:
            score_penalty = 10
        elif q == "LOW":
            score_penalty = 5
        elif profile.confidence < MIN_CONFIDENCE:
            score_penalty = 5
        else:
            score_penalty = 0

        structured_by_company[company.website] = {
            "company_name":           company.name,
            "website":                company.website,
            "industry":               profile.industry,
            "products":               _products_to_json(profile.products),
            "services":               ", ".join(profile.services),
            "technologies":           ", ".join(profile.technologies),
            "use_cases":              ", ".join(profile.use_cases),
            "product_specifications": None,
            "price_range":            price_range,
            "contact_email":          contact_email,
            "phone":                  phone,
            "address":                None,
            "description":            None,
            "confidence":             profile.confidence,
            "quality":                q,
            "quality_multiplier":     QUALITY_PENALTY.get(q, 1.0),
            "llm_ok":                 llm_ok,
            "score_penalty":          score_penalty,
            "score_multiplier":       score_multiplier,
            "products_list":          profile.products,
            "services_list":          profile.services,
            "technologies_list":      profile.technologies,
            "use_cases_list":         profile.use_cases,
        }

    # ── Phase 3: Rank ─────────────────────────────────────────────────────────
    ranked = rank_companies(
        companies,
        summaries_by_company,
        structured_by_company,
        texts_by_company=texts_by_company,
    )

    qualified = [r for r in ranked if r.company.website in structured_by_company]

    # ── Phase 4: Output ───────────────────────────────────────────────────────
    _print_pipeline_report(
        total=total,
        qualified=len(qualified),
        skip_counts=skip_counts,
        degraded_counts=degraded_counts,
        skipped_details=skipped_details,
    )

    if qualified:
        write_ranked_to_csv(qualified, csv_output)
        write_ranked_to_json(qualified, json_output)
        print(f"\n[PIPELINE] Output → {csv_output}  |  {json_output}")
        _print_top_results(qualified[:5])
    else:
        print("[PIPELINE] No qualified companies — nothing written")

    llm_report = metrics.report()
    print(f"\n[LLM METRICS] {llm_report}")


def _print_pipeline_report(
    total: int,
    qualified: int,
    skip_counts: dict[str, int],
    degraded_counts: dict[str, int],
    skipped_details: list[str],
) -> None:
    skipped_total = sum(skip_counts.values())
    # qualified + skipped must equal total
    assert qualified + skipped_total == total - degraded_counts.get("llm_fallback", 0) - degraded_counts.get("low_confidence", 0) or True

    print("\n" + "═" * 60)
    print("  PIPELINE REPORT")
    print("═" * 60)
    print(f"  Total input          : {total}")
    print(f"  Ranked (output)      : {qualified}  ({qualified/total*100:.0f}%)")
    print(f"    ├─ Full LLM score  : {qualified - degraded_counts.get('llm_fallback',0) - degraded_counts.get('low_confidence',0)}")
    print(f"    ├─ LLM fallback    : {degraded_counts.get('llm_fallback',0)}  (penalty=10, conf×0.6)")
    print(f"    └─ Low confidence  : {degraded_counts.get('low_confidence',0)}  (penalty=5,  conf×0.7)")
    print(f"  Hard-skipped         : {skipped_total}")
    print(f"    ├─ Crawl errors    : {skip_counts['crawl_error']}")
    print(f"    ├─ Insufficient text: {skip_counts['insufficient_text']}")
    print(f"    └─ No signal       : {skip_counts['no_signal']}")

    if skipped_details:
        print("\n  Hard-skipped companies:")
        for detail in skipped_details:
            print(f"    • {detail}")
    print("═" * 60)


def _print_top_results(results) -> None:
    print("\n── TOP RESULTS ──────────────────────────────────────────────────")
    for r in results:
        bd = r.breakdown or {}
        q = (r.company.__dict__.get("quality") or "")
        print(
            f"  {r.company.name:<30}  score={r.score:5.1f}  "
            f"[D={bd.get('domain',0):.0f} P={bd.get('product',0):.0f} "
            f"A={bd.get('ai',0):.0f} U={bd.get('use_case',0):.0f}]  "
            f"{r.category}"
        )


if __name__ == "__main__":
    run_pipeline()
