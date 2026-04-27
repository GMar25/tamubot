---
name: check-syllabus-gaps
description: Use when checking syllabus coverage gaps across Howdy Portal, Simple Syllabus, and catalog.tamu.edu — finding missing syllabi per department and term
triggers: ["check syllabus gaps", "missing syllabi", "syllabus coverage", "syllabus gaps", "check-syllabus-gaps"]
---

# /check-syllabus-gaps — Syllabus Coverage Report

## Quick reference

```bash
python -m tamubot.scraper.find_missing_syllabi                # both gap types
python -m tamubot.scraper.find_missing_syllabi --source-gap   # Howdy vs Simple only
python -m tamubot.scraper.find_missing_syllabi --catalog-gap  # catalog vs both only
```

Script: `src/tamubot/scraper/find_missing_syllabi.py`

## What it does

Compares syllabus coverage across three data sources and produces one report per department under `tamu_data/raw/missing_syllabuses/<DEPT>.md`.

Each report has two sections:

### Source Gap
Courses that **have a syllabus in Howdy Portal** but are **missing from Simple Syllabus**. Broken down by term, with section and CRN details. Also flags terms where one source has no data at all.

### Catalog Gap
Courses listed in **catalog.tamu.edu course descriptions** that have **no syllabus in either Howdy Portal or Simple Syllabus**. These are courses the department offers but no PDF was found in any source.

## Data sources

| Source | Path | What it contains |
|---|---|---|
| Howdy Portal | `tamu_data/raw/howdy_portal/{DEPT}/graduate/` | Syllabus PDFs from howdyportal.tamu.edu |
| Simple Syllabus | `tamu_data/raw/simple_syllabus/{DEPT}/graduate/` | Syllabus PDFs from simplesyllabus.com |
| Catalog | `tamu_data/raw/catalog/{DEPT}/` | Course descriptions scraped from catalog.tamu.edu |

PDF filename convention: `{term_code}_{SUBJECT}_{COURSE}_{SECTION}_{CRN}.pdf`

## Output

```
tamu_data/raw/missing_syllabuses/
  CSCE.md   ← source gap + catalog gap for CSCE
  ISEN.md   ← source gap + catalog gap for ISEN
```

## Prerequisites

Run the relevant scrapers first to populate the raw data:
- `/scrape-howdy-portal` — Howdy Portal syllabi
- `/scrape-simple-syllabus` — Simple Syllabus syllabi
- `/scrape-catalog` — catalog.tamu.edu course descriptions

The script works with whatever data is currently available — missing sources are noted in the report rather than causing errors.

## Gotchas

- **Term code mismatch**: Howdy Portal uses `*31` for Fall, Simple Syllabus uses `*41`. Both are handled correctly.
- **Catalog lists all courses ever offered**, not just currently scheduled ones. Many catalog-gap entries are courses not taught in recent terms.
- **Graduate only**: catalog gap filters to course numbers >= 600.
