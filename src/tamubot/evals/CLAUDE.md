# evals/

## Probe
```bash
python -m tamubot.evals.run_probe --suite smoke
python -m tamubot.evals.run_probe --query "..." [--memory] [--thread-id ID] [--tag label] [--ragas]
python -m tamubot.evals.run_probe --test-ids 1 3 7
```

## Benchmark (A/B)
```bash
make eval-draft                          # generate questions → drafts/eval_draft_YYYYMMDD.xlsx
make import-draft DRAFT=... TAG=v1       # approve → golden_sets/golden_*.xlsx
CHUNK_SIZE=600 OVERLAP=100 make ingest-corpus
make bench GOLDEN=... EXP=cs600_ov100   # → reports/benchmark_*.xlsx + .md
make bench-ragas GOLDEN=... EXP=...     # with RAGAS (~30s/q)
make validate-ragas BENCH=...           # after filling human_judgment column
```

## Key Exports
```python
from tamubot.evals.eval_pipeline import TEST_SUITE, TestCase
```

