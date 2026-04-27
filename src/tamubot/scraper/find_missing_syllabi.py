"""Compare syllabus coverage across Howdy Portal, Simple Syllabus, and the catalog.

Produces one report per department under tamu_data/raw/missing_syllabuses/<DEPT>.md
containing two sections:
  1. Source Gap   — courses in Howdy Portal but missing from Simple Syllabus
  2. Catalog Gap  — courses in catalog but missing from BOTH syllabus sources

Flags:
  --source-gap   Only include the source-gap section
  --catalog-gap  Only include the catalog-gap section
  (default)      Both sections
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path

RAW_DIR = Path("tamu_data/raw")
HOWDY_DIR = RAW_DIR / "howdy_portal"
SIMPLE_DIR = RAW_DIR / "simple_syllabus"
CATALOG_DIR = RAW_DIR / "catalog"
OUTPUT_DIR = RAW_DIR / "missing_syllabuses"

# Filename pattern: {term_code}_{SUBJ}_{COURSE}_{SECTION}_{CRN}.pdf
PDF_RE = re.compile(r"^(\d{6})_([A-Z]+)_(\d{3})_(\d{3})_(\d+)\.pdf$")

# Catalog heading pattern: SUBJ NNN Title
CATALOG_COURSE_RE = re.compile(r"^([A-Z]{3,5})\s+(\d{3})\s+.+")

TERM_SEMESTER = {"11": "Spring", "21": "Summer", "31": "Fall", "41": "Fall"}


def term_label(term_code: str) -> str:
    year = term_code[:4]
    sem = TERM_SEMESTER.get(term_code[4:], term_code[4:])
    return f"{sem} {year}"


def parse_pdfs(root: Path) -> dict[str, dict[str, set[str]]]:
    """Return {dept: {term_code: {course_number, ...}}}."""
    result: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    if not root.exists():
        return result
    for pdf in root.rglob("*.pdf"):
        m = PDF_RE.match(pdf.name)
        if not m:
            continue
        term_code, subj, course, _section, _crn = m.groups()
        result[subj][term_code].add(course)
    return result


def parse_pdfs_sections(root: Path) -> dict[str, dict[str, dict[str, list[str]]]]:
    """Return {dept: {term_code: {course: [section_strings]}}}."""
    result: dict[str, dict[str, dict[str, list[str]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    if not root.exists():
        return result
    for pdf in root.rglob("*.pdf"):
        m = PDF_RE.match(pdf.name)
        if not m:
            continue
        term_code, subj, course, section, crn = m.groups()
        result[subj][term_code][course].append(f"{section} (CRN {crn})")
    return result


def parse_catalog(catalog_dir: Path, dept: str) -> set[str]:
    """Extract graduate course numbers (>=600) from catalog course-descriptions file."""
    courses: set[str] = set()
    pattern = f"graduate_course-descriptions_{dept.lower()}.md"
    desc_file = catalog_dir / dept / pattern
    if not desc_file.exists():
        return courses
    for line in desc_file.read_text(encoding="utf-8").splitlines():
        m = CATALOG_COURSE_RE.match(line)
        if m and m.group(1) == dept and int(m.group(2)) >= 600:
            courses.add(m.group(2))
    return courses


# ---------------------------------------------------------------------------
# Per-department report builders
# ---------------------------------------------------------------------------


def source_gap_section(
    dept: str,
    howdy_sections: dict[str, dict[str, list[str]]],
    simple_courses: dict[str, set[str]],
) -> list[str]:
    """Return markdown lines for the source-gap section of one department."""
    lines: list[str] = []
    all_terms = sorted(set(howdy_sections) | set(simple_courses))
    count = 0
    for term_code in all_terms:
        howdy_course_set = set(howdy_sections.get(term_code, {}).keys())
        simple_course_set = simple_courses.get(term_code, set())
        has_howdy = term_code in howdy_sections
        has_simple = term_code in simple_courses

        lines.append(f"\n### {term_label(term_code)} ({term_code})\n")

        if not has_howdy and not has_simple:
            lines.append("_No data from either source for this term._\n")
            continue
        if not has_howdy:
            lines.append(
                f"_No Howdy Portal data for this term. Simple Syllabus has {len(simple_course_set)} course(s)._\n"
            )
            continue
        if not has_simple:
            lines.append(
                f"_No Simple Syllabus data for this term. Howdy Portal has {len(howdy_course_set)} course(s)._\n"
            )
            for c in sorted(howdy_course_set):
                sections = howdy_sections[term_code][c]
                sec_str = ", ".join(sorted(sections))
                lines.append(f"- {dept} {c}  —  sections: {sec_str}")
                count += 1
            continue

        missing = sorted(howdy_course_set - simple_course_set)
        if not missing:
            lines.append("_No gap — all Howdy Portal courses are also in Simple Syllabus._\n")
        else:
            for c in missing:
                sections = howdy_sections[term_code][c]
                sec_str = ", ".join(sorted(sections))
                lines.append(f"- {dept} {c}  —  sections: {sec_str}")
                count += 1

    if count == 0:
        lines.insert(0, "\nNo source gaps found.\n")
    else:
        lines.insert(0, f"\n**{count} course-sections** in Howdy Portal with no Simple Syllabus match.\n")
    return lines


def catalog_gap_section(
    dept: str,
    howdy_courses: dict[str, set[str]],
    simple_courses: dict[str, set[str]],
    catalog_dir: Path,
) -> list[str]:
    """Return markdown lines for the catalog-gap section of one department."""
    catalog_courses = parse_catalog(catalog_dir, dept)
    if not catalog_courses:
        return ["\nNo catalog course-descriptions file found for this department.\n"]

    all_howdy: set[str] = set()
    for tc in howdy_courses.values():
        all_howdy |= tc
    all_simple: set[str] = set()
    for tc in simple_courses.values():
        all_simple |= tc

    covered = all_howdy | all_simple
    missing = sorted(catalog_courses - covered)

    lines: list[str] = []
    lines.append(
        f"\nCatalog lists **{len(catalog_courses)}** graduate courses, "
        f"**{len(covered)}** have at least one syllabus, "
        f"**{len(missing)}** missing.\n"
    )
    if missing:
        for c in missing:
            lines.append(f"- {dept} {c}")
    else:
        lines.append("Full coverage — every catalog course has at least one syllabus.\n")
    return lines


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source-gap", action="store_true", help="Only include source-gap section")
    parser.add_argument("--catalog-gap", action="store_true", help="Only include catalog-gap section")
    args = parser.parse_args()

    include_source = not args.catalog_gap or args.source_gap
    include_catalog = not args.source_gap or args.catalog_gap

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Parse all sources
    howdy_sec = parse_pdfs_sections(HOWDY_DIR)
    howdy_crs = parse_pdfs(HOWDY_DIR)
    simple_crs = parse_pdfs(SIMPLE_DIR)

    # Discover all departments across all sources
    all_depts: set[str] = set(howdy_crs) | set(simple_crs)
    if CATALOG_DIR.exists():
        all_depts |= {d.name for d in CATALOG_DIR.iterdir() if d.is_dir()}

    written: list[str] = []

    for dept in sorted(all_depts):
        lines = [f"# {dept} — Missing Syllabuses Report\n"]

        if include_source:
            lines.append(
                "\n## Source Gap\n\n"
                "Courses that **have a syllabus in Howdy Portal** but are **missing from Simple Syllabus**.\n"
                "These syllabi exist on howdyportal.tamu.edu but were not found on simplesyllabus.com.\n"
            )
            lines.extend(
                source_gap_section(
                    dept,
                    howdy_sec.get(dept, {}),
                    simple_crs.get(dept, {}),
                )
            )

        if include_catalog:
            lines.append(
                "\n## Catalog Gap\n\n"
                "Courses listed in the **catalog.tamu.edu course descriptions** that have "
                "**no syllabus in either Howdy Portal or Simple Syllabus**.\n"
                "These courses are offered by the department but no syllabus PDF was found in any source.\n"
            )
            lines.extend(
                catalog_gap_section(
                    dept,
                    howdy_crs.get(dept, {}),
                    simple_crs.get(dept, {}),
                    CATALOG_DIR,
                )
            )

        report = "\n".join(lines)
        out = OUTPUT_DIR / f"{dept}.md"
        out.write_text(report, encoding="utf-8")
        written.append(str(out))
        print(report)
        print()

    print(f"Reports saved: {', '.join(written)}")


if __name__ == "__main__":
    main()
