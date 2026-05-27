# Rebhu Computing — Client Ranking System: Full System Design

## Overview

The Client Ranking System automatically discovers, crawls, analyses, and ranks potential client companies for **Rebhu Computing** — a company that sells AI/autonomous compute hardware. Given a spreadsheet of company names and websites, the pipeline outputs a ranked list of companies sorted by their likelihood of needing Rebhu's products.

The system answers: *"Which of these companies most urgently need real-time AI/autonomous compute?"*

---

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                        INPUT LAYER                                   │
│  data/companies.xlsx  ──►  input/loader.py  ──►  [Company objects]  │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      HEALTH CHECK                                    │
│  health/health_check.py  — validates file, checks Ollama, disk      │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│                 PHASE 1 — PARALLEL CRAWL (5 workers)                 │
│  crawler/crawler.py                                                  │
│  • Exponential backoff retry (1s, 2s, 4s)                           │
│  • Two header profiles: standard → browser-mimicry on 403           │
│  • Skips: legal, blog, auth, careers, pricing, contact pages        │
│  • Quality flags: GOOD ≥1000 chars / LOW ≥200 / FAILED              │
│  • Returns: {all, products, services, specifications, quality}       │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│              PHASE 2 — SEQUENTIAL LLM EXTRACTION                     │
│  extraction/structured_extractor.py                                  │
│                                                                      │
│  Path A — Ollama LLM (llama3:latest, timeout=25s):                  │
│    • 3-tier text filter: CamelCase/TitleCase → keyword → other      │
│    • Attempt 1: 900 chars   Attempt 2: 600 chars                    │
│    • Anti-hallucination: product names must appear in source         │
│    • Returns StructuredProfile (products, services, tech,            │
│               industry, use_cases, confidence)                       │
│                                                                      │
│  Path B — Keyword Fallback (instant, no LLM):                       │
│    • Triggered when Ollama times out or returns bad JSON             │
│    • Confidence capped at 0.40                                       │
│    • Applied penalty: multiplier×0.60, score−10                     │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│                  PHASE 3 — SCORING & RANKING                         │
│  ranking/ranker.py                                                   │
│                                                                      │
│  FinalScore = max(0, min(BaseScore × multiplier − penalty, 100))    │
│  BaseScore  = 0.35·D + 0.25·P + 0.20·A + 0.20·U                   │
│                                                                      │
│   D = Domain match        (target sectors: robotics, defense, UAV)  │
│   P = Product relevance   (do their products need edge compute?)    │
│   A = AI capability       (computer vision, SLAM, deep learning)    │
│   U = Use-case alignment  (warehouse automation, drone delivery…)   │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   PHASE 4 — OUTPUT                                   │
│  output/writer.py                                                    │
│  • output/ranked_companies.csv                                       │
│  • output/ranked_companies.json                                      │
│  • Served via Flask REST API (api/app.py)                            │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Folder Structure

```
clinet-ranking-system/
│
├── main.py                          # Pipeline orchestrator
│
├── data/
│   └── companies.xlsx               # Input: company list (Name + Website)
│
├── input/
│   └── loader.py                    # Reads Excel, emits Company objects
│
├── health/
│   └── health_check.py              # Pre-flight: file, Ollama, disk checks
│
├── crawler/
│   └── crawler.py                   # Web crawler with retry + quality flags
│
├── extraction/
│   ├── structured_extractor.py      # LLM + keyword-fallback extractor
│   ├── company_extraction.py        # Helpers: regex email/phone/price
│   ├── hybrid_extractor.py          # _extract_email, _extract_phone, _extract_pricing
│   └── schema_extractor.py          # Prompt templates, schema definitions
│
├── llm/
│   └── summarizer.py                # Sentence-extraction summariser (no LLM)
│
├── ranking/
│   └── ranker.py                    # Scoring formula + rank_companies()
│
├── models/
│   ├── schemas.py                   # Company, RankedCompany dataclasses
│   └── output_schema.py             # JSON output row schema
│
├── output/
│   ├── writer.py                    # write_ranked_to_csv / write_ranked_to_json
│   ├── ranked_companies.csv         # Pipeline output (gitignored in prod)
│   └── ranked_companies.json        # Pipeline output
│
├── api/
│   └── app.py                       # Flask API: /companies /refresh /status
│
├── processing/
│   └── text_processing.py           # merge_page_texts, clean_text helpers
│
├── frontend/
│   ├── index.html                   # Single-page dashboard
│   ├── app.js                       # Fetch + render ranked table
│   └── styles.css                   # Responsive styling
│
└── tests/
    ├── test_phase2_crawler_extraction.py
    ├── test_phase3_structured_product_extraction.py
    ├── test_phase4_llm_strict_extraction.py
    ├── test_phase6_api_auto_pipeline.py
    ├── test_phase7_integration_end_to_end.py
    ├── test_phase8_structured_products_formatting.py
    ├── test_phase9_llm_cleaning.py
    ├── test_phase10_product_name_rules.py
    ├── test_phase11_industry_mapping.py
    └── test_schema.py
```

