# Rebhu Computing - Client Targeting System

## Overview

The ranking system has been completely redesigned to identify and rank companies based on their **NEED** for Rebhu Computing's products.

This is **NOT** a general company quality ranking system.
This is a **client targeting system** focused on finding companies that need Rebhu's solutions.

---

## The Scoring Model

### Formula

```
Client Score (0-100) = 
  Autonomy (30) +
  AI/Vision (25) +
  Industry (20) +
  Product Fit (15) +
  Data Quality (10)
```

### Component Breakdown

#### 1. **Autonomy Need (0-30 points)**

Indicates if company needs autonomous or navigation solutions.

| Signal | Points |
|--------|--------|
| "autonomous" OR "navigation" present | 30 |
| "automation" OR "automated" present | 20 |
| Otherwise | 5 |

**Examples:**
- "Autonomous drone navigation system" → 30 points
- "Automated manufacturing process" → 20 points
- "General software company" → 5 points

---

#### 2. **AI / Vision Need (0-25 points)**

Indicates if company uses AI, ML, or computer vision.

Looks for these keywords:
- AI
- Artificial Intelligence
- Machine Learning
- Computer Vision
- Deep Learning
- Neural Network

**Scoring:**
```
Score = (keywords_found / total_keywords) * 25
```

**Examples:**
- "AI-powered computer vision platform" → 18+ points (2/6 keywords)
- "Deep learning neural network engine" → 12+ points (2/6 keywords)
- "Rule-based system" → 0 points (0/6 keywords)

---

#### 3. **Industry Match (0-20 points)**

Indicates if company is in robotics, drones, or automation space.

Looks for keywords:
- Robotics
- Drone
- UAV
- Defense
- Automation
- Robot
- Unmanned

**Scoring:**
```
Score = (keywords_found / total_keywords) * 20
```

**Examples:**
- "Robotics and drone manufacturing" → 14+ points (2/7 keywords)
- "Defense automation systems" → 14+ points (2/7 keywords)
- "E-commerce platform" → 0 points (0/7 keywords)

---

#### 4. **Product Fit (0-15 points)**

Indicates how well Rebhu's products fit the company's needs.

| Company Type | Points |
|--------------|--------|
| Robotics OR Drone company | 15 |
| AI/Vision-based company | 10 |
| Automation company | 5 |
| Others | 0 |

**Examples:**
- "Drone company" → 15 points
- "AI research lab" → 10 points
- "Manufacturing automation" → 5 points

---

#### 5. **Data Quality (0-10 points)**

Indicates quality of extracted company data.

| Text Length | Points |
|-------------|--------|
| > 1000 chars | 10 |
| > 300 chars | 5 |
| ≤ 300 chars | 0 |

**Logic:** Better data = More confidence in scoring

---

## Category Classification

Based on the total score, companies are categorized:

| Score Range | Category | Meaning |
|-------------|----------|---------|
| ≥ 80 | **High Potential** | Strong match, ready to target |
| 60-79 | **Good Potential** | Clear signals, worth pursuing |
| 40-59 | **Moderate** | Some relevance, low priority |
| < 40 | **Low Potential** | Unlikely to be good fit |

---

## Example Scoring

### Example 1: Drone Manufacturer

**Company:** Acme Drones Inc.

**Text Summary:**
"We manufacture autonomous drones for agriculture and delivery. Our drones use advanced computer vision for obstacle detection and autonomous navigation. We leverage deep learning for real-time decision making. All systems built on robotics-grade embedded systems."

**Scoring:**

| Component | Calculation | Points |
|-----------|-------------|--------|
| **Autonomy** | "autonomous" + "navigation" present | 30 |
| **AI/Vision** | AI, computer vision, deep learning found (3/6) | 12.5 |
| **Industry** | Drones, robotics, autonomous found (3/7) | 14.3 |
| **Product Fit** | Drone company | 15 |
| **Data Quality** | Text length > 1000 | 10 |
| **TOTAL** | — | **81.8** |

**Category:** High Potential ✅

**Recommended Products:**
- Autonomous Navigation System
- Computer Vision Platform
- Real-time Control System

**Reason:** Company shows strong signals in autonomous/navigation needs, robotics/drone focus, and AI/ML capabilities

---

### Example 2: Manufacturing Automation Company

**Company:** SmartFactory Systems

**Text Summary:**
"We provide industrial automation solutions for manufacturing. Our systems automate assembly lines and quality control processes. We work with major automotive suppliers."

**Scoring:**

| Component | Calculation | Points |
|-----------|-------------|--------|
| **Autonomy** | "automate" present | 20 |
| **AI/Vision** | No AI/vision keywords (0/6) | 0 |
| **Industry** | No industry keywords (0/7) | 0 |
| **Product Fit** | Automation company | 5 |
| **Data Quality** | Text length ~300 chars | 5 |
| **TOTAL** | — | **30** |

**Category:** Low Potential ❌

**Reasoning:** While they do automation, they lack the AI/vision/robotics signals that indicate Rebhu product need

---

### Example 3: AI Research Company

**Company:** NeuralLabs AI

**Text Summary:**
"We conduct research in machine learning and computer vision. Our team has published papers on deep learning architectures. We develop AI frameworks for vision applications. Our work has applications in autonomous systems and robotics."

**Scoring:**

