"""Base types for v4 pipeline filters.

Every filter implements the BaseFilter protocol:
    filter.apply(input_dir, output_dir, config) -> FilterResult

Each filter is also runnable standalone via its __main__ block.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@dataclass
class FilterResult:
    """Outcome of running a filter over a directory of markdown files."""

    input_count: int = 0
    modified_count: int = 0
    metrics: dict[str, Any] = field(default_factory=dict)
    log_entries: list[dict[str, Any]] = field(default_factory=list)


@runtime_checkable
class BaseFilter(Protocol):
    """Protocol that every v4 filter must satisfy."""

    name: str

    def apply(self, input_dir: Path, output_dir: Path, config: dict[str, Any]) -> FilterResult: ...