---

## Step-by-Step Data Flow

### Step 1 — Load Input

**File:** [input/loader.py](input/loader.py)

Reads `data/companies.xlsx` with pandas. Each row must have at minimum a `name` and `website` column. Returns an iterator of `Company` objects (defined in [models/schemas.py](models/schemas.py)).

```python
@dataclass
class Company:
    name: str
    website: str
```

Any row missing a website is silently skipped.

---

### Step 2 — Health Check

**File:** [health/health_check.py](health/health_check.py)

Before starting the pipeline, the system checks:

| Check | What it does |
|---|---|
| Input file | Does `companies.xlsx` exist and is it non-empty? |
| Ollama | Is `http://localhost:11434` reachable? |
| Disk space | Is there at least 100 MB free? |
| Output dir | Does `output/` exist (creates if not)? |

The health report is printed to the terminal. A missing Ollama is a **warning** (not a failure) — the pipeline continues using keyword-fallback extraction.

---

### Step 3 — Parallel Web Crawl

**File:** [crawler/crawler.py](crawler/crawler.py)

Crawls each company's website using a `ThreadPoolExecutor` with 5 workers — parallelism is safe here because crawling is I/O-bound (waiting for HTTP responses).

**Per-company crawl process:**

1. **Normalise URL** — adds `https://` if missing, strips trailing slash and query params.
2. **Fetch homepage** with exponential backoff:
   - Attempt 1: standard browser headers
   - Attempt 2: upgraded headers (adds `Referer: google.com`, `Sec-Fetch-*` headers) to bypass 403s
   - Attempt 3: same upgraded headers after 4s wait
3. **Extract text** — strips `<script>`, `<style>`, `<nav>`, `<footer>`. Extracts meta descriptions, headings (h1–h3), paragraphs, list items. Normalises whitespace. Caps at 4000 chars per page.
4. **Extract section-specific text** — CSS selectors for `[class*='product']`, `[class*='service']`, `[class*='solution']` nodes.
5. **Extract specs** — table rows and list items as structured data.
6. **Discover links** — scores internal links by path hints (`/about`, `/products`, `/solutions`, etc.). Enqueues top-scoring links up to `MAX_PAGES=8`.
7. **Quality flag** the merged text: `GOOD` (≥1000 chars), `LOW` (≥200 chars), `FAILED` (<200 chars).

**Pages that are always skipped:**

`blog`, `news`, `press`, `careers`, `jobs`, `login`, `pricing`, `contact`, `support`, `terms`, `privacy`, `legal`, `.pdf`, `.docx`, `.png`, `.xlsx`, `.zip`, ...

**Return format:**
```python
{
    "all":            "merged text from all pages (≤4000 chars)",
    "products":       "text from product/solution CSS sections",
    "services":       "text from service CSS sections",
    "specifications": "table rows and spec lists",
    "quality":        "GOOD"  # or "LOW" or "FAILED"
}
```

---

### Step 4 — LLM Extraction (or Keyword Fallback)

**File:** [extraction/structured_extractor.py](extraction/structured_extractor.py)

This is the most complex stage. It runs **sequentially** (not parallel) because Ollama is a single-process server that would bottleneck under concurrent requests anyway.

#### Hard Skips (before extraction)

If `len(merged_text) < 800` chars → the company is **hard-skipped** (too little data to extract anything useful).

#### LLM Path — `extract_structured(text)`

1. **3-tier text filter** (`_filter_relevant()`): selects the most signal-rich sentences first:
   - **Tier 1** — sentences containing CamelCase (`SwarmOS`), acronym+number (`EZ10`), or Title Case pairs (`Fast DDS`) — these almost always contain product names.
   - **Tier 2** — sentences containing any of 50+ domain keywords (`autonomous`, `lidar`, `robotics`, `warehouse`, `edge AI`, …).
   - **Tier 3** — any remaining sentences.
   - Tiers are filled in order until the char budget is reached.

2. **LLM call to Ollama** (`llama3:latest`):
   - Attempt 1: 900-char filtered text, 25s timeout
   - Attempt 2 (on timeout/bad JSON): 600-char text, 25s timeout
   - Prompt asks for JSON with keys: `products`, `services`, `technologies`, `industry`, `use_cases`, `confidence`

