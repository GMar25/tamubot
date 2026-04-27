from __future__ import annotations

import re
import statistics
from pathlib import Path


def _tokens_approx(text: str) -> int:
    return max(0, round(len(text) / 4))


_HEADER_RE = re.compile(r"^(#{1,6})\s+", re.MULTILINE)
_LIST_RE = re.compile(r"^(?:[-*]|\d+\.)\s+", re.MULTILINE)
_TABLE_RE = re.compile(r"\|.*\|")
_ARTIFACT_RE = re.compile(r"&amp;|&lt;|&gt;|\ufffd")


def compute_file_metrics(markdown: str, filter_name: str | None = None) -> dict:
    headers = _HEADER_RE.findall(markdown)
    header_count = len(headers)

    hierarchy_depth: dict[int, int] = {}
    for h in headers:
        level = len(h)
        hierarchy_depth[level] = hierarchy_depth.get(level, 0) + 1

    # Orphan sections: header with empty body (next line is another header or EOF)
    lines = markdown.splitlines()
    orphan_sections = 0
    empty_sections = 0
    for i, line in enumerate(lines):
        if _HEADER_RE.match(line):
            # Look at next non-blank line
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j >= len(lines):
                orphan_sections += 1
                empty_sections += 1
            elif _HEADER_RE.match(lines[j]):
                empty_sections += 1
                # Check if there's no body content at all until next header
                orphan_sections += 1

    result = {
        "header_count": header_count,
        "hierarchy_depth": hierarchy_depth,
        "orphan_sections": orphan_sections,
        "empty_sections": empty_sections,
        "total_tokens": _tokens_approx(markdown),
        "table_count": len(_TABLE_RE.findall(markdown)),
        "list_count": len(_LIST_RE.findall(markdown)),
        "encoding_artifacts": len(_ARTIFACT_RE.findall(markdown)),
    }
    if filter_name:
        result["filter_name"] = filter_name
    return result


def compute_filter_metrics(input_md: str, output_md: str, filter_name: str) -> dict:
    tokens_before = _tokens_approx(input_md)
    tokens_after = _tokens_approx(output_md)
    reduction = ((tokens_before - tokens_after) / tokens_before * 100) if tokens_before > 0 else 0.0
    return {
        "tokens_before": tokens_before,
        "tokens_after": tokens_after,
        "reduction_pct": round(reduction, 2),
        "filter_name": filter_name,
    }


def compute_aggregate_metrics(file_metrics: list[dict]) -> dict:
    if not file_metrics:
        return {}

    # Collect numeric keys (skip hierarchy_depth which is a dict, and filter_name which is str)
    numeric_keys = [k for k in file_metrics[0] if isinstance(file_metrics[0][k], (int, float)) and k != "filter_name"]

    agg: dict = {}
    for key in numeric_keys:
        values = [m[key] for m in file_metrics if key in m and isinstance(m[key], (int, float))]
        if not values:
            continue
        agg[key] = {
            "mean": round(statistics.mean(values), 2),
            "min": min(values),
            "max": max(values),
        }

    # Outlier detection: files > 2 std devs from mean on any metric
    outliers: list[dict] = []
    for key in numeric_keys:
        values = [m.get(key, 0) for m in file_metrics if isinstance(m.get(key), (int, float))]
        if len(values) < 3:
            continue
        mean = statistics.mean(values)
        stdev = statistics.stdev(values)
        if stdev == 0:
            continue
        threshold = 2 * stdev
        for i, m in enumerate(file_metrics):
            val = m.get(key)
            if isinstance(val, (int, float)) and abs(val - mean) > threshold:
                outliers.append(
                    {
                        "file_index": i,
                        "metric": key,
                        "value": val,
                        "mean": round(mean, 2),
                        "stdev": round(stdev, 2),
                    }
                )

    agg["outliers"] = outliers
    return agg


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Compute quality metrics for markdown files")
    parser.add_argument("input_dir", type=Path, help="Directory of .md files")
    parser.add_argument("--output", type=Path, default=None, help="Output JSON path")
    args = parser.parse_args()

    md_files = sorted(args.input_dir.glob("*.md"))
    all_metrics: list[dict] = []

    for md_path in md_files:
        text = md_path.read_text(encoding="utf-8")
        m = compute_file_metrics(text)
        m["file"] = md_path.name
        all_metrics.append(m)
        print(
            f"  {md_path.name}: tokens={m['total_tokens']}, headers={m['header_count']}, "
            f"artifacts={m['encoding_artifacts']}"
        )

    agg = compute_aggregate_metrics(all_metrics)

    output = {
        "file_count": len(all_metrics),
        "files": all_metrics,
        "aggregate": agg,
    }

    out_path = args.output or args.input_dir / "metrics.json"
    out_path.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(f"\nMetrics for {len(all_metrics)} files -> {out_path}")
    if agg.get("outliers"):
        print(f"  {len(agg['outliers'])} outlier(s) detected")
