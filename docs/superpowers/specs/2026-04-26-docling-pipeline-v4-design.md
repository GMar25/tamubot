# Docling Pipeline v4 Design Spec

## Context

PyMuPDF uses font-size heuristics for header detection (header = body_size + 1.0pt), which fails when syllabus headers are at body font size. The v3 eval showed Docling (IBM, ML-based layout detection) finds 5-25 extra real structural headers per PDF. However, Docling's markdown export flattens headings to `##` and produces false positive headers.

This spec designs a modular v4 pipeline that replaces PyMuPDF with Docling as the primary converter, adds a filter architecture for post-processing, and restructures the data folder using medallion (raw/bronze/silver/gold) conventions to support future document types beyond syllabi.

## Pipeline Flow

```
PDF --> [Raw] --> [Bronze: Docling] --> Silver: 01_false_pos --> 02_boilerplate --> 03_hierarchy --> 04_validate --> 05_chunk --> [Gold]
```

### Steps

1. **Raw** - Copy source PDFs with version suffix (`_v001.pdf`). Reuses v3 step0 logic.
2. **Bronze** - Docling converts PDF to markdown. `docling-hierarchical-pdf` post-processes to reconstruct heading hierarchy from PDF bookmarks/TOC or font-size clustering.
3. **Silver 01_false_positive** - Registry-based filter demotes known false positive headers back to body text (e.g., "This material Is: Required/Recommended/Optional", "Notes:", "URL for Resource:", "Texas A&M College Station", short sentences incorrectly promoted to headers).
4. **Silver 02_boilerplate** - Strips institutional boilerplate sections (header + body until next header). Registry ported from v3's `BOILERPLATE_REGISTRY` and `BODY_BOILERPLATE_HEADERS`, adapted to match markdown headers instead of font-annotated text. Flags new boilerplate candidates via `_BP_KEYWORDS`.
5. **Silver 03_hierarchy** - Additional heading level correction if `docling-hierarchical-pdf` output still needs adjustment. Pass-through if hierarchy is already correct.
6. **Silver 04_validate** - Single LLM call per file performing 4 checks. Read-only (produces reports, does not modify files).
7. **Silver 05_chunk** - Header-based semantic chunking + LLM metadata extraction. Produces JSON.
8. **Gold** - Final JSON files ready for MongoDB ingestion.

### Filter Ordering Rationale

False positive and boilerplate filters run BEFORE hierarchy reconstruction. This gives the hierarchy step a cleaner document with fewer noise headers, improving reconstruction accuracy.

## Data Folder Structure

Source-first medallion layout, supporting future document types (catalogs, policies, etc.):

```
data/
  syllabi/
    raw/                          # Versioned PDF copies (_v001.pdf)
    bronze/                       # Docling markdown output
    silver/
      01_false_positive/          # False positive headers demoted
      02_boilerplate/             # Boilerplate sections stripped
      03_hierarchy/               # Heading levels reconstructed
      04_validate/                # LLM quality reports (JSON, no markdown changes)
      05_chunk/                   # Chunked JSON with metadata
    gold/                         # Final JSON for ingestion
    logs/                         # Consolidated pipeline logs (CSV + JSONL)
  catalogs/                       # Future: same medallion sub-structure
  ...                             # Future document types
```

Each filter writes to its own sub-directory for full traceability of intermediate states.

## Code Structure

```
src/tamubot/ingestion/
  pipeline_v4.py                  # Orchestrator + CLI entry point
  converters/
    __init__.py
    docling_converter.py          # Primary: Docling + docling-hierarchical-pdf
    pymupdf_converter.py          # Fallback: existing PyMuPDF logic
  filters/
    __init__.py
    base.py                       # FilterResult dataclass, BaseFilter protocol
    false_positive.py             # False positive header removal
    boilerplate.py                # Boilerplate stripping (ported registry)
    hierarchy.py                  # Heading level reconstruction
  validators/
    __init__.py
    llm_validator.py              # 4-check LLM validation
  chunker_v4.py                   # Header-based semantic chunking
  metrics.py                      # Quality metrics computation
  pipeline_logger.py              # Existing (reused)
  boilerplate_stripper.py         # Existing (kept for v3 compat)
  process_syllabi_v3.py           # Existing (kept for v3 compat)
```