3. **Anti-hallucination check** (`_product_in_text()`): each returned product name is verified to have at least one identifying word present in the original source text. Products that fail this check are discarded.

4. **Post-processing**:
   - `_infer_industry()` — if LLM returned no industry, maps keywords → 26 canonical industry labels
   - `_infer_use_cases()` — supplements with keyword-matched use cases from 15 known patterns
   - `_rescue_products_from_text()` — if LLM returned `products:[]`, scans for capitalised brand tokens near product-context words (e.g., "platform", "system", "solution")

**Returns:** `StructuredProfile` with `confidence` in `[0.0, 1.0]`.

#### Keyword Fallback Path — `extract_fallback(text)`

Used when Ollama is unreachable, times out twice, or returns malformed JSON.

- Runs `_infer_technologies()`, `_rescue_products_from_text()`, `_infer_industry()`, `_infer_use_cases()` purely via regex/keyword matching — no network call, completes in milliseconds.
- Confidence is capped at **0.40** (lower bound for LLM-extracted profiles is 0.45).
- Company is **included in output** but receives a score penalty.

#### Hard Skip — No Signal

If `profile.confidence == 0.0` AND no technologies AND no industry found → **hard-skipped** (truly unextractable).

#### Penalty Table

| Situation | Score multiplier | Score penalty |
|---|---|---|
| LLM succeeded, quality=GOOD, confidence≥0.45 | 1.0 | 0 |
| LLM succeeded, quality=LOW | 0.70 | −5 |
| LLM succeeded, confidence<0.45 | 0.70 | −5 |
| LLM failed → keyword fallback | 0.60 | −10 |

Combined confidence:
```python
quality_conf  = {"GOOD": 1.0, "LOW": 0.7}.get(quality, 0.5)
llm_conf      = 1.0 if llm_ok else 0.6
score_multiplier = quality_conf × llm_conf
```

---

### Step 5 — Summarisation

**File:** [llm/summarizer.py](llm/summarizer.py)

Purely sentence-extraction — no LLM call. Splits text on sentence boundaries, keeps the first 3 sentences that are ≥40 chars long, truncates to `max_chars=350`.

This was previously an Ollama call with a 120s timeout — removed entirely to avoid the third Ollama bottleneck per company.

---

### Step 6 — Scoring & Ranking

**File:** [ranking/ranker.py](ranking/ranker.py)

#### The Formula

```
FinalScore = max(0, min(BaseScore × multiplier − penalty, 100))

BaseScore = 0.35·D + 0.25·P + 0.20·A + 0.20·U
```

Each raw factor (D, P, A, U) is calculated independently on a 0–100 scale, then weighted.

#### Factor D — Domain Match (weight: 35%)

Checks whether the company operates in Rebhu's target sectors.

| Signal strength | Keywords | Points each |
|---|---|---|
| Strong | autonomous, robotics, drone, UAV, defense, military, self-driving, navigation | +28 |
| Medium | automation, manufacturing, warehouse, logistics, aerospace, edge computing, embedded | +10 |

`D = min(strong×28 + medium×10, 100)`

#### Factor P — Product Relevance (weight: 25%)

Checks whether their products are the type that need real-time AI compute.

| Signal strength | Keywords | Points each |
|---|---|---|
| Strong | robotics, drone, UAV, autonomous vehicle, AGV, AMR, navigation system, vision system, LiDAR | +25 |
| Medium | AI platform, computer vision platform, control system, embedded system, inference engine | +10 |

Plus a **named products bonus**: `min(count_of_products_with_name_longer_than_3_chars × 8, 24)`.

`P = min(strong×25 + medium×10 + named_bonus, 100)`

A company with 3+ real product names gets up to +24 pts — rewarding companies with actual products over companies that just talk about being an "AI company".

#### Factor A — AI Capability (weight: 20%)

Checks how deeply AI/ML is embedded in their stack.

| Signal strength | Keywords | Points each |
|---|---|---|
| Strong | computer vision, deep learning, neural network, LiDAR, sensor fusion, SLAM, edge AI, object detection | +22 |
| Medium | artificial intelligence, machine learning, inference, perception, reinforcement learning | +8 |

`A = min(strong×22 + medium×8, 100)`

#### Factor U — Use-Case Alignment (weight: 20%)

Checks whether their actual application domain maps to Rebhu's deployment targets.

