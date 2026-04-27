---
name: iterate-pipeline
description: Use when iteratively improving the ingestion pipeline — run validation, diagnose issues, apply fixes, re-validate changed files, and track results across iterations in an Excel report
triggers: ["iterate pipeline", "pipeline iteration", "fix pipeline issues", "pipeline QA", "validate pipeline", "improve pipeline", "iterate-pipeline"]
---

# Iterate Pipeline — Iterative QA for Ingestion

Announce: "Using iterate-pipeline skill."

Iteratively improve the syllabus processing pipeline: validate output, diagnose issues by root cause, apply targeted fixes, re-run only affected files, and track progress across iterations in a versioned Excel report.

## Key Files

| File | Purpose |
|---|---|
| `src/tamubot/ingestion/filters/false_positive.py` | False-positive header filter + text cleanup |
| `src/tamubot/ingestion/filters/boilerplate.py` | Boilerplate section stripper |
| `src/tamubot/ingestion/boilerplate_stripper.py` | Boilerplate registry definitions (`BOILERPLATE_REGISTRY`, `BODY_BOILERPLATE_HEADERS`) |
| `src/tamubot/ingestion/validators/llm_validator.py` | LLM validation (4-category findings) |
| `data/syllabi/silver/04_validate/*_validation.json` | Per-file validation results |
| `data/syllabi/silver/pipeline_summary_v{N}_baseline.csv` | Saved baselines per iteration |
| `data/syllabi/silver/docling_pipeline_v4_report.xlsx` | Cross-iteration tracking report |

## Step 1 — Establish Baseline

If no baseline exists for the current iteration, run LLM validation on all files in the corpus.

```python
from pathlib import Path
from tamubot.ingestion.validators.llm_validator import validate_syllabus

bp_dir = Path("data/syllabi/silver/02_boilerplate")
val_dir = Path("data/syllabi/silver/04_validate")
md_files = sorted(bp_dir.glob("*.md"))
# Exclude *_stripped.txt sidecar files
md_files = [f for f in md_files if not f.name.endswith("_stripped.txt")]
```

Invoke task-budget skill first — each validation call is ~1 TAMU API call (~25s each).

Save the baseline as `pipeline_summary_v{N}_baseline.csv` with columns:
`file_stem, total_issues, content_preservation, strip_completeness, structural_coherence, metadata_accuracy, content_preservation_detail, strip_completeness_detail, structural_coherence_detail, metadata_accuracy_detail`

Detail columns use ` | ` as delimiter between findings.

## Step 2 — Analyze Issues

Group validation findings by category and root cause. Present a summary:

```
Iteration v{N} Validation Summary
  Files validated:      73
  Files with 0 issues:  2
  Total findings:       310

  By category:
    content_preservation:   31  (course schedule missing, learning outcomes empty, ...)
    strip_completeness:     52  (Late Work Policy, indented headers, ...)
    structural_coherence:  207  (broken tables, orphaned headers, ...)
    metadata_accuracy:      20  (missing instructor phone, TBD fields, ...)
```

Then diagnose root causes — read the specific findings and identify actionable patterns:

- **Registry gaps**: boilerplate headers not in `BOILERPLATE_REGISTRY` or `BODY_BOILERPLATE_HEADERS` → add entries
- **Regex issues**: indented headers (`    ### Header`) not matching `_HEADER_RE` → fix regex
- **False positives**: body text promoted to headers by Docling → add to `_EXACT_FP`, `_PREFIX_FP`, or `_REGEX_FP`
- **Text artifacts**: broken URLs, `<!-- image -->` tags → add to `TEXT_CLEANUP_PATTERNS` or `_URL_SPACE_RE`
- **Source data issues**: image-based schedules, empty sections in original PDF → not fixable by pipeline
- **LLM false positives**: validator flagging correct output → note but don't fix

Separate fixable vs. not-fixable issues. Present the diagnosis and proposed fixes to the user.

**STOP — get user confirmation on which fixes to apply before proceeding.**

## Step 3 — Apply Fixes

Apply the agreed fixes to the relevant files. Common fix types:

### Registry updates (`boilerplate_stripper.py`)
```python
# Add to appropriate category in BOILERPLATE_REGISTRY
"TAMU_POLICY": [..., "new header text"],
# Or add to BODY_BOILERPLATE_HEADERS for non-# headers
BODY_BOILERPLATE_HEADERS = [..., "New Body Header"]
```

### False positive updates (`filters/false_positive.py`)
```python
# Exact match
_EXACT_FP: frozenset[str] = frozenset([..., "New False Positive"])
# Prefix match
_PREFIX_FP: list[str] = [..., "new prefix"]
# Regex match
_REGEX_FP: list[tuple[re.Pattern, str]] = [..., (re.compile(r"pattern"), "reason")]
```

### Text cleanup updates (`filters/false_positive.py`)
```python
TEXT_CLEANUP_PATTERNS: list[str] = [..., "new artifact pattern"]
# Or update _URL_SPACE_RE for URL-specific fixes
```

### Regex fixes (any filter)
```python
# e.g., support indented headers
_HEADER_RE = re.compile(r"^\s*(#{1,6})\s+(.+)$")  # was r"^(#{1,6})..."
```

## Step 4 — Re-run Only Affected Files

**Critical: only re-run files that were affected by the changes.** Do not re-run the entire corpus.