## Filter Architecture

### Common Interface

```python
@dataclass
class FilterResult:
    input_count: int          # Files processed
    modified_count: int       # Files where changes were made
    metrics: dict             # Filter-specific metrics
    log_entries: list[dict]   # Per-file log rows

class BaseFilter(Protocol):
    name: str
    def apply(self, input_dir: Path, output_dir: Path, config: dict) -> FilterResult: ...
```

Each filter is both:
- **A callable function** the orchestrator invokes: `filter.apply(input_dir, output_dir, config)`
- **A standalone CLI** for debugging: `python -m tamubot.ingestion.filters.false_positive input/ output/`

### False Positive Filter

- Registry of patterns known to be false positive headers
- Demotes matching headers back to body text (removes `#` prefix)
- Metrics: count of demoted headers per file, list of demoted text

### Boilerplate Filter

- Ported from v3's `BOILERPLATE_REGISTRY` (4 categories: DEPT_HEADER, TAMU_POLICY, TECH_SUPPORT, INSTITUTIONAL)
- Matches markdown headers (`## Header Text`) instead of font-annotated text (`[16.0pt bold] Header Text`)
- Strips entire sections (header + body until next header of same or higher level)
- Flags new boilerplate candidates via keyword matching (`_BP_KEYWORDS` ported from v3)
- Metrics: sections stripped by category, tokens removed, reduction %, new candidates

### Hierarchy Filter

- The bronze step applies `docling-hierarchical-pdf` as part of conversion. This filter provides additional corrections if the bronze output still has flat or incorrect hierarchy (e.g., all `##` with no `###`).
- Remaps heading levels to proper hierarchy (`#` > `##` > `###`) using heuristics (indentation, numbering patterns, font-size metadata if available)
- Pass-through if hierarchy depth distribution looks correct (has at least 2 distinct levels)
- Metrics: level distribution before/after, max depth

## Converter Design

### Docling Converter (Primary)

```python
def convert(pdf_path: Path, output_dir: Path) -> ConvertResult:
    # 1. Docling conversion (OCR off, tables off, pictures off)
    # 2. docling-hierarchical-pdf post-processing for hierarchy
    # 3. Custom MarkdownTextSerializer to map levels correctly
    # 4. Write markdown to output_dir
```

Configuration (from eval):
- `do_ocr=False` (syllabi have embedded text)
- `do_table_structure=False`
- `do_picture_classification=False`, `do_picture_description=False`
- `do_code_enrichment=False`, `do_formula_enrichment=False`, `do_chart_extraction=False`
- Layout model enabled (core value, ~6GB RAM, ~10-22s per PDF)

### PyMuPDF Converter (Fallback)

- Extracted from v3's `boilerplate_stripper.py::pdf_to_annotated_markdown()`
- Available via `--converter pymupdf` flag
- Produces font-annotated markdown (same format as v3 step1)

## Header-Based Semantic Chunking

Replaces v3's flat token-count chunking with hierarchy-aware splitting:

### Algorithm

1. Parse markdown into a tree of sections (header + body text, with children)
2. Walk the tree depth-first
3. For each section:
   - If total tokens <= `max_chunk_tokens`: emit as one chunk
   - If total tokens > `max_chunk_tokens` and has sub-headers: split at sub-headers, recurse
   - If total tokens > `max_chunk_tokens` and no sub-headers: split at paragraph boundaries (fallback)
4. For tiny sections (< `min_chunk_tokens`): merge with adjacent sibling under same parent

### Config

- `max_chunk_tokens`: Maximum tokens per chunk (initial default: 600, tune after first run by reviewing chunking log)
- `min_chunk_tokens`: Minimum tokens per chunk, merge if below (initial default: 50, tune after first run)
- `split_level`: Deepest header level to split on (e.g., 3 means split at `###` but not `####`)

### Chunk Output

Each chunk includes:
- `content`: The chunk text
- `header_path`: Source header trail (e.g., "Grading > Late Policy")
- `chunk_index`: Position in document
- `token_count`: Token count
- `split_reason`: "section" | "sub-header" | "paragraph-fallback" | "merged"

### Chunking Log

Per-file log records:
- Which sections were kept as-is (within limits)
- Which sections were split at sub-headers (and which sub-headers)
- Which sections were merged with siblings (and why)
- Which sections required paragraph-level fallback splitting
- Per-chunk: token count, source header path