| Use case | Score |
|---|---|
| autonomous navigation | 100 |
| drone delivery | 100 |
| defense | 100 |
| SLAM | 95 |
| warehouse automation | 95 |
| search and rescue | 90 |
| last-mile delivery | 85 |
| factory automation | 82 |
| logistics automation | 82 |
| industrial inspection | 80 |
| mapping | 80 |
| surveillance | 78 |
| precision agriculture | 75 |
| fleet management | 70 |
| predictive maintenance | 68 |
| quality control | 65 |

`U = best matching use case score (0 if none match)`

#### Score Categories

| FinalScore | Category |
|---|---|
| ≥ 75 | High Potential |
| ≥ 55 | Good Potential |
| ≥ 35 | Moderate |
| < 35 | Low Potential |

#### Recommended Rebhu Products

Based on the company's profile, the ranker suggests which Rebhu products to pitch:

| Profile type | Recommended |
|---|---|
| robotics/drone/navigation | Autonomous Navigation System, Computer Vision Platform, Real-time Control Engine |
| AI/vision/deep learning | Computer Vision Platform, AI Inference Accelerator, Data Pipeline System |
| general automation | Automation Control System, Real-time Processing Platform, Edge Compute Module |
| other | Embedded Systems Framework, Real-time Compute Platform |

---

### Step 7 — Output

**File:** [output/writer.py](output/writer.py)

Writes two files after ranking:

#### CSV (`output/ranked_companies.csv`)

One row per company, columns: `rank`, `company_name`, `website`, `score`, `category`, `industry`, `products`, `services`, `technologies`, `use_cases`, `price_range`, `contact_email`, `phone`, `summary`, `confidence`, `quality`, `reason`.

#### JSON (`output/ranked_companies.json`)

Array of objects. Each object:
```json
{
  "name": "EasyMile",
  "website": "https://easymile.com",
  "score": 78.5,
  "category": "High Potential",
  "industry": "Autonomous Vehicles",
  "products": [{"name": "EZ10", "specifications": ""}],
  "services": "system integration, fleet management",
  "technologies": "computer vision, SLAM, LiDAR, sensor fusion",
  "use_cases": ["autonomous navigation", "last-mile delivery"],
  "summary": "EasyMile develops autonomous shuttles using AI-powered navigation.",
  "confidence": 0.82,
  "quality": "GOOD",
  "breakdown": {
    "domain": 28.0,
    "product": 25.0,
    "ai": 17.6,
    "use_case": 20.0
  },
  "recommended_products": ["Autonomous Navigation System", "Computer Vision Platform"],
  "reason": "Rebhu fit: domain match (Autonomous Vehicles); AI/vision capabilities; use case: autonomous navigation (score 78.5).",
  "contact_email": "info@easymile.com",
  "phone": null,
  "price_range": null
}
```

---

## REST API

**File:** [api/app.py](api/app.py)

A lightweight Flask server that serves the pipeline output.

| Endpoint | Method | Description |
|---|---|---|
| `/companies` | GET | Returns full ranked list from JSON file |
| `/companies?q=drone` | GET | Filters results by keyword search |
| `/refresh` | POST | Re-runs the pipeline, refreshes output files |
| `/status` | GET | Health info: last run time, company count, staleness |

The API reads from `output/ranked_companies.json` — it never blocks on a live pipeline run unless `/refresh` is called.

**Staleness check:** if the JSON file is older than 24 hours, `is_data_stale()` returns `True` and the `/status` endpoint reports it. The frontend can prompt users to refresh.

---

## Environment Modes

### Live Mode (default)

```bash
python main.py
```

- Crawls real websites
- Calls Ollama for LLM extraction
- Produces differentiated scores based on actual company data

### Sandbox / Offline Mode

```bash
CRS_OFFLINE_MODE=1 python main.py
```

- All crawl calls return mock data (same template for every company)
- Extraction runs keyword-fallback only (no Ollama)
- Useful for: CI/CD, unit tests, demonstrating the pipeline without internet access
- **Limitation:** all companies receive identical scores (same mock input → same output)

---

## Key Configuration Constants

| Constant | File | Default | Meaning |
|---|---|---|---|
| `MIN_TEXT_CHARS` | main.py | 800 | Hard-skip if crawl yields fewer chars |
| `MIN_CONFIDENCE` | main.py | 0.45 | Below this → include with penalty (not skip) |
| `MIN_SUMMARY_CHARS` | main.py | 50 | Fall back to first-sentence if summary too short |
| `MAX_CRAWL_WORKERS` | main.py | 5 | Parallel crawl threads |
| `LLM_TIMEOUT` | structured_extractor.py | 25 | Seconds before Ollama request is abandoned |
| `LLM_MAX_CHARS` | structured_extractor.py | 900 | First attempt input to Ollama |
| `LLM_RETRY_CHARS` | structured_extractor.py | 600 | Retry attempt input (shorter = faster) |
| `MAX_PAGES` | crawler.py | 8 | Max pages crawled per company |
| `MAX_TEXT_CHARS` | crawler.py | 4000 | Max chars kept per crawled page |
| `QUALITY_GOOD` | crawler.py | 1000 | Char threshold for GOOD quality flag |
| `QUALITY_LOW` | crawler.py | 200 | Char threshold for LOW quality flag |
| `REQUEST_TIMEOUT` | crawler.py | 10 | HTTP timeout per URL |

