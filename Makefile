.PHONY: run scrape-catalog scrape-classes scrape-simple-syllabus setup-atlas ingest ingest-dept \
        ingest-corpus test typecheck lint format probe probe-v3 probe-full \
        eval-draft import-draft bench bench-ragas test-v4 probe-v4 \
        eval-chunking sandbox-up sandbox-down sandbox-shell agent

# --- App ---
run:
	@echo "Starting TamuBot..."
	@streamlit run app.py --server.headless true

# --- Data Pipeline ---
scrape-catalog:
	cd tamu_data/scraper && scrapy crawl catalog

scrape-classes:
	cd tamu_data/scraper && scrapy crawl class_search

scrape-simple-syllabus:
	python tamu_data/scraper/download_simple_syllabus.py

setup-atlas:
	python -m tamubot.ingestion.setup_atlas

ingest:
	python -m tamubot.ingestion.ingest

ingest-v3:
	python -m tamubot.ingestion.ingest --v3

ingest-dept:
	python -m tamubot.ingestion.ingest --department $(DEPT)

ingest-corpus:
	python -m tamubot.ingestion.ingest --v3 --crns-file tamu_data/evals/eval_corpus.json

# --- Dev / Testing ---
test:
	pytest tests/ -v

typecheck:
	mypy src/tamubot/ --ignore-missing-imports

lint:
	ruff check src/tamubot/ app.py config.py

format:
	ruff format src/tamubot/ app.py config.py

probe:
	python -m tamubot.evals.run_probe --suite smoke

probe-v3:
	USE_V4_PIPELINE=false python -m tamubot.evals.run_probe --suite smoke

probe-full:
	python -m tamubot.evals.run_probe --suite all

test-v4:
	pytest tests/test_v4_*.py -v

probe-v4:
	python -m tamubot.evals.run_probe --suite smoke

# --- Benchmarking ---
eval-draft:
	python -m tamubot.evals.generate_eval_draft --n 60

import-draft:
	python -m tamubot.evals.import_eval_draft --draft $(DRAFT) --tag $(or $(TAG),v1)

bench:
	python -m tamubot.evals.run_benchmark --golden-set $(GOLDEN) --experiment-name $(EXP) \
		$(if $(CHUNKS_COL),--chunks-collection $(CHUNKS_COL),)

bench-ragas:
	python -m tamubot.evals.run_benchmark --golden-set $(GOLDEN) --experiment-name $(EXP) --ragas \
		$(if $(CHUNKS_COL),--chunks-collection $(CHUNKS_COL),)

eval-chunking:
	SESSION_CACHE_ENABLED=false python -m tamubot.evals.eval_chunking \
		--golden-set $(GOLDEN) \
		--experiment $(EXP) \
		$(if $(RAGAS),--ragas,) \
		$(if $(TOP_K),--top-k $(TOP_K),) \
		$(if $(THRESHOLD),--threshold $(THRESHOLD),) \
		$(if $(CHUNK_SIZE),--chunk-size $(CHUNK_SIZE),) \
		$(if $(CHUNK_OVERLAP),--chunk-overlap $(CHUNK_OVERLAP),) \
		$(if $(CHUNKS_COL),--chunks-collection $(CHUNKS_COL),) \
		$(if $(DESC),--description "$(DESC)",) \
		$(if $(OUTPUT),--output $(OUTPUT),)

# --- Docker Sandbox ---
sandbox-up:
	docker compose up -d

sandbox-down:
	docker compose down

sandbox-shell:
	docker exec -it tamubot-dev-1 bash

agent:
	docker exec -it tamubot-dev-1 claude --dangerously-skip-permissions
