---
name: scrape-howdy-portal
description: Use when scraping class sections or syllabi from howdyportal.tamu.edu — running the Scrapy spider, adding departments/terms, or debugging
triggers: ["scrape howdy portal", "scrape classes", "howdy portal", "scrape-howdy-portal"]
---

# /scrape-howdy-portal — Howdy Portal Scraper

## Quick reference

```bash
make scrape-classes
```

Spider: `src/tamubot/scraper/spiders/class_search_spider.py`

## Output conventions

- PDFs → `tamu_data/raw/howdy_portal/{SUBJECT}/{subgroup}/{Term_Year}/`
  - subgroup: `graduate` (course ≥ 600), `undergraduate` (course < 600)
  - e.g. `ISEN/graduate/Fall_2025/`
- Filename: `{term_code}_{SUBJECT}_{COURSE}_{SECTION}_{CRN}.pdf`
- Term codes: Spring→11, Summer→21, Fall→31 (note: `41` is "Full Yr Professional", NOT Fall)

## Site details

- Open API, Scrapy works (no JS gate)
- Seed session via GET to `/uPortal/p/public-class-search-ui.ctf1/max/render.uP`, then POST `/api/course-sections` with `{"termCode": "202631"}`
- Term discovery: GET `/api/all-terms` returns all available term codes and descriptions

## Spider config

Edit these constants at the top of `class_search_spider.py`:

- `DEPARTMENTS` — set of subject codes (e.g. `{"ISEN"}`)
- `GRADUATE_ONLY` — `True` filters to course ≥ 600
- `TARGET_TERMS` — set of term code strings (e.g. `{"202511", "202531", "202611"}`)

## Known Howdy Portal term codes

| Term | Code | Description |
|---|---|---|
| Spring 2025 | 202511 | Spring 2025 - College Station |
| Summer 2025 | 202521 | Summer 2025 - College Station |
| Fall 2025 | 202531 | Fall 2025 - College Station |
| Spring 2026 | 202611 | Spring 2026 - College Station |
| Summer 2026 | 202621 | Summer 2026 - College Station |
| Fall 2026 | 202631 | Fall 2026 - College Station |

**Warning:** these codes differ from Simple Syllabus. Howdy Portal uses `*31` for Fall; Simple Syllabus uses `*41`.

## Gotchas

- **Only downloads syllabi that exist**: the API field `SWV_CLASS_SEARCH_HAS_SYL_IND` must be `'Y'`. Courses appear in the term dropdown long before professors upload PDFs. Re-run the scraper later to pick up newly uploaded syllabi.
- **Skip-existing**: pipeline checks `os.path.exists()` before downloading — safe to re-run without re-downloading.
- **College Station only**: spider filters `SWV_CLASS_SEARCH_SITE == 'College Station'`, skipping Galveston/Qatar campuses.

## Scrapy layout

- `scrapy.cfg`: `default = settings`
- `settings.py` (`src/tamubot/scraper/settings.py`): `FILES_STORE = 'tamu_data/raw'`
- Pipeline: `SyllabusPipeline` in `src/tamubot/scraper/pipelines.py` routes files to `howdy_portal/{SUBJECT}/{subgroup}/{Term}/`
