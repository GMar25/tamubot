"""
tamubot.ingestion.docling_eval

Standalone evaluation script comparing PyMuPDF vs Docling header detection
on TAMU syllabus PDFs. Produces side-by-side markdown outputs, per-file
header diffs, and a summary CSV report.

Usage:
    # Single PDF:
    python -m tamubot.ingestion.docling_eval \
        tamu_data/raw/simple_syllabus/ISEN/graduate/Fall_2025/202541_ISEN_620_601_52745.pdf

    # Directory of PDFs:
    python -m tamubot.ingestion.docling_eval \
        tamu_data/raw/simple_syllabus/ISEN/graduate/Spring_2026/

    # With options:
    python -m tamubot.ingestion.docling_eval --limit 5 --output-dir /tmp/eval \
        tamu_data/raw/simple_syllabus/ISEN/graduate/Spring_2026/
"""

import argparse
import csv
import re
import time
from pathlib import Path

from docling.datamodel.base_models import InputFormat  # noqa: E402
from docling.datamodel.pipeline_options import PdfPipelineOptions  # noqa: E402
from docling.document_converter import DocumentConverter, PdfFormatOption  # noqa: E402

from tamubot.ingestion.boilerplate_stripper import (
    annotated_to_clean_markdown,
    pdf_to_annotated_markdown,
    strip_font_annotated_boilerplate,
)

DEFAULT_OUTPUT_DIR = Path("tamu_data/processed/docling_eval")

HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$")
# Synthetic font sizes for converting Docling markdown headers to annotated format
LEVEL_TO_PT = {1: 22.0, 2: 16.0, 3: 13.0, 4: 12.0, 5: 11.5, 6: 11.0}


def convert_with_docling(converter: DocumentConverter, pdf_path: Path) -> str:
    """Convert a PDF to markdown using Docling's ML-based structure detection."""
    result = converter.convert(str(pdf_path))
    return result.document.export_to_markdown()


def extract_headers(markdown: str) -> list[dict]:
    """Extract headers from markdown, returning [{level, text, normalized}]."""
    headers = []
    for line in markdown.splitlines():
        m = HEADER_RE.match(line)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            normalized = re.sub(r"[^\w\s]", "", text.lower()).strip()
            normalized = re.sub(r"\s+", " ", normalized)
            headers.append({"level": level, "text": text, "normalized": normalized})
    return headers


def compare_headers(pymupdf_headers: list[dict], docling_headers: list[dict]) -> dict:
    """Compare header sets, returning shared/unique headers and counts."""
    pymupdf_norms = {h["normalized"] for h in pymupdf_headers}
    docling_norms = {h["normalized"] for h in docling_headers}

    shared = pymupdf_norms & docling_norms
    pymupdf_only = pymupdf_norms - docling_norms
    docling_only = docling_norms - pymupdf_norms

    # Map normalized back to original text for readability
    pymupdf_text_map = {h["normalized"]: h["text"] for h in pymupdf_headers}
    docling_text_map = {h["normalized"]: h["text"] for h in docling_headers}

    return {
        "shared_count": len(shared),
        "shared": sorted(shared),
        "pymupdf_only_count": len(pymupdf_only),
        "pymupdf_only": sorted(pymupdf_text_map[n] for n in pymupdf_only),
        "docling_only_count": len(docling_only),
        "docling_only": sorted(docling_text_map[n] for n in docling_only),
    }


def docling_md_to_annotated(docling_md: str, body_size: float = 11.0) -> str:
    """Convert Docling markdown headers to font-annotated format.

    This lets us run Docling output through the existing boilerplate stripper
    by mapping # levels to synthetic font sizes.
    """
    out_lines = [f"<!-- body_font:{body_size}pt -->"]
    for line in docling_md.splitlines():
        m = HEADER_RE.match(line)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            pt = LEVEL_TO_PT.get(level, 11.0)
            out_lines.append(f"[{pt}pt] {text}")
        else:
            out_lines.append(line)
    return "\n".join(out_lines)