## Quality Metrics

### Automatic Metrics (per file, aggregated per department)

**Structural:**
- Header count
- Hierarchy depth distribution (count of `#`, `##`, `###`, etc.)
- Orphan section detection (headers with no body text)
- Empty/near-empty section count

**Content:**
- Total token count (before/after each filter)
- Reduction % per filter
- Table count, list count
- Encoding artifact count (`&amp;`, `U+FFFD`, etc.)

**Filter-specific:**
- False positives caught (count + list)
- Boilerplate sections stripped (count + list by category)
- New boilerplate candidates flagged

**Chunking:**
- Chunk count
- Avg/min/max chunk tokens
- Sections split/merged counts
- Header path per chunk

**Cross-document (aggregated):**
- Per-department averages for all metrics
- Outlier detection (files with unusually low/high scores)
- Conversion timing stats

### LLM Validation (single call per file, 4 checks)

1. **Strip completeness** (0-1): Was all boilerplate removed?
2. **Content preservation** (0-1): Was any course-specific content accidentally removed?
3. **Structural coherence** (0-1): Do headers and hierarchy make logical sense?
4. **Metadata accuracy** (0-1): Does extracted metadata match document content?

Output: JSON report per file in `silver/04_validate/` + summary CSV in `logs/`.

## CLI Interface

```bash
python -m tamubot.ingestion.pipeline_v4 --department ISEN --term "Fall 2026"
```

### Confirmation Display

```
=== Docling Pipeline v4 ===
  Source:      data/syllabi/raw/
  Department:  ISEN
  Term:        Fall 2026
  Converter:   docling
  Steps:       convert > false_positive > boilerplate > hierarchy > validate > chunk > gold

  Found 16 PDFs matching criteria.
  Proceed? [Y/n]
```

### Step Selection Flags

```bash
# Run specific steps (comma-separated)
--steps convert,false_positive,boilerplate

# Run a range
--from convert --to hierarchy

# Skip specific steps
--skip validate

# Single step
--step false_positive
```

When chunking is not in the selected steps, chunk config is hidden from confirmation. When validate is not selected, LLM settings are hidden.

### Other Flags

- `--department DEPT` - Filter source PDFs by department
- `--term "Fall 2026"` - Filter by term (human-readable, mapped internally to numeric codes)
- `--converter docling|pymupdf` - Converter choice (default: docling)
- `--no-validate` - Shorthand for `--skip validate`
- `--limit N` - Process only first N files
- `--max-chunk-tokens N` - Max tokens per chunk
- `--min-chunk-tokens N` - Min tokens per chunk (merge threshold)
- `--split-level N` - Deepest header level to split on

## Reuse from v3

| v3 Component | v4 Usage |
|---|---|
| `boilerplate_stripper.py` BOILERPLATE_REGISTRY | Port entries to `filters/boilerplate.py` (match markdown headers) |
| `boilerplate_stripper.py` BODY_BOILERPLATE_HEADERS | Port to boilerplate filter |
| `process_syllabi_v3.py` step0 copy logic | Reuse for raw step (version suffix) |
| `process_syllabi_v3.py` `_BP_KEYWORDS` | Port to boilerplate filter candidate detection |
| `chunker_v3.py` equalized chunking | Keep as paragraph-level fallback in `chunker_v4.py` |
| `pipeline_logger.py` | Reuse for logging infrastructure |
| `docling_eval.py` Docling config | Reuse converter settings |
| LLM metadata extraction prompt | Reuse in chunk step |

## Dependencies

- `docling` >= 2.91.0 (already installed)
- `docling-hierarchical-pdf` (new dependency, to be installed)
- Existing: `pymupdf`, `tiktoken`, `anthropic`

## Verification Plan

1. **Unit tests**: Each filter independently on a known-good PDF
2. **Integration test**: Full pipeline run on 2-3 ISEN PDFs, verify gold output
3. **Regression test**: Compare v4 gold output against v3 step3 output for the same PDFs
4. **Metrics review**: Check quality metrics CSV for outliers
5. **LLM validation**: Review validation reports for any content loss flags
6. **Skill test**: Run via the Claude Code skill, verify confirmation prompts display correctly