Identify affected files by checking which files contain the patterns that were fixed:

```python
# Example: find files affected by a new boilerplate registry entry
import re
affected = []
for md_path in sorted(fp_dir.glob("*.md")):
    text = md_path.read_text()
    if re.search(r"new header pattern", text, re.IGNORECASE):
        affected.append(md_path.stem)
print(f"{len(affected)} files affected")
```

Re-run only the changed filter stages on affected files. Use temp directories to run single files through the filter's `apply()` method:

```python
import tempfile, shutil
from tamubot.ingestion.filters.boilerplate import BoilerplateFilter

bf = BoilerplateFilter()
for stem in affected:
    with tempfile.TemporaryDirectory() as tmp_in, tempfile.TemporaryDirectory() as tmp_out:
        shutil.copy(fp_dir / f"{stem}.md", Path(tmp_in) / f"{stem}.md")
        bf.apply(Path(tmp_in), Path(tmp_out))
        shutil.copy(Path(tmp_out) / f"{stem}.md", bp_dir / f"{stem}.md")
        # Also copy sidecar if it exists
        sidecar = Path(tmp_out) / f"{stem}_stripped.txt"
        if sidecar.exists():
            shutil.copy(sidecar, bp_dir / f"{stem}_stripped.txt")
```

## Step 5 — Re-validate Only Changed Files

Invoke task-budget skill — count TAMU API calls for the affected files only.

```python
for stem in affected:
    result = validate_syllabus(bp_dir / f"{stem}.md", val_dir)
    # Result saved as {stem}_validation.json
```

Compare v{N-1} vs v{N} results for affected files:

```
v{N} Re-validation Results ({len(affected)} files)
  202611_ISEN_641_600_59191:  strip 11->0, total 22->12
  202641_ISEN_667_600_62094:  strip 12->2, total 21->16
  ...
```

## Step 6 — Save Baseline and Update Report

Save the new iteration baseline:
```python
# For affected files: use new validation JSON
# For unaffected files: carry forward v{N-1} values
# Save as pipeline_summary_v{N}_baseline.csv
```

Update the Excel report (`docling_pipeline_v4_report.xlsx`) by appending v{N} columns.

### Report Structure (6 sheets)

**Sheet 1 — Summary**

Columns grouped by iteration:
```
File | Term | Course | Section | Tokens In | Tokens Out | Sections Stripped
  | v1 CP | v1 SC | v1 Str | v1 Met
  | v2 CP | v2 SC | v2 Str | v2 Met
  | v{N} CP | v{N} SC | v{N} Str | v{N} Met
```

Rules:
- **Arrow notation** for changed values: `11→0`, `4→2`
- **Absolute coloring**: green = 0 issues, yellow = 1-2, red = 3+
- **Gray fill** for files not re-validated in this iteration (carried forward)
- **Iteration objective** as comment on each iteration group's first header cell
- **Findings detail** as comment on each iteration group's first data cell (Content Pres.) per row
- **Stripped headers** as comment on Sections Stripped cell

**Sheets 2-5 — Per-Category Detail** (Content Pres., Strip Compl., Structural, Metadata)

```
File | v1 Count | v2 Count | v{N} Count | v1 Findings | v2 Findings | v{N} Findings
```

Same arrow/color/gray rules. Full findings text in the Findings columns.

**Sheet 6 — Stripped Headers**

```
File | Sections Stripped | Tokens In | Tokens Out | % Removed | Stripped Headers
```

All boilerplate headers stripped from each file (from `*_stripped.txt` sidecar files).

### Report Generation

```python
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.comments import Comment

GREEN  = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")  # 0 issues
YELLOW = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")  # 1-2 issues
RED    = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")  # 3+ issues
GRAY   = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")  # not re-validated
```

## Step 7 — Decide Next Iteration

Present the aggregate v{N-1} → v{N} comparison:

```
Category              v{N-1}  v{N}   Delta
content_preservation     31    28     -3
strip_completeness       52     8    -44
structural_coherence    207   200     -7
metadata_accuracy        20    24     +4
TOTAL                   310   260    -50
```

Then ask the user:
1. Are there remaining issues worth fixing in another iteration?
2. Any false strips to investigate (course-specific content removed)?
3. Ready to proceed to chunking, or iterate again?

If iterating again, go back to Step 2 with the new baseline.

## Gotchas

- **LLM validation variance**: re-validating the same unchanged file can produce slightly different findings counts (+/-1-2). This is expected — the LLM may phrase findings differently or catch different edge cases. Don't chase variance.
- **Body-level boilerplate**: headers at body font size (no `#` prefix) need separate detection in `_BODY_BP_SET`. The boilerplate filter scans body lines against this set.
- **Indented headers**: Docling outputs `    ### Header` (4-space indent) for some PDFs. The header regex must use `^\s*` not `^` to match these.
- **Source data vs pipeline issues**: image-based course schedules, empty sections in the original PDF, and minimal registrar templates (e.g., Summer 2025 ISEN 691 "Research" sections) are source data limitations, not pipeline bugs. Don't try to fix these in the pipeline.
- **TAMU API always returns SSE**: set `stream=True` in validation calls. Each call takes ~25s.
- **Re-run scope**: always identify and re-run only affected files. Running the full corpus wastes API budget and adds LLM variance noise.