| Component | Calculation | Points |
|-----------|-------------|--------|
| **Autonomy** | "autonomous" present | 30 |
| **AI/Vision** | AI, machine learning, computer vision, deep learning (4/6) | 16.7 |
| **Industry** | Robotics, autonomous (2/7) | 5.7 |
| **Product Fit** | AI/vision company | 10 |
| **Data Quality** | Text length > 1000 | 10 |
| **TOTAL** | — | **72.4** |

**Category:** Good Potential ✅

**Recommended Products:**
- Computer Vision Platform
- AI Processing Engine
- Data Pipeline System

**Reason:** Company shows strong signals in AI/ML capabilities, autonomous systems focus

---

## Output Format

### CSV Output Example

```csv
company_name,website,industry,score,category,reason,recommended_products
"Acme Drones","https://acmedrones.com","Robotics",81.8,"High Potential","Company shows strong signals in autonomous/navigation needs, robotics/drone focus, and AI/ML capabilities","Autonomous Navigation System, Computer Vision Platform, Real-time Control System"
```

### JSON Output Example

```json
{
  "company_name": "Acme Drones",
  "website": "https://acmedrones.com",
  "industry": "Robotics",
  "products": [...],
  "technologies": ["autonomous navigation", "computer vision", "deep learning"],
  "score": 81.8,
  "category": "High Potential",
  "recommended_products": [
    "Autonomous Navigation System",
    "Computer Vision Platform",
    "Real-time Control System"
  ],
  "reason": "Company shows strong signals in autonomous/navigation needs, robotics/drone focus, and AI/ML capabilities"
}
```

---

## Key Differences from Previous System

### Before (General Quality Ranking)
- ❌ Ranked companies on overall quality/popularity
- ❌ No focus on Rebhu's specific market
- ❌ Treated all companies equally
- ❌ Not useful for sales targeting

### After (Rebhu Client Targeting)
- ✅ Ranks by NEED for Rebhu products
- ✅ Focuses on robotics, drones, AI, autonomy
- ✅ Weights factors relevant to Rebhu
- ✅ Ready for sales targeting and outreach

---

## Implementation Details

### Scoring Functions

All scoring functions are in `ranking/ranker.py`:

- `_autonomy_score(text)` - Detect autonomy/navigation needs
- `_ai_vision_score(text)` - Count AI/vision keywords
- `_industry_score(text)` - Count industry keywords
- `_product_fit_score(text)` - Assess product fit
- `_data_quality_score(text)` - Assess data quality
- `_compute_client_score(text)` - Calculate final score
- `_get_category(score)` - Classify into category
- `_get_recommended_products(text)` - Recommend products
- `_generate_reason(text, score)` - Generate explanation

### Integration Points

The system integrates seamlessly with existing pipeline:

1. **Input:** Companies with summary, products, technologies
2. **Processing:** `rank_companies()` computes Rebhu client scores
3. **Output:** CSV/JSON with score, category, recommendations, reason

---

## Usage Example

```python
from ranking.ranker import rank_companies

# Existing code flows through pipeline
ranked = rank_companies(
    companies=company_list,
    summaries_by_company=summaries,
    structured_by_company=structured,
    texts_by_company=texts
)

# Results include:
for company in ranked:
    print(f"{company.company.name}")
    print(f"  Score: {company.score}")
    print(f"  Category: {company.category}")
    print(f"  Reason: {company.reason}")
    print(f"  Recommended: {company.recommended_products}")
```

---

## Tuning the System

### Adjust Keyword Lists

Edit `ranking/ranker.py`:

```python
AUTONOMY_KEYWORDS = ["autonomous", "navigation", ...]
AI_VISION_KEYWORDS = ["AI", "machine learning", ...]
INDUSTRY_KEYWORDS = ["robotics", "drone", ...]
```

### Adjust Weights

The formula weights are fixed (30, 25, 20, 15, 10) but can be modified if needed:

```python
def _compute_client_score(text):
    # Change weights here
    autonomy * 0.3 + ai_vision * 0.25 + ...
```

### Adjust Thresholds

Category thresholds are in `_get_category()`:

```python
if score >= 80:      # Adjust these
    return "High Potential"
elif score >= 60:
    return "Good Potential"
```

---

## Validation Checklist

After implementation, verify:

- ✅ Drone companies score 75+
- ✅ AI companies score 60+
- ✅ Robotics companies score 70+
- ✅ E-commerce/SaaS companies score < 40
- ✅ Products properly recommended by category
- ✅ CSV/JSON output includes all fields

---

## FAQ

**Q: Why is a company scoring low even though it has AI?**
A: Because AI alone isn't enough. It needs autonomy/navigation OR be in robotics/drone space.

**Q: Why does data quality matter?**
A: Small company descriptions might not mention key keywords even if relevant. Quality score reflects confidence.

**Q: Can I customize the keywords?**
A: Yes! Edit `AUTONOMY_KEYWORDS`, `AI_VISION_KEYWORDS`, etc. in `ranking/ranker.py`

**Q: What about companies not in the current list?**
A: The system works for any company that crawls properly. If no need signals found, it will score low (correct).

---

## Next Steps

1. Run pipeline to generate ranked output
2. Export to sales team
3. Focus outreach on "High Potential" companies
4. Adjust keywords based on sales feedback
5. Track conversion rates by score category

---

## Summary

Your system now ranks companies based on:

✅ How much they **NEED** Rebhu's products
✅ Whether they're in robotics/drone/AI/automation space
✅ Whether they have autonomy or navigation requirements
✅ Whether they use AI/vision technologies

**Result:** High scores = hot leads ready to target