def write_comparison(
    stem: str,
    pymupdf_headers: list[dict],
    docling_headers: list[dict],
    comparison: dict,
    metrics: dict,
    output_dir: Path,
) -> None:
    """Write a human-readable comparison file for one PDF."""
    lines = [f"=== {stem} ===", ""]

    lines.append(f"PyMuPDF headers ({len(pymupdf_headers)}):")
    for h in pymupdf_headers:
        tag = ""
        if h["normalized"] not in {d["normalized"] for d in docling_headers}:
            tag = "  <-- PYMUPDF ONLY"
        lines.append(f"  {'#' * h['level']} {h['text']}{tag}")

    lines.append("")
    lines.append(f"Docling headers ({len(docling_headers)}):")
    for h in docling_headers:
        tag = ""
        if h["normalized"] not in {p["normalized"] for p in pymupdf_headers}:
            tag = "  <-- DOCLING ONLY"
        lines.append(f"  {'#' * h['level']} {h['text']}{tag}")

    lines.append("")
    lines.append(f"Shared headers ({comparison['shared_count']}): {', '.join(comparison['shared']) or '(none)'}")
    lines.append(
        f"Docling-only ({comparison['docling_only_count']}): {', '.join(comparison['docling_only']) or '(none)'}"
    )
    lines.append(
        f"PyMuPDF-only ({comparison['pymupdf_only_count']}): {', '.join(comparison['pymupdf_only']) or '(none)'}"
    )

    lines.append("")
    lines.append("--- Boilerplate strip rates ---")
    lines.append(f"PyMuPDF: {metrics['pymupdf_bp_strip_rate']:.1f}%")
    lines.append(f"Docling: {metrics['docling_bp_strip_rate']:.1f}%")

    lines.append("")
    lines.append("--- Body text char counts ---")
    lines.append(f"PyMuPDF: {metrics['body_chars_pymupdf']}")
    lines.append(f"Docling: {metrics['body_chars_docling']}")

    lines.append("")
    lines.append("--- Timing ---")
    lines.append(f"PyMuPDF: {metrics['pymupdf_time_s']:.2f}s")
    lines.append(f"Docling: {metrics['docling_time_s']:.2f}s")

    (output_dir / f"{stem}_comparison.txt").write_text("\n".join(lines))


def evaluate_pdf(pdf_path: Path, converter: DocumentConverter, output_dir: Path) -> dict:
    """Run both parsers on one PDF, compare, and write outputs."""
    stem = pdf_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- PyMuPDF path ---
    t0 = time.monotonic()
    annotated_text, stats = pdf_to_annotated_markdown(pdf_path)
    pymupdf_clean_md = annotated_to_clean_markdown(annotated_text)
    pymupdf_time = time.monotonic() - t0

    pymupdf_headers = extract_headers(pymupdf_clean_md)

    # Strip rate via existing boilerplate stripper
    stripped_pymupdf, strip_log_pymupdf = strip_font_annotated_boilerplate(annotated_text)
    pymupdf_orig_chars = len(annotated_text)
    pymupdf_stripped_chars = sum(e["chars"] for e in strip_log_pymupdf)
    pymupdf_strip_rate = (pymupdf_stripped_chars / pymupdf_orig_chars * 100) if pymupdf_orig_chars > 0 else 0.0

    # --- Docling path ---
    t0 = time.monotonic()
    docling_md = convert_with_docling(converter, pdf_path)
    docling_time = time.monotonic() - t0

    docling_headers = extract_headers(docling_md)

    # Convert Docling output to annotated format for boilerplate comparison
    docling_annotated = docling_md_to_annotated(docling_md, stats.get("body_size", 11.0))
    stripped_docling, strip_log_docling = strip_font_annotated_boilerplate(docling_annotated)
    docling_orig_chars = len(docling_annotated)
    docling_stripped_chars = sum(e["chars"] for e in strip_log_docling)
    docling_strip_rate = (docling_stripped_chars / docling_orig_chars * 100) if docling_orig_chars > 0 else 0.0

    # --- Compare ---
    comparison = compare_headers(pymupdf_headers, docling_headers)

    # Body text char counts (non-header lines)
    body_chars_pymupdf = sum(len(line) for line in pymupdf_clean_md.splitlines() if not HEADER_RE.match(line))
    body_chars_docling = sum(len(line) for line in docling_md.splitlines() if not HEADER_RE.match(line))

    metrics = {
        "stem": stem,
        "pymupdf_header_count": len(pymupdf_headers),
        "docling_header_count": len(docling_headers),
        "shared_headers": comparison["shared_count"],
        "pymupdf_only_count": comparison["pymupdf_only_count"],
        "docling_only_count": comparison["docling_only_count"],
        "pymupdf_only_headers": "; ".join(comparison["pymupdf_only"]),
        "docling_only_headers": "; ".join(comparison["docling_only"]),
        "pymupdf_bp_strip_rate": pymupdf_strip_rate,
        "docling_bp_strip_rate": docling_strip_rate,
        "body_chars_pymupdf": body_chars_pymupdf,
        "body_chars_docling": body_chars_docling,
        "pymupdf_time_s": pymupdf_time,
        "docling_time_s": docling_time,
    }

    # --- Write outputs ---
    (output_dir / f"{stem}_pymupdf.md").write_text(pymupdf_clean_md)
    (output_dir / f"{stem}_docling.md").write_text(docling_md)
    write_comparison(stem, pymupdf_headers, docling_headers, comparison, metrics, output_dir)

    return metrics


