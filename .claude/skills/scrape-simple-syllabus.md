---
name: scrape-simple-syllabus
description: Use when scraping syllabi from simplesyllabus.com — downloading PDFs, adding departments/terms, or debugging the Playwright scraper
triggers: ["scrape simple syllabus", "download syllabi", "simple syllabus", "scrape-simple-syllabus"]
---

# /scrape-simple-syllabus — Simple Syllabus Scraper

## Quick reference

```bash
make scrape-simple-syllabus
```

Scraper: `src/tamubot/scraper/download_simple_syllabus.py`

## Output conventions

- PDFs → `tamu_data/raw/simple_syllabus/{SUBJECT}/{subgroup}/{Term_Year}/`
  - subgroup: `graduate` (course ≥ 600), `undergraduate` (course < 600)
  - e.g. `ISEN/graduate/Fall_2026/`
- Metadata → `metadata.json` per term folder
- Filename: `{term_code}_{SUBJECT}_{COURSE}_{SECTION}_{CRN}.pdf`
- Term codes: Spring→11, Summer→21, Fall→41

## Site details

- CloudFront WAF blocks plain requests → must use Playwright
- Real search endpoint: `/api2/doc-library-search` (NOT `/api2/search`)
- `/api2/doc-pdf` is broken → use `page.pdf()` instead

## API filtering

- **Filter by term**: `term_ids[]={entity_id}` (NOT `term_statuses[]`)
- **Filter by department**: `search={DEPT}` (e.g. `search=ISEN`). This is a text search — not exact, but cuts scan from 10k+ items to ~200-300. Still filter client-side by `parsed["subject"]`.
- **`subject_ids[]` does NOT work** — returns all items regardless of value
- Combine both: `term_ids[]={tid}&search={DEPT}&page_size=50&page=0`

## Known term entity_ids

| Term | entity_id |
|---|---|
| Summer 2025 | `9ca19ce6-e67d-485f-b6d4-3febcab32aa5` |
| Fall 2025 | `ecd304d6-7795-4f49-a0ee-1d6137884ac7` |
| Spring 2026 | `3a9c109e-8e72-4682-966e-b6c754c0596f` |
| Fall 2026 | `6dcfa515-e3c9-4cd0-8413-ff8c00517ae3` |

To discover new term IDs: load the library page, watch for `doc-png` URLs in network traffic — they contain the term name (e.g. `Fall-2026-College-Station-ACCT-...`). Then fetch page 0 unfiltered and read `term_id` from the first matching item.

## Slug format

`{term_name.replace(' - ','-').replace(' ','-')}-{SUBJ}-{COURSE}-{SEC}-({CRN})`; URL-encode parens

## Scraper config

Edit these constants at the top of `download_simple_syllabus.py`:

- `DEPARTMENTS` — set of subject codes to scrape (e.g. `{"ISEN", "CSCE"}`)
- `GRADUATE_ONLY` — `True` filters to course ≥ 600
- `TARGET_TERMS` — set of term strings to include

## Gotchas

- **Stdout buffering**: when running in background, Python buffers stdout. Always use `PYTHONUNBUFFERED=1` (env var) or `sys.stdout.reconfigure(line_buffering=True)`.
- **Playwright in Docker**: needs system libraries (`playwright install --with-deps chromium` in Dockerfile, run as root before `USER` switch). Browser path set via `ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright`.
- **Skip-existing**: scraper checks `os.path.exists(out_path)` before downloading — safe to re-run to add new terms without re-downloading.