---

## Pipeline Report

After each run, the terminal prints a structured report:

```
════════════════════════════════════════════════════════════
  PIPELINE REPORT
════════════════════════════════════════════════════════════
  Total input          : 50
  Ranked (output)      : 43  (86%)
    ├─ Full LLM score  : 38
    ├─ LLM fallback    : 3   (penalty=10, conf×0.6)
    └─ Low confidence  : 2   (penalty=5,  conf×0.7)
  Hard-skipped         : 7
    ├─ Crawl errors    : 2
    ├─ Insufficient text: 4
    └─ No signal       : 1

  Hard-skipped companies:
    • Acme Corp — crawl error
    • Widget Ltd — only 312 chars (quality=LOW)
════════════════════════════════════════════════════════════
```

**Important:** `Ranked + Hard-skipped = Total input` always holds. Degraded companies (LLM fallback, low confidence) are **counted in Ranked**, not Skipped.

---

## LLM Metrics

The `_Metrics` class in [extraction/structured_extractor.py](extraction/structured_extractor.py) tracks session-level stats:

```
[LLM METRICS] calls=43 success=40 (93%) avg_time=14.2s retries=6 timeouts=3
```

Resets each pipeline run. Useful for diagnosing Ollama performance degradation.

---

## Test Coverage

47 tests across 11 files, all passing.

| Test file | What it covers |
|---|---|
| `test_phase2_crawler_extraction.py` | Fetch, HTML parsing, link extraction, quality flags |
| `test_phase3_structured_product_extraction.py` | 3-tier filter, product rescue, industry inference |
| `test_phase4_llm_strict_extraction.py` | Anti-hallucination check, fallback triggering |
| `test_phase6_api_auto_pipeline.py` | API endpoints, staleness, refresh trigger |
| `test_phase7_integration_end_to_end.py` | Full pipeline mock: crawl → extract → rank → API |
| `test_phase8_structured_products_formatting.py` | Product JSON serialisation format |
| `test_phase9_llm_cleaning.py` | Confidence capping, fallback confidence bounds |
| `test_phase10_product_name_rules.py` | CamelCase/TitleCase product name detection regex |
| `test_phase11_industry_mapping.py` | `_infer_industry()` keyword → label mapping |
| `test_schema.py` | JSON output schema (19 required keys) |
| `test_phase2_crawler_extraction.py` | Crawler retry logic, binary URL skip, offline mock |

Run all tests:
```bash
python -m pytest tests/ -v
```

---

## Known Limitations

| Limitation | Impact | Workaround |
|---|---|---|
| JavaScript-rendered sites | Crawler uses `requests` + BeautifulSoup — can't execute JS. Sites built entirely in React/Vue/Angular with no SSR return empty bodies. | FAILED quality flag → hard-skipped. Future: add Playwright/Selenium. |
| Ollama single-process | LLM extraction is sequential. 50 companies × ~14s avg = ~12 min. | Reduce `LLM_MAX_CHARS`, or deploy multiple Ollama instances with a load balancer. |
| Identical sandbox scores | All companies get the same mock template → identical D/P/A/U scores. | Sandbox is for integration testing only. Use live mode for real differentiation. |
| LiDAR/SLAM niche | Scoring heavily rewards autonomous/robotics signals. CRM, SaaS, fintech companies score near 0 by design. | Intended — the system is purpose-built for Rebhu's ICP. |
| Confidence ceiling at 0.40 for fallback | Keyword-fallback companies can never exceed 0.40 confidence (LLM threshold is 0.45). | Forces them into the penalised tier even if keyword signals are strong. |

---

## Running the Pipeline

```bash
# Install dependencies
pip install -r requirements.txt

# Start Ollama (required for LLM extraction)
ollama serve
ollama pull llama3

# Run the pipeline
python main.py

# Start the API server
python api/app.py

# Run tests
python -m pytest tests/ -v

# Run in offline/sandbox mode (no crawling, no Ollama)
CRS_OFFLINE_MODE=1 python main.py
```

Output files are written to `output/ranked_companies.csv` and `output/ranked_companies.json`.
