# tamubot.ingestion

## Contract

Producer for `tamubot.rag.models` — import schema models from there, never define them here.

## Pipeline

Full run: `make scrape-catalog && make scrape-classes` → `process_syllabi_v3.py --department CSCE` → `setup_atlas` → `ingest`. **Always run all steps together** — `--step N` is for debugging only, partial runs leave downstream stale.

Reset catalog crawl: delete `tamu_data/scraper/logs/progress_log.txt`.

## Gotchas

- **U+FFFD chars**: PyMuPDF emits replacement chars for un-decodable bytes. `clean_replacement_chars()` handles post-parse.
- **Boilerplate registry** (`boilerplate_stripper.py`): font-annotated headers → `BOILERPLATE_REGISTRY`; body-size → `BODY_BOILERPLATE_HEADERS`. Only add long, unambiguous phrases to body list.
- **`_BP_KEYWORDS`** in `process_syllabi_v3.py`: flags non-stripped headers as new candidates → `new_bp_candidates` column. Expand when new patterns emerge.
