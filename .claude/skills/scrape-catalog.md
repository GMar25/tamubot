---
name: scrape-catalog
description: Use when scraping course catalog pages from catalog.tamu.edu — graduate program descriptions, degree plans, course descriptions, or certificates
triggers: ["scrape catalog", "catalog scrape", "course catalog", "scrape-catalog"]
---

# /scrape-catalog — TAMU Course Catalog Scraper

## Quick reference

```bash
# Scrape specific departments (CSCE and ISEN graduate)
scrapy crawl catalog -a departments=CSCE,ISEN

# Full-site crawl (no department filter)
make scrape-catalog
```

Spider: `src/tamubot/scraper/spiders/catalog_spider.py`

## Output conventions

- Markdown files → `tamu_data/raw/catalog/{DEPT}/`
  - e.g. `tamu_data/raw/catalog/CSCE/`, `tamu_data/raw/catalog/ISEN/`
- Filename: URL path slugified (e.g. `graduate_course-descriptions_csce.md`)
- Each file has a title header, source URL, and cleaned text content
- Pages outside known departments go to `catalog/general/`

## Configured departments

Edit `DEPT_PATHS` dict in `catalog_spider.py` to add departments:

```python
DEPT_PATHS = {
    "CSCE": [
        "/graduate/colleges-schools-interdisciplinary/engineering/computer-science/",
        "/graduate/course-descriptions/csce/",
    ],
    "ISEN": [
        "/graduate/colleges-schools-interdisciplinary/engineering/industrial-systems/",
        "/graduate/course-descriptions/isen/",
    ],
}
```

Each entry has two paths:
1. **Program pages** — department overview, degree plans (MS, PhD, MEng, certificates)
2. **Course descriptions** — full course listing for the subject code

The spider follows links within these path prefixes, so sub-pages (e.g. `/computer-science/phd/`) are automatically discovered.

## Adding a new department

1. Find the department's graduate catalog URL at `catalog.tamu.edu/graduate/`
2. Add an entry to `DEPT_PATHS` with the program path and course-descriptions path
3. Run: `scrapy crawl catalog -a departments=NEWDEPT`

## Spider behaviour

- `-a departments=CSCE,ISEN` — comma-separated list restricts crawl to those departments only
- Without `-a departments`, crawls the entire `catalog.tamu.edu` site
- Respects `robots.txt`, 1.5s download delay
- Progress log at `tamu_data/scraper/logs/progress_log.txt` enables resumable crawls
- HTML cleaned via Trafilatura (removes nav, footers, sidebars)

## Pipeline

`CatalogPagePipeline` in `src/tamubot/scraper/pipelines.py` saves `TamuPageItem` content to disk. It determines the department from the URL path using `CatalogSpider.dept_for_url()`.

## Gotchas

- **Trafilatura extraction**: some pages with heavy JS navigation may yield thin content. The course-descriptions pages are the most reliable.
- **Resumable**: the spider skips URLs already in the progress log. Delete the log to force a full re-scrape.
- **Full-site crawl is slow**: the entire catalog has thousands of pages. Always use `-a departments=` for targeted scrapes.