def write_report(all_metrics: list[dict], output_dir: Path) -> None:
    """Write summary CSV report sorted by docling_only_count descending."""
    if not all_metrics:
        return
    all_metrics.sort(key=lambda m: m["docling_only_count"], reverse=True)
    report_path = output_dir / "docling_eval_report.csv"
    with open(report_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_metrics[0].keys())
        writer.writeheader()
        writer.writerows(all_metrics)
    print(f"\nReport written to {report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare PyMuPDF vs Docling header detection on syllabus PDFs")
    parser.add_argument("path", type=Path, help="PDF file or directory of PDFs")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument("--limit", type=int, default=None, help="Process only first N PDFs")
    args = parser.parse_args()

    # Collect PDF paths
    if args.path.is_file():
        pdf_paths = [args.path]
    elif args.path.is_dir():
        pdf_paths = sorted(args.path.glob("*.pdf"))
    else:
        parser.error(f"Path does not exist: {args.path}")

    if args.limit:
        pdf_paths = pdf_paths[: args.limit]

    if not pdf_paths:
        parser.error(f"No PDF files found in {args.path}")

    print(f"Evaluating {len(pdf_paths)} PDF(s) → {args.output_dir}/")

    # Create converter once (model loading is expensive).
    # Layout model enabled (needs ~3-4GB RAM) — this is the core value of Docling
    # for header detection. OCR disabled since syllabi have embedded text.
    pipeline_options = PdfPipelineOptions(
        do_ocr=False,
        do_table_structure=False,
        do_picture_classification=False,
        do_picture_description=False,
        do_code_enrichment=False,
        do_formula_enrichment=False,
        do_chart_extraction=False,
    )
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)},
    )

    all_metrics: list[dict] = []
    for i, pdf_path in enumerate(pdf_paths, 1):
        print(f"\n[{i}/{len(pdf_paths)}] {pdf_path.name}")
        try:
            metrics = evaluate_pdf(pdf_path, converter, args.output_dir)
            all_metrics.append(metrics)
            print(
                f"  PyMuPDF: {metrics['pymupdf_header_count']} headers, "
                f"strip {metrics['pymupdf_bp_strip_rate']:.1f}%, "
                f"{metrics['pymupdf_time_s']:.1f}s"
            )
            print(
                f"  Docling: {metrics['docling_header_count']} headers, "
                f"strip {metrics['docling_bp_strip_rate']:.1f}%, "
                f"{metrics['docling_time_s']:.1f}s"
            )
            if metrics["docling_only_count"] > 0:
                print(f"  Docling-only: {metrics['docling_only_headers']}")
            if metrics["pymupdf_only_count"] > 0:
                print(f"  PyMuPDF-only: {metrics['pymupdf_only_headers']}")
        except Exception as e:
            print(f"  ERROR: {e}")

    write_report(all_metrics, args.output_dir)


if __name__ == "__main__":
    main()
