# Docling Evaluation Script — Design Spec

## Context

TamuBot's PDF-to-markdown pipeline (Step 1) uses PyMuPDF to extract text with font metadata, then applies heuristics to detect headers: a line is a header if its font size is >= body_size + 1.0pt, or its text matches a known boilerplate registry. This works when PDFs use distinct font sizes for headers, but fails when headers appear at body font size (e.g., "Office Hours", "Biography", "Preferred Contact Method" in ISEN syllabi). Recent ISEN course processing surfaced multiple cases where boilerplate stripping underperformed because headers were invisible to font-based detection.

Docling (IBM's open-source document parser) uses computer vision models (DocLayNet) to detect document structure — headers, paragraphs, tables — regardless of font metadata. This script evaluates whether Docling produces more reliable header detection on our syllabus PDFs.

## Goal

Build a standalone evaluation script that runs both PyMuPDF and Docling on the same PDFs, compares their header detection, and produces a report to decide whether Docling should replace PyMuPDF in Step 1.

## Script: `src/tamubot/ingestion/docling_eval.py`

### CLI Interface

```bash
# Run on a directory of PDFs:
python -m tamubot.ingestion.docling_eval \
    tamu_data/raw/simple_syllabus/ISEN/graduate/Spring_2026/

# Run on a single PDF:
python -m tamubot.ingestion.docling_eval \
    tamu_data/raw/simple_syllabus/ISEN/graduate/Fall_2025/202541_ISEN_620_601_52745.pdf

# Optional flags:
#   --output-dir DIR    Override output directory (default: tamu_data/processed/docling_eval/)
#   --limit N           Process only first N PDFs from a directory
```

### Output Structure

```
tamu_data/processed/docling_eval/
  ├── {stem}_pymupdf.md          # PyMuPDF font-annotated markdown (existing Step 1 output)
  ├── {stem}_docling.md          # Docling native markdown output
  ├── {stem}_comparison.txt      # Per-file header diff and metrics
  └── docling_eval_report.csv    # Summary table across all files
```

### Processing Flow Per PDF

1. **PyMuPDF path**: Call existing `pdf_to_annotated_markdown(pdf_path)` from `boilerplate_stripper.py`, then `annotated_to_clean_markdown()` to get final markdown with `#`/`##`/`###` headers. Save both the annotated and clean versions.

2. **Docling path**: Use Docling's native `DocumentConverter` API:
   ```python
   from docling.document_converter import DocumentConverter

   converter = DocumentConverter()
   result = converter.convert(str(pdf_path))
   docling_md = result.document.export_to_markdown()
   ```
   No font-size heuristics — Docling's ML models handle structure detection.

3. **Header extraction**: Parse both markdown outputs, extract lines starting with `#`, `##`, `###` (or `[Xpt]` annotations for the raw PyMuPDF output). Normalize header text for comparison (lowercase, strip whitespace/punctuation).

4. **Comparison metrics** (per file):
   - `pymupdf_header_count`: Number of headers detected by PyMuPDF
   - `docling_header_count`: Number of headers detected by Docling
   - `shared_headers`: Headers detected by both (fuzzy text match)
   - `pymupdf_only`: Headers found only by PyMuPDF
   - `docling_only`: Headers found only by Docling (these are the "missed by PyMuPDF" cases we care about)
   - `pymupdf_bp_strip_rate`: Boilerplate strip rate using PyMuPDF headers
   - `docling_bp_strip_rate`: Boilerplate strip rate using Docling headers (run Docling markdown through `strip_font_annotated_boilerplate` after converting Docling `#` headers to `[Xpt]` annotation format)
   - `body_char_count_pymupdf` / `body_char_count_docling`: Total non-header character counts for sanity check

5. **Human-readable comparison file** (`_comparison.txt`): For each PDF, show:
   ```
   === 202541_ISEN_620_601_52745 ===
   PyMuPDF headers (8):
     ## College of Engineering
     ## Industrial and Systems Engineering
     ...
   Docling headers (12):
     ## College of Engineering
     ## Industrial and Systems Engineering
     ## Office Hours              <-- DOCLING ONLY
     ## Biography                 <-- DOCLING ONLY
     ...
   Docling-only headers: Office Hours, Biography, Preferred Contact Method, Socials
   PyMuPDF-only headers: (none)
   ```

6. **Summary CSV** (`docling_eval_report.csv`): One row per PDF with all metrics above, sortable by `docling_only` count to surface the biggest wins.

### Reused Code from Existing Pipeline

| Function | Source | Purpose |
|----------|--------|---------|
| `pdf_to_annotated_markdown()` | `boilerplate_stripper.py` | PyMuPDF extraction for comparison baseline |
| `annotated_to_clean_markdown()` | `boilerplate_stripper.py` | Convert font annotations to `#` headers |
| `strip_font_annotated_boilerplate()` | `boilerplate_stripper.py` | Measure boilerplate strip rate for both parsers |

### New Code

- `docling_eval.py` — single file, ~200-250 lines:
  - `convert_with_docling(pdf_path) -> str` — wraps Docling API, returns markdown
  - `extract_headers(markdown: str) -> list[str]` — pulls `#`-prefixed lines
  - `compare_headers(pymupdf_headers, docling_headers) -> dict` — fuzzy match, compute overlap/diffs
  - `docling_md_to_annotated(docling_md: str) -> str` — converts `#`/`##`/`###` to `[Xpt]` format with synthetic sizes so boilerplate stripping can run on it
  - `evaluate_pdf(pdf_path, output_dir) -> dict` — orchestrates one PDF through both paths
  - `main()` — argparse CLI, iterates PDFs, writes outputs and summary CSV

### Dependencies

- **New**: `docling` (pip install)
- **Existing**: `pymupdf` (already installed), `boilerplate_stripper` (project code)

### What This Does NOT Do

- Does not modify the existing pipeline (Step 1/2/3)
- Does not replace PyMuPDF — this is evaluation only
- Does not use `docling-eval` (CLI-only, requires academic ground-truth datasets we don't have)
- Does not evaluate table extraction (separate concern for later)

## Verification

1. **Install**: `pip install docling` succeeds on Python 3.14
2. **Smoke test**: Run on a single ISEN PDF, verify both `.md` files are written and `_comparison.txt` shows header lists
3. **Batch test**: Run on `tamu_data/raw/simple_syllabus/ISEN/graduate/Spring_2026/` (~16 PDFs), review `docling_eval_report.csv`
4. **Spot check**: Open 2-3 `_comparison.txt` files, verify the "Docling-only" headers are real headers (not false positives) and that "PyMuPDF-only" headers aren't noise

## Success Criteria

Docling is worth integrating into the pipeline if:
- It detects headers that PyMuPDF misses (body-size headers like "Office Hours", "Biography")
- It doesn't produce excessive false-positive headers
- Boilerplate strip rates improve or stay the same
- Processing time is acceptable (even if slower than PyMuPDF, since it only runs once per PDF)
