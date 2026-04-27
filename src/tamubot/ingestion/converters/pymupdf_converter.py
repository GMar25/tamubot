"""PyMuPDF-based PDF-to-markdown converter (fast fallback)."""

from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from tamubot.ingestion.boilerplate_stripper import (
    annotated_to_clean_markdown,
    pdf_to_annotated_markdown,
)

HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


@dataclass
class ConvertResult:
    markdown: str
    output_path: Path
    timing_s: float
    header_count: int
    hierarchy_depth: dict[int, int] = field(default_factory=dict)


def _count_headers(markdown: str) -> tuple[int, dict[int, int]]:
    """Return (total_header_count, {level: count})."""
    depth: dict[int, int] = {}
    count = 0
    for m in HEADER_RE.finditer(markdown):
        level = len(m.group(1))
        depth[level] = depth.get(level, 0) + 1
        count += 1
    return count, depth


def convert(
    pdf_path: Path,
    output_dir: Path,
    **kwargs: object,
) -> ConvertResult:
    """Convert a PDF to markdown using PyMuPDF font-based header detection."""
    t0 = time.monotonic()

    annotated_text, _stats = pdf_to_annotated_markdown(pdf_path)
    markdown = annotated_to_clean_markdown(annotated_text)

    timing_s = time.monotonic() - t0

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{pdf_path.stem}.md"
    output_path.write_text(markdown, encoding="utf-8")

    header_count, hierarchy_depth = _count_headers(markdown)

    return ConvertResult(
        markdown=markdown,
        output_path=output_path,
        timing_s=timing_s,
        header_count=header_count,
        hierarchy_depth=hierarchy_depth,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Convert PDF to markdown via PyMuPDF")
    parser.add_argument("pdf", type=Path, help="Input PDF file")
    parser.add_argument("output_dir", type=Path, help="Output directory")
    args = parser.parse_args()

    if not args.pdf.is_file():
        print(f"Error: {args.pdf} is not a file", file=sys.stderr)
        sys.exit(1)

    print(f"Converting {args.pdf.name}...")
    res = convert(args.pdf, args.output_dir)
    print(f"  Output: {res.output_path}")
    print(f"  Time:   {res.timing_s:.1f}s")
    print(f"  Headers: {res.header_count}  depth: {res.hierarchy_depth}")
